#!/usr/bin/env python3
"""Import exact-match PoeCharm CSV translations into an existing PO catalog."""

from __future__ import annotations

import argparse
import ast
import csv
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}|%[sdif]|%\.[0-9]+f|%[0-9]+\$[sdif]")
COLOR_RE = re.compile(r"\^(?:x[0-9A-Fa-f]{6}|.)")


@dataclass
class PoEntry:
    msgid: str
    msgstr: str
    comments: list[str] = field(default_factory=list)
    msgstr_start: int = -1
    msgstr_end: int = -1


@dataclass(frozen=True)
class CsvTranslation:
    msgid: str
    msgstr: str
    source_name: str


@dataclass
class MergeResult:
    translated: int = 0
    already: int = 0
    skipped_invalid: int = 0
    skipped_conflict: int = 0


def po_unquote(text: str) -> str:
    return ast.literal_eval(text)


def po_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def normalize_msgid(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("&", "and")
    text = re.sub(r"['’`´]", "", text)
    text = re.sub(r"\b(rejuv)\.?\b", "rejuvenation", text)
    text = re.sub(r"^[+-]\s*", "", text)
    text = re.sub(r"[^a-z0-9{}%]+", " ", text)
    return " ".join(text.split())


def read_po_entries(path: Path) -> list[PoEntry]:
    entries: list[PoEntry] = []
    comments: list[str] = []
    msgid: str | None = None
    msgstr: str | None = None
    active: str | None = None
    msgstr_start = -1
    msgstr_end = -1

    def flush() -> None:
        nonlocal comments, msgid, msgstr, active, msgstr_start, msgstr_end
        if msgid is not None:
            entries.append(PoEntry(msgid, msgstr or "", comments, msgstr_start, msgstr_end))
        comments = []
        msgid = None
        msgstr = None
        active = None
        msgstr_start = -1
        msgstr_end = -1

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith("#"):
            comments.append(raw_line)
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
        raise ValueError(f"{path}:{line_no}: unsupported PO line: {raw_line}")
    flush()
    return entries


def token_counter(pattern: re.Pattern[str], text: str) -> Counter[str]:
    return Counter(pattern.findall(text))


def validate_translation(msgid: str, msgstr: str) -> None:
    placeholders = token_counter(PLACEHOLDER_RE, msgid)
    translated_placeholders = token_counter(PLACEHOLDER_RE, msgstr)
    if translated_placeholders != placeholders:
        raise ValueError(
            f"placeholder tokens differ for {msgid!r}: "
            f"expected {dict(placeholders)!r}, got {dict(translated_placeholders)!r}"
        )
    colors = token_counter(COLOR_RE, msgid)
    translated_colors = token_counter(COLOR_RE, msgstr)
    if translated_colors != colors:
        raise ValueError(
            f"color escapes differ for {msgid!r}: "
            f"expected {dict(colors)!r}, got {dict(translated_colors)!r}"
        )


def read_csv_translations(paths: list[Path]) -> list[CsvTranslation]:
    translations: list[CsvTranslation] = []
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                if len(row) < 2:
                    continue
                msgid = row[0].strip()
                msgstr = row[1].strip()
                if not msgid or not msgstr or msgid == msgstr:
                    continue
                translations.append(CsvTranslation(msgid, msgstr, path.name))
    return translations


def build_translation_index(
    rows: list[CsvTranslation],
    match_mode: str,
) -> tuple[dict[str, CsvTranslation], set[str]]:
    buckets: dict[str, list[CsvTranslation]] = {}
    for row in rows:
        key = row.msgid if match_mode == "exact" else normalize_msgid(row.msgid)
        buckets.setdefault(key, []).append(row)

    index: dict[str, CsvTranslation] = {}
    conflicts: set[str] = set()
    for key, matches in buckets.items():
        translations = {match.msgstr for match in matches}
        if len(translations) > 1:
            conflicts.add(key)
            continue
        index[key] = matches[0]
    return index, conflicts


def replace_po_msgstrs(entries: list[PoEntry], path: Path, replacements: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    spans: list[tuple[int, int, str]] = []
    for entry in entries:
        msgstr = replacements.get(entry.msgid)
        if msgstr is None:
            continue
        if entry.msgstr_start < 0 or entry.msgstr_end < entry.msgstr_start:
            raise ValueError(f"{path}: cannot replace msgstr for {entry.msgid!r}")
        spans.append((entry.msgstr_start, entry.msgstr_end, f"msgstr {po_quote(msgstr)}\n"))
    for start, end, line in sorted(spans, reverse=True):
        lines[start:end] = [line]
    path.write_text("".join(lines), encoding="utf-8")


def merge_translations(
    po_path: Path,
    csv_paths: list[Path],
    dry_run: bool,
    strict: bool,
    replace_same: bool,
    match_mode: str,
) -> MergeResult:
    entries = read_po_entries(po_path)
    translations, conflicts = build_translation_index(read_csv_translations(csv_paths), match_mode)
    result = MergeResult()
    replacements: dict[str, str] = {}

    for entry in entries:
        if entry.msgid == "":
            continue
        key = entry.msgid if match_mode == "exact" else normalize_msgid(entry.msgid)
        if entry.msgstr and not (replace_same and entry.msgstr == entry.msgid):
            if key in conflicts or key in translations:
                result.already += 1
            continue
        if key in conflicts:
            result.skipped_conflict += 1
            continue
        match = translations.get(key)
        if not match:
            continue
        msgstr = match.msgstr
        try:
            validate_translation(entry.msgid, msgstr)
        except ValueError:
            if strict:
                raise
            result.skipped_invalid += 1
            continue
        if entry.msgstr == msgstr:
            result.already += 1
            continue
        result.translated += 1
        if dry_run:
            continue
        replacements[entry.msgid] = msgstr

    if not dry_run:
        replace_po_msgstrs(entries, po_path, replacements)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--po", type=Path, required=True)
    parser.add_argument("--csv", type=Path, action="append", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true", help="fail instead of skipping placeholder/color mismatches")
    parser.add_argument("--match-mode", choices=("exact", "normalized"), default="exact")
    parser.add_argument("--replace-same", action="store_true", help="replace entries whose msgstr is exactly the English msgid")
    args = parser.parse_args()

    result = merge_translations(args.po, args.csv, args.dry_run, args.strict, args.replace_same, args.match_mode)
    action = "would import" if args.dry_run else "imported"
    print(
        f"{action} {result.translated} translations into {args.po}; "
        f"{result.already} existing translations left unchanged; "
        f"{result.skipped_invalid} invalid translations skipped; "
        f"{result.skipped_conflict} conflict matches skipped"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
