#!/usr/bin/env python3
"""Fill empty PO translations with their source msgid as a placeholder."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PoEntry:
    msgid: str
    msgstr: str
    msgstr_start: int
    msgstr_end: int


def po_unquote(text: str) -> str:
    return ast.literal_eval(text)


def po_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


class PoCatalog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        self.entries = self._read_entries()

    def _read_entries(self) -> list[PoEntry]:
        entries: list[PoEntry] = []
        msgid: str | None = None
        msgstr: str | None = None
        active: str | None = None
        msgstr_start = -1
        msgstr_end = -1

        def flush() -> None:
            nonlocal msgid, msgstr, active, msgstr_start, msgstr_end
            if msgid is not None and msgid != "":
                entries.append(PoEntry(msgid, msgstr or "", msgstr_start, msgstr_end))
            msgid = None
            msgstr = None
            active = None
            msgstr_start = -1
            msgstr_end = -1

        for line_no, raw_line in enumerate(self.lines, start=1):
            line = raw_line.strip()
            if not line:
                flush()
                continue
            if line.startswith("#"):
                continue
            if line.startswith("msgid "):
                flush()
                msgid = po_unquote(line[6:].strip())
                active = "msgid"
                continue
            if line.startswith("msgstr "):
                if msgid is None:
                    raise ValueError(f"{self.path}:{line_no}: msgstr before msgid")
                msgstr = po_unquote(line[7:].strip())
                active = "msgstr"
                msgstr_start = line_no - 1
                msgstr_end = line_no
                continue
            if line.startswith('"') and active == "msgid":
                msgid = (msgid or "") + po_unquote(line)
                continue
            if line.startswith('"') and active == "msgstr":
                msgstr = (msgstr or "") + po_unquote(line)
                msgstr_end = line_no
                continue
            raise ValueError(f"{self.path}:{line_no}: unsupported PO line: {raw_line.rstrip()}")
        flush()
        return entries

    def empty_entries(self) -> list[PoEntry]:
        return [entry for entry in self.entries if entry.msgstr == ""]

    def fill_empty_with_source(self, dry_run: bool) -> int:
        replacements = self.empty_entries()
        if dry_run or not replacements:
            return len(replacements)
        lines = list(self.lines)
        for entry in sorted(replacements, key=lambda item: item.msgstr_start, reverse=True):
            if entry.msgstr_start < 0 or entry.msgstr_end < entry.msgstr_start:
                raise ValueError(f"{self.path}: cannot replace msgstr for {entry.msgid!r}")
            lines[entry.msgstr_start:entry.msgstr_end] = [f"msgstr {po_quote(entry.msgid)}\n"]
        self.path.write_text("".join(lines), encoding="utf-8")
        return len(replacements)


class PlaceholderFiller:
    def __init__(self, paths: list[Path], dry_run: bool) -> None:
        self.paths = paths
        self.dry_run = dry_run

    def run(self) -> int:
        total = 0
        for path in self.paths:
            catalog = PoCatalog(path)
            count = catalog.fill_empty_with_source(self.dry_run)
            total += count
            action = "would fill" if self.dry_run else "filled"
            print(f"{path}: {action} {count} empty msgstr placeholders")
        print(f"total: {total}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--po", type=Path, action="append", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return PlaceholderFiller(args.po, args.dry_run).run()


if __name__ == "__main__":
    raise SystemExit(main())
