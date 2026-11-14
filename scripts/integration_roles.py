#!/usr/bin/env python3
"""Grant scoped data roles to the explicitly configured temporary CI identity."""

import json
import os
import subprocess

from azd_env import load


def run(*args):
    return subprocess.check_output(args, text=True).strip()  # noqa: S603


def main():
    env = load()
    group = env["RESOURCE_GROUP_NAME"]
    principal = run(
        "az", "ad", "sp", "show", "--id", os.environ["AZURE_CLIENT_ID"], "--query", "id", "-o", "tsv"
    )
    resources = json.loads(run("az", "resource", "list", "-g", group, "-o", "json"))
    for resource in resources:
        kind = resource["type"].lower()
        roles = []
        if kind == "microsoft.storage/storageaccounts":
            roles = ["Storage Blob Data Contributor"]
        elif kind == "microsoft.search/searchservices":
            roles = ["Search Service Contributor", "Search Index Data Contributor"]
        for role in roles:
            run(
                "az",
                "role",
                "assignment",
                "create",
                "--assignee-object-id",
                principal,
                "--assignee-principal-type",
                "ServicePrincipal",
                "--role",
                role,
                "--scope",
                resource["id"],
            )


if __name__ == "__main__":
    main()
