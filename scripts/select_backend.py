#!/usr/bin/env python3
"""Emit a staged host configuration for an isolated backend benchmark."""

import argparse
import json
from pathlib import Path


def host_configuration(backend):
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "src/host.json").read_text())
    durable = config["extensions"]["durableTask"]
    if backend == "scheduler":
        durable["hubName"] = "indexadillobenchmark"
        durable["storageProvider"] = {
            "type": "azureManaged",
            "connectionStringName": "DURABLE_TASK_SCHEDULER_CONNECTION_STRING",
        }
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True, choices=["storage", "scheduler"])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with Path(args.output).open("x") as output:
        json.dump(host_configuration(args.backend), output, indent=2)


if __name__ == "__main__":
    main()
