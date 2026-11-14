#!/usr/bin/env python3
"""Provision all configured physical indexes with the deployment identity."""

import time

from manage_search import create_index

from core.azure import ServiceError
from core.config import scopes


def main():
    for name in sorted({index for scope in scopes().values() for index in scope.indexes}):
        for attempt in range(9):
            try:
                create_index(name)
                break
            except ServiceError as exc:
                if exc.status != 403 or attempt == 8:
                    raise
                time.sleep(min(60, 2**attempt))


if __name__ == "__main__":
    main()
