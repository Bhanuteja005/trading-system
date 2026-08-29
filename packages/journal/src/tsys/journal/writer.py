"""Append-only JSONL writer.

One line per decision, flushed immediately. A crash loses at most the line
being written, never the history.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from .schema import JournalEntry


class Journal:
    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, day: date) -> Path:
        return self.dir / f"decisions-{day.isoformat()}.jsonl"

    def append(self, entry: JournalEntry) -> Path:
        path = self.path_for(entry.at.date())
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_record(), separators=(",", ":")) + "\n")
            fh.flush()
        return path

    def read(self, day: date) -> Iterator[dict[str, Any]]:
        path = self.path_for(day)
        if not path.exists():
            return
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue  # tolerate one torn trailing line
