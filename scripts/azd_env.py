"""Read azd output as data without evaluating shell expressions."""

import re
import shlex
import subprocess


def load():
    output = subprocess.check_output(["azd", "env", "get-values"], text=True)  # noqa: S603,S607
    result = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator and re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            parts = shlex.split(value)
            if len(parts) != 1:
                raise ValueError("Unexpected azd environment output")
            result[key] = parts[0]
    return result
