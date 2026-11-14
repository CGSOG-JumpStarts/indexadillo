#!/usr/bin/env python3
"""Deployment-identity tooling. No index administration is exposed through HTTP."""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import profile, scopes  # noqa: E402
from core.search import Search  # noqa: E402
from core.storage import store  # noqa: E402


def name(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,126}[a-z0-9]", value):
        raise argparse.ArgumentTypeError("Invalid Search object name")
    return value


def create_index(index):
    config = profile()
    Search(config).ensure_index(index)
    storage = store()
    previous = storage.read("registry", f"{index}.json") or {}
    storage.write(
        "registry",
        f"{index}.json",
        {**previous, "fingerprint": config.fingerprint(), "profile": config.model_dump()},
    )


def cutover(index, alias, record):
    search = Search(profile())
    old = search.call("GET", f"aliases/{alias}", acceptable=(200, 404))
    previous = old.json().get("indexes", []) if old.status_code == 200 else []
    # Exclusive create prevents accidentally destroying the rollback record.
    with Path(record).open("x") as output:
        json.dump({"alias": alias, "previous_indexes": previous, "new_index": index}, output, indent=2)
    search.alias(alias, index)
    time.sleep(10)
    actual = search.call("GET", f"aliases/{alias}").json()["indexes"]
    if actual != [index]:
        raise RuntimeError("Alias verification failed; retain both indexes and inspect the cutover record")


def knowledge(index, source_name, base_name):
    """Only tenant-isolated indexes with no restricted content can use this GA route.

    Generic knowledge-base access does not substitute for the application's custom
    permission filters. The registry policy also applies to future publication.
    """
    tenants = {value.tenant_id for value in scopes().values() if index in value.indexes}
    if len(tenants) != 1:
        raise ValueError("A knowledge source requires one explicitly configured tenant per physical index")
    tenant = next(iter(tenants))
    search = Search(profile())
    unsafe = search.call(
        "POST",
        f"indexes/{index}/docs/search",
        json={
            "search": "*",
            "top": 0,
            "count": True,
            "filter": f"visibility ne 'tenant' or tenant_id ne '{tenant}'",
        },
    ).json()
    if unsafe.get("@odata.count", 0):
        raise ValueError("Use the authenticated application retrieval route for restricted or shared indexes")
    storage = store()
    with storage.lock(f"registry/{index}"):
        registry = storage.read("registry", f"{index}.json")
        if not registry:
            raise ValueError("Provision the index registry first")
        storage.write("registry", f"{index}.json", {**registry, "knowledge_tenant": tenant})
    search.knowledge_source(source_name, index)
    search.call(
        "PUT",
        f"knowledgebases/{base_name}",
        json={
            "name": base_name,
            "knowledgeSources": [{"name": source_name}],
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-index")
    create.add_argument("--index", type=name, required=True)
    alias = commands.add_parser("alias")
    alias.add_argument("--index", type=name, required=True)
    alias.add_argument("--alias", type=name, required=True)
    alias.add_argument("--record", required=True)
    kb = commands.add_parser("knowledge")
    kb.add_argument("--index", type=name, required=True)
    kb.add_argument("--source", type=name, required=True)
    kb.add_argument("--base", type=name, required=True)
    kb.add_argument(
        "--confirm-ingestion-drained",
        action="store_true",
        help="Required: pause source ingestion and drain active publications before binding knowledge",
    )
    args = parser.parse_args()
    if not os.getenv("SEARCH_SERVICE_ENDPOINT") or not os.getenv("ARTIFACT_STORAGE_ACCOUNT_NAME"):
        from azd_env import load

        values = load()
        for key in (
            "SEARCH_SERVICE_ENDPOINT",
            "ARTIFACT_STORAGE_ACCOUNT_NAME",
            "SOURCE_STORAGE_ACCOUNT_NAME",
            "TENANT_SCOPES_JSON",
        ):
            if key in values:
                os.environ.setdefault(key, values[key])
    if args.command == "create-index":
        create_index(args.index)
    elif args.command == "alias":
        cutover(args.index, args.alias, args.record)
    else:
        if not args.confirm_ingestion_drained:
            parser.error("Pause/drain ingestion before provisioning a knowledge source")
        knowledge(args.index, args.source, args.base)


if __name__ == "__main__":
    main()
