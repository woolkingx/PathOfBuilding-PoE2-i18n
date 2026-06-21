#!/usr/bin/env python3
"""Export untranslated PO candidates into small review/model translation batches."""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path


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


INTERNAL_TOKEN_RE = re.compile(r"^[A-Za-z0-9_]+$")
FORMAT_ONLY_RE = re.compile(r"^[%+\\-\\.0-9dfs: ]+$")
INTERNAL_KEY_RE = re.compile(r"^[A-Za-z]+:[A-Za-z0-9_]+$")
INTERNAL_DOTTED_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
SYNTHETIC_FRAGMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*-$")
BRACED_TOKEN_RE = re.compile(r"\{[^{}]+\}")
PRINTF_TOKEN_RE = re.compile(r"%[sdif]|%\.[0-9]+f|%[0-9]+\$[sdif]")
COLOR_TOKEN_RE = re.compile(r"\^(?:x[0-9A-Fa-f]{6}|.)")
FORMULA_REMAINDER_RE = re.compile(r"^[%+*/xX().,:; <>=\\-\\s]*$")
UI_SINGLE_WORDS = {
    "Search",
    "Level",
    "Label",
}


def looks_formula_only(text: str) -> bool:
    remainder = BRACED_TOKEN_RE.sub("", text)
    remainder = PRINTF_TOKEN_RE.sub("", remainder)
    remainder = COLOR_TOKEN_RE.sub("", remainder)
    return not remainder.strip() or bool(FORMULA_REMAINDER_RE.match(remainder))


def looks_translatable_ui(text: str) -> bool:
    if text in UI_SINGLE_WORDS:
        return True
    if looks_formula_only(text):
        return False
    if FORMAT_ONLY_RE.match(text):
        return False
    if INTERNAL_KEY_RE.match(text):
        return False
    if INTERNAL_DOTTED_KEY_RE.match(text):
        return False
    if SYNTHETIC_FRAGMENT_RE.match(text):
        return False
    if INTERNAL_TOKEN_RE.match(text) and not text.endswith(":"):
        return False
    if " .. " in text or "[[" in text or "]]" in text:
        return False
    if text.startswith(("%^", "^x")):
        return False
    if re.match(r"^\^[A-Za-z]", text):
        return False
    if text in {"(%l)(%u)", "-label"}:
        return False
    return True


def write_batch(entries: list[PoEntry], path: Path, language: str, batch_index: int, total_batches: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Translation batch for Path of Building UI.",
        "# Fill msgstr only. Do not change msgid, comments, ordering, placeholders, or color escapes.",
        "# Keep PoB placeholders such as {0}, {0:output:Stat}, %s, ^7, and ^xRRGGBB intact.",
        f"# Batch {batch_index} of {total_batches}.",
        'msgid ""',
        'msgstr ""',
        '"Project-Id-Version: Path of Building PoE2 UI translation batch\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        f'"Language: {language}\\n"',
        "",
    ]
    for entry in entries:
        lines.extend(entry.comments)
        lines.append(f"msgid {po_quote(entry.msgid)}")
        lines.append('msgstr ""')
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-po", type=Path, required=True)
    parser.add_argument("--existing-po", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--language", default="zh_TW")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--filter-ui", action="store_true", help="skip obvious format strings and internal tokens")
    args = parser.parse_args()

    known = {entry.msgid for entry in read_po_entries(args.existing_po)}
    candidates = [
        entry for entry in read_po_entries(args.candidate_po)
        if entry.msgid and entry.msgid not in known
    ]
    if args.filter_ui:
        candidates = [entry for entry in candidates if looks_translatable_ui(entry.msgid)]
    if args.limit > 0:
        candidates = candidates[: args.limit]

    batches = [
        candidates[index:index + args.batch_size]
        for index in range(0, len(candidates), args.batch_size)
    ]
    total = len(batches)
    for batch_index, batch in enumerate(batches, start=1):
        write_batch(batch, args.output_dir / f"ui-{args.language}-{batch_index:03d}.po", args.language, batch_index, total)
    print(f"exported {len(candidates)} entries into {total} batches under {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
