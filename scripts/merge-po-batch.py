#!/usr/bin/env python3
"""Merge a reviewed PO translation batch into a canonical locale PO file."""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path


PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}|%\.[0-9]+f|%[0-9]+\$[sdif]|%[sdif]")


@dataclass
class PoEntry:
    msgid: str
    msgstr: str
    comments: list[str] = field(default_factory=list)


def po_unquote(text: str) -> str:
    return ast.literal_eval(text)


def po_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def read_po_entries(path: Path) -> list[PoEntry]:
    entries: list[PoEntry] = []
    comments: list[str] = []
    msgid: str | None = None
    msgstr: str | None = None
    active: str | None = None

    def flush() -> None:
        nonlocal comments, msgid, msgstr, active
        if msgid:
            entries.append(PoEntry(msgid, msgstr or "", comments))
        comments = []
        msgid = None
        msgstr = None
        active = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith("#"):
            comments.append(raw_line)
            continue
        if line.startswith("msgid "):
            if msgid is not None:
                flush()
            msgid = po_unquote(line[6:].strip())
            active = "msgid"
            continue
        if line.startswith("msgstr "):
            msgstr = po_unquote(line[7:].strip())
            active = "msgstr"
            continue
        if line.startswith('"') and active == "msgid":
            msgid = (msgid or "") + po_unquote(line)
            continue
        if line.startswith('"') and active == "msgstr":
            msgstr = (msgstr or "") + po_unquote(line)
            continue
        raise ValueError(f"{path}: unsupported PO line: {raw_line}")
    flush()
    return entries


def validate_placeholders(msgid: str, msgstr: str) -> None:
    source = sorted(PLACEHOLDER_RE.findall(msgid))
    translated = sorted(PLACEHOLDER_RE.findall(msgstr))
    if translated != source:
        raise ValueError(f"translation for {msgid!r} has placeholders {translated!r}, expected {source!r}")


def parse_block(lines: list[str]) -> tuple[str | None, str | None, int | None, int | None]:
    msgid: str | None = None
    msgstr: str | None = None
    active: str | None = None
    msgstr_start: int | None = None
    msgstr_end: int | None = None
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line.startswith("#"):
            continue
        if line.startswith("msgid "):
            msgid = po_unquote(line[6:].strip())
            active = "msgid"
            continue
        if line.startswith("msgstr "):
            msgstr = po_unquote(line[7:].strip())
            active = "msgstr"
            msgstr_start = index
            msgstr_end = index + 1
            continue
        if line.startswith('"') and active == "msgid":
            msgid = (msgid or "") + po_unquote(line)
            continue
        if line.startswith('"') and active == "msgstr":
            msgstr = (msgstr or "") + po_unquote(line)
            msgstr_end = index + 1
            continue
    return msgid, msgstr, msgstr_start, msgstr_end


def update_existing_entries(canonical_po: Path, batch: dict[str, PoEntry]) -> int:
    content = canonical_po.read_text(encoding="utf-8")
    blocks = content.rstrip("\n").split("\n\n")
    changed = 0
    new_blocks: list[str] = []
    for block in blocks:
        lines = block.splitlines()
        msgid, msgstr, msgstr_start, msgstr_end = parse_block(lines)
        replacement = batch.get(msgid or "")
        if (
            replacement
            and replacement.msgstr
            and msgstr in ("", msgid)
            and msgstr_start is not None
            and msgstr_end is not None
        ):
            lines = lines[:msgstr_start] + [f"msgstr {po_quote(replacement.msgstr)}"] + lines[msgstr_end:]
            changed += 1
        new_blocks.append("\n".join(lines))
    if changed:
        canonical_po.write_text("\n\n".join(new_blocks) + "\n", encoding="utf-8")
    return changed


def merge_entries(
    canonical_po: Path,
    entries: list[PoEntry],
    dry_run: bool,
    update_empty_or_same: bool,
    disallow_additions: bool,
) -> tuple[int, int]:
    canonical_entries = read_po_entries(canonical_po)
    existing = {entry.msgid: entry for entry in canonical_entries}
    batch = {entry.msgid: entry for entry in entries if entry.msgstr and entry.msgstr != entry.msgid}
    additions = [entry for entry in entries if entry.msgstr and entry.msgid not in existing]
    updates = [
        entry for entry in batch.values()
        if entry.msgid in existing and existing[entry.msgid].msgstr in ("", entry.msgid)
    ] if update_empty_or_same else []
    for entry in additions + updates:
        validate_placeholders(entry.msgid, entry.msgstr)
    if disallow_additions and additions:
        names = ", ".join(entry.msgid for entry in additions[:5])
        if len(additions) > 5:
            names += ", ..."
        raise ValueError(f"{canonical_po}: refusing {len(additions)} additions: {names}")
    if dry_run:
        return len(additions), len(updates)

    updated_count = update_existing_entries(canonical_po, batch) if update_empty_or_same and updates else 0
    if updated_count != len(updates):
        raise ValueError(
            f"{canonical_po}: expected to update {len(updates)} existing entries, "
            f"but updated {updated_count}"
        )

    lines = [canonical_po.read_text(encoding="utf-8").rstrip(), ""]
    for entry in additions:
        lines.append("#. Source: reviewed translation batch")
        for comment in entry.comments:
            if comment.startswith("#:"):
                lines.append(comment)
        lines.append(f"msgid {po_quote(entry.msgid)}")
        lines.append(f"msgstr {po_quote(entry.msgstr)}")
        lines.append("")
    if additions:
        canonical_po.write_text("\n".join(lines), encoding="utf-8")
    return len(additions), updated_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-po", type=Path, required=True)
    parser.add_argument("--batch-po", type=Path, action="append", required=True)
    parser.add_argument("--update-empty-or-same", action="store_true")
    parser.add_argument("--disallow-additions", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    entries: list[PoEntry] = []
    for batch_po in args.batch_po:
        entries.extend(read_po_entries(batch_po))
    additions, updates = merge_entries(
        args.canonical_po,
        entries,
        args.dry_run,
        args.update_empty_or_same,
        args.disallow_additions,
    )
    action = "would merge" if args.dry_run else "merged"
    print(f"{action} {additions} new and {updates} existing translated entries into {args.canonical_po}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
