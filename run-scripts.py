#!/bin/env .venv/bin/python3

import re
from pathlib import Path

NUMBER = re.compile(r"(\d+)-.*\.py")

def sort_key(path: Path) -> tuple[int, str]:
    match = NUMBER.fullmatch(path.name)
    if match is None:
        raise ValueError(f"Unexpected filename: {path.name}")
    return int(match.group(1)), path.name

for path in sorted(Path(".").glob("[0-9]*-*.py"), key=sort_key):
    print(f"Running {path}")
    __import__(path.stem)
