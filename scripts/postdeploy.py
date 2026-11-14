#!/usr/bin/env python3
import os

from azd_env import load


def main():
    values = load()
    for key in (
        "SOURCE_STORAGE_ACCOUNT_NAME",
        "ARTIFACT_STORAGE_ACCOUNT_NAME",
        "SEARCH_SERVICE_ENDPOINT",
        "AZURE_OPENAI_ENDPOINT",
        "DI_ENDPOINT",
        "TENANT_SCOPES_JSON",
    ):
        os.environ[key] = values[key]
    from provision_indexes import main as provision

    provision()


if __name__ == "__main__":
    main()
