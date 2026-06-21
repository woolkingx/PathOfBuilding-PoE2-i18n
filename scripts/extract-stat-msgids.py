#!/usr/bin/env python3
"""Extract stat description text msgids for the zh_TW stat domain PO catalog."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


TEXT_ASSIGN_RE = re.compile(r"\btext\s*=")
LUA_STRING_RE = re.compile(r"(['\"])(?:\\.|(?!\1).)*\1")
MODS_GLOB = "src/Data/Mod*.lua"
TREE_GLOB = "src/TreeData/*/tree.lua"


def decode_lua_string(token: str) -> str:
    body = token[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch != "\\" or i + 1 >= len(body):
            out.append(ch)
            i += 1
            continue
        nxt = body[i + 1]
        if nxt == "n":
            out.append("\n")
        elif nxt == "t":
            out.append("\t")
        elif nxt == "r":
            out.append("\r")
        elif nxt in ('"', "'", "\\"):
            out.append(nxt)
        else:
            out.append(nxt)
        i += 2
    return "".join(out)


def po_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def collect_stat_texts(root: Path) -> set[str]:
    texts: set[str] = set()
    for path in sorted(root.glob("src/Data/StatDescriptions/**/*.lua")):
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = TEXT_ASSIGN_RE.search(raw_line)
            if not match:
                continue
            rest = raw_line[match.end():].lstrip()
            if not rest or rest[0] not in ("\"", "'"):
                continue
            quote = rest[0]
            value_chars: list[str] = []
            i = 1
            while i < len(rest):
                ch = rest[i]
                if ch == "\\" and i + 1 < len(rest):
                    value_chars.append(rest[i])
                    value_chars.append(rest[i + 1])
                    i += 2
                    continue
                if ch == quote:
                    break
                value_chars.append(ch)
                i += 1
            else:
                continue
            token = quote + "".join(value_chars) + quote
            text = decode_lua_string(token)
            if text:
                texts.add(text)
    return texts


def is_keyed_lua_string(prefix: str, start: int) -> bool:
    before = prefix[:start].rstrip()
    if before.endswith("["):
        return True
    return bool(re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\s*=\s*$", before))


def collect_mod_stat_texts(root: Path) -> set[str]:
    texts: set[str] = set()
    for path in sorted(root.glob(MODS_GLOB)):
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "statOrder" not in raw_line:
                continue
            prefix = raw_line.split("statOrder", 1)[0]
            for match in LUA_STRING_RE.finditer(prefix):
                if is_keyed_lua_string(prefix, match.start()):
                    continue
                text = decode_lua_string(match.group(0))
                if text:
                    texts.add(text)
    return texts


def collect_tree_stat_texts(root: Path) -> set[str]:
    texts: set[str] = set()
    for path in sorted(root.glob(TREE_GLOB)):
        in_stats = False
        depth = 0
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not in_stats and line.startswith("stats={"):
                in_stats = True
                depth = line.count("{") - line.count("}")
                continue
            if not in_stats:
                continue
            depth += line.count("{") - line.count("}")
            for match in LUA_STRING_RE.finditer(line):
                text = decode_lua_string(match.group(0))
                if text:
                    texts.add(text)
            if depth <= 0:
                in_stats = False
                depth = 0
    return texts


def existing_msgids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    msgids: set[str] = set()
    active = False
    current = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("msgid "):
            if active and current:
                msgids.add(current)
            current = decode_lua_string(line[6:].strip())
            active = True
            continue
        if active and line.startswith('"'):
            current += decode_lua_string(line)
            continue
        if active:
            if current:
                msgids.add(current)
            current = ""
            active = False
    if active and current:
        msgids.add(current)
    return msgids


def append_missing_msgids(msgids: set[str], po_path: Path) -> int:
    existing = existing_msgids(po_path)
    missing = sorted(msgids - existing)
    if not missing:
        return 0
    lines = [po_path.read_text(encoding="utf-8").rstrip(), ""]
    for msgid in missing:
        lines.append("#. Source: scripts/extract-stat-msgids.py")
        lines.append(f"msgid {po_quote(msgid)}")
        lines.append('msgstr ""')
        lines.append("")
    po_path.write_text("\n".join(lines), encoding="utf-8")
    return len(missing)


def write_po(msgids: set[str], out_path: Path) -> int:
    entries = sorted(msgids)
    lines = [
        "# Extracted stat description msgids.",
        "# Generated by scripts/extract-stat-msgids.py; keep msgstr empty in this phase.",
        "# Scope: src/Data/StatDescriptions/**/*.lua text fields, Mod*.lua positional stat lines, and TreeData tree.lua stats.",
        "",
        'msgid ""',
        'msgstr ""',
        '"Project-Id-Version: Path of Building PoE2 Stat translation\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        '"Language: zh_TW\\n"',
        "",
    ]
    for msgid in entries:
        lines.append(f"msgid {po_quote(msgid)}")
        lines.append('msgstr ""')
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return len(entries)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("locale/zh_TW/LC_MESSAGES/stats.po"))
    parser.add_argument("--append-missing-to", type=Path, help="append missing msgids to an existing PO while preserving translations")
    args = parser.parse_args()

    root = args.root.resolve()
    texts = collect_stat_texts(root)
    texts.update(collect_mod_stat_texts(root))
    texts.update(collect_tree_stat_texts(root))
    output = root / args.output if not args.output.is_absolute() else args.output
    count = write_po(texts, output)
    print(f"wrote {count} stat msgids to {output}")
    if args.append_missing_to:
        append_target = root / args.append_missing_to if not args.append_missing_to.is_absolute() else args.append_missing_to
        appended = append_missing_msgids(texts, append_target)
        print(f"appended {appended} missing stat msgids to {append_target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
