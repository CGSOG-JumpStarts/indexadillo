#!/usr/bin/env python3
"""Check security and resilience invariants in compiled ARM templates."""

import json
import sys
from pathlib import Path


def resources(template):
    entries = template.get("resources", [])
    if isinstance(entries, dict):
        entries = entries.values()
    for resource in entries:
        yield resource
        nested = resource.get("properties", {}).get("template")
        if nested:
            yield from resources(nested)


def validate(template):
    rows = list(resources(template))
    storage = [r for r in rows if r["type"].lower() == "microsoft.storage/storageaccounts"]
    assert storage and all(r["properties"]["allowSharedKeyAccess"] is False for r in storage)
    assert all(r["properties"]["allowBlobPublicAccess"] is False for r in storage)
    functions = [r for r in rows if r["type"].lower() == "microsoft.web/sites"]
    assert functions and all(r["properties"]["httpsOnly"] for r in functions)
    auth = [
        r for r in rows if r["type"].lower() == "microsoft.web/sites/config" and "authsettingsV2" in r["name"]
    ]
    assert auth and all(r["properties"]["globalValidation"]["requireAuthentication"] for r in auth)
    assignments = [r for r in rows if r["type"].lower() == "microsoft.authorization/roleassignments"]
    forbidden = {
        "b24988ac-6180-42a0-ab88-20f7382dd24c",
        "8e3af657-a8ff-443c-a75c-2fe8c4bcb635",
        "7ca78c08-252a-4471-8644-bb5ff32d4ba0",
    }
    assert all(
        not any(role in str(r["properties"]["roleDefinitionId"]) for role in forbidden) for r in assignments
    )
    subscriptions = [r for r in rows if r["type"].lower().endswith("systemtopics/eventsubscriptions")]
    assert subscriptions and all("deadLetterWithResourceIdentity" in r["properties"] for r in subscriptions)
    assert any("privateEndpoints" in r["type"] for r in rows)


if __name__ == "__main__":
    validate(json.loads(Path(sys.argv[1]).read_text()))
    print("Infrastructure invariants passed")
