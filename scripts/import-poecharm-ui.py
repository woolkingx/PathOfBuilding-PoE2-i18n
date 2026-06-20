#!/usr/bin/env python3
"""Build a reviewable PO catalog from PoeCharm UI CSV translations."""

from __future__ import annotations

import argparse
import csv
from collections import OrderedDict
from pathlib import Path


UI_FILES = [
    "GUI.csv",
    "Main.csv",
    "Build.csv",
    "BuildListControl.csv",
    "TreeTab.csv",
    "SkillsTab.csv",
    "ItemsTab.csv",
    "ItemListControl.csv",
    "ItemSetListControl.csv",
    "ItemDBControl.csv",
    "ConfigTab.csv",
    "ConfigOptions.csv",
    "CalcsTab.csv",
    "CalcSections.csv",
    "CalcSetup.csv",
    "CalcOffence.csv",
    "CalcDefence.csv",
    "CalcBreakdown.csv",
    "CompareTab.csv",
    "ImportTab.csv",
    "NotesTab.csv",
    "PartyTab.csv",
    "PowerReportListControl.csv",
    "PassiveTreeView.csv",
    "SharedItemListControl.csv",
    "SharedItemSetListControl.csv",
    "ExtBuildListControl.csv",
    "PoBArchivesProvider.csv",
    "Help.csv",
    "TradeQuery.csv",
    "Unsorted.csv",
]


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


def read_msgids_from_po(path: Path) -> list[str]:
    msgids: list[str] = []
    active = False
    current = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("msgid "):
            if active and current:
                msgids.append(current)
            current = decode_lua_string(line[6:].strip())
            active = True
            continue
        if active and line.startswith('"'):
            current += decode_lua_string(line)
            continue
        if active:
            if current:
                msgids.append(current)
            current = ""
            active = False
    if active and current:
        msgids.append(current)
    return msgids


def read_poecharm_csvs(root: Path, locale: str) -> dict[str, tuple[str, str]]:
    translations: dict[str, tuple[str, str]] = {}
    base = root / "Data" / "Translate" / locale
    for file_name in UI_FILES:
        path = base / file_name
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                if len(row) < 2:
                    continue
                msgid = row[0].strip()
                msgstr = row[1].strip()
                if not msgid or not msgstr:
                    continue
                translations.setdefault(msgid, (msgstr, file_name))
    return translations


def write_po(entries: OrderedDict[str, tuple[str, str]], out_path: Path, language: str, source_locale: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        'msgid ""',
        'msgstr ""',
        f'"Project-Id-Version: Path of Building PoE2 UI from PoeCharm {source_locale}\\n"',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        f'"Language: {language}\\n"',
        "",
    ]
    for msgid, (msgstr, source_file) in entries.items():
        lines.append(f"#. Source: PoeCharm2 {source_locale}/{source_file}")
        lines.append(f"msgid {po_quote(msgid)}")
        lines.append(f"msgstr {po_quote(msgstr)}")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poecharm-root", type=Path, default=Path("../poecharm2"))
    parser.add_argument("--candidate-po", type=Path, default=Path("work/pob/ui-msgids-candidates.po"))
    parser.add_argument("--source-locale", default="zh-rCN")
    parser.add_argument("--language", default="zh_CN")
    parser.add_argument("--output-po", type=Path, default=Path("locale/zh_CN/LC_MESSAGES/pob.po"))
    args = parser.parse_args()

    candidate_msgids = set(read_msgids_from_po(args.candidate_po))
    translations = read_poecharm_csvs(args.poecharm_root, args.source_locale)
    entries: OrderedDict[str, tuple[str, str]] = OrderedDict()
    for msgid in sorted(candidate_msgids, key=str.lower):
        if msgid in translations:
            entries[msgid] = translations[msgid]
    write_po(entries, args.output_po, args.language, args.source_locale)
    print(f"matched {len(entries)} of {len(candidate_msgids)} UI candidates into {args.output_po}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
