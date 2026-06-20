#!/usr/bin/env python3
"""Validate that a translated PO batch preserves source msgids and placeholders."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import re
from dataclasses import dataclass
from pathlib import Path


PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}|%\.[0-9]+f|%[0-9]+\$[sdif]|%[sdif]")
COLOR_RE = re.compile(r"\^(?:x[0-9A-Fa-f]{6}|.)")


@dataclass
class PoEntry:
    msgid: str
    msgstr: str


def po_unquote(text: str) -> str:
    return ast.literal_eval(text)


def read_po_entries(path: Path) -> list[PoEntry]:
    entries: list[PoEntry] = []
    msgid: str | None = None
    msgstr: str | None = None
    active: str | None = None

    def flush() -> None:
        nonlocal msgid, msgstr, active
        if msgid is not None and msgid != "":
            entries.append(PoEntry(msgid, msgstr or ""))
        msgid = None
        msgstr = None
        active = None

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
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
                raise ValueError(f"{path}:{line_no}: msgstr before msgid")
            msgstr = po_unquote(line[7:].strip())
            active = "msgstr"
            continue
        if line.startswith('"') and active == "msgid":
            msgid = (msgid or "") + po_unquote(line)
            continue
        if line.startswith('"') and active == "msgstr":
            msgstr = (msgstr or "") + po_unquote(line)
            continue
        raise ValueError(f"{path}:{line_no}: unsupported PO line: {raw_line}")
    flush()
    return entries


def tokens(pattern: re.Pattern[str], text: str) -> list[str]:
    return pattern.findall(text)


def token_counter(pattern: re.Pattern[str], text: str) -> Counter[str]:
    return Counter(tokens(pattern, text))


def validate(source: Path, translated: Path) -> list[str]:
    source_entries = read_po_entries(source)
    translated_entries = read_po_entries(translated)
    errors: list[str] = []

    if [entry.msgid for entry in translated_entries] != [entry.msgid for entry in source_entries]:
        errors.append("msgid order or content differs from source batch")
        return errors

    for index, (source_entry, translated_entry) in enumerate(zip(source_entries, translated_entries), start=1):
        if not translated_entry.msgstr:
            errors.append(f"entry {index} has empty msgstr for {source_entry.msgid!r}")
        source_placeholders = token_counter(PLACEHOLDER_RE, source_entry.msgid)
        translated_placeholders = token_counter(PLACEHOLDER_RE, translated_entry.msgstr)
        if translated_placeholders != source_placeholders:
            errors.append(
                f"entry {index} placeholder tokens differ for {source_entry.msgid!r}: "
                f"expected {dict(source_placeholders)!r}, got {dict(translated_placeholders)!r}"
            )
        source_colors = token_counter(COLOR_RE, source_entry.msgid)
        translated_colors = token_counter(COLOR_RE, translated_entry.msgstr)
        if translated_colors != source_colors:
            errors.append(
                f"entry {index} color escapes differ for {source_entry.msgid!r}: "
                f"expected {dict(source_colors)!r}, got {dict(translated_colors)!r}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-po", type=Path, required=True)
    parser.add_argument("--translated-po", type=Path, required=True)
    args = parser.parse_args()

    errors = validate(args.source_po, args.translated_po)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"validated {len(read_po_entries(args.source_po))} translated entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
