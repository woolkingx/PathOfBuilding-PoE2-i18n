#!/usr/bin/env python3
"""Audit PO translation progress for empty and identity translations."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def po_unquote(text: str) -> str:
    return ast.literal_eval(text)


@dataclass(frozen=True)
class PoEntry:
    msgid: str
    msgstr: str


@dataclass(frozen=True)
class CatalogReport:
    path: str
    domain: str
    total: int
    empty: int
    same: int
    changed: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "domain": self.domain,
            "total": self.total,
            "empty": self.empty,
            "same": self.same,
            "changed": self.changed,
        }


class PoCatalog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries = self._read_entries()

    @property
    def domain(self) -> str:
        name = self.path.name
        if name.endswith(".worker.po"):
            return name.removesuffix(".worker.po")
        if name.endswith(".po"):
            return name.removesuffix(".po")
        return self.path.stem

    def report(self) -> CatalogReport:
        total = len(self.entries)
        empty = sum(1 for entry in self.entries if entry.msgstr == "")
        same = sum(1 for entry in self.entries if entry.msgid and entry.msgstr == entry.msgid)
        return CatalogReport(
            path=str(self.path),
            domain=self.domain,
            total=total,
            empty=empty,
            same=same,
            changed=total - empty - same,
        )

    def _read_entries(self) -> list[PoEntry]:
        entries: list[PoEntry] = []
        msgid: str | None = None
        msgstr: str | None = None
        active: str | None = None

        def flush() -> None:
            nonlocal msgid, msgstr, active
            if msgid:
                entries.append(PoEntry(msgid, msgstr or ""))
            msgid = None
            msgstr = None
            active = None

        for line_no, raw_line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
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
                continue
            if line.startswith('"') and active == "msgid":
                msgid = (msgid or "") + po_unquote(line)
                continue
            if line.startswith('"') and active == "msgstr":
                msgstr = (msgstr or "") + po_unquote(line)
                continue
            raise ValueError(f"{self.path}:{line_no}: unsupported PO line: {raw_line}")
        flush()
        return entries


class ProgressAudit:
    def __init__(self, po_paths: list[Path]) -> None:
        self.po_paths = po_paths

    def reports(self) -> list[CatalogReport]:
        return [PoCatalog(path).report() for path in self.po_paths]

    @staticmethod
    def write_json(reports: list[CatalogReport], output: Path | None) -> None:
        payload = {
            "catalogs": [report.as_dict() for report in reports],
            "totals": ProgressAudit.total_report(reports),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")

    @staticmethod
    def write_table(reports: list[CatalogReport]) -> None:
        print(f"{'domain':32} {'total':>7} {'empty':>7} {'same':>7} {'changed':>7} path")
        for report in reports:
            print(
                f"{report.domain[:32]:32} {report.total:7} {report.empty:7} "
                f"{report.same:7} {report.changed:7} {report.path}"
            )
        totals = ProgressAudit.total_report(reports)
        print(
            f"{'TOTAL':32} {totals['total']:7} {totals['empty']:7} "
            f"{totals['same']:7} {totals['changed']:7}"
        )

    @staticmethod
    def total_report(reports: list[CatalogReport]) -> dict[str, int]:
        return {
            "total": sum(report.total for report in reports),
            "empty": sum(report.empty for report in reports),
            "same": sum(report.same for report in reports),
            "changed": sum(report.changed for report in reports),
        }


def default_po_paths(root: Path) -> list[Path]:
    return [
        root / "locale/zh_TW/LC_MESSAGES/items.po",
        root / "locale/zh_TW/LC_MESSAGES/skills.po",
        root / "locale/zh_TW/LC_MESSAGES/passives.po",
        root / "locale/zh_TW/LC_MESSAGES/stats.po",
        root / "locale/zh_TW/LC_MESSAGES/pob.po",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--po", type=Path, action="append", help="PO file to audit; defaults to zh_TW domains")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--output", type=Path, help="write JSON report to this path")
    parser.add_argument("--fail-on-empty", action="store_true")
    parser.add_argument("--fail-on-same", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    po_paths = args.po or default_po_paths(root)
    reports = ProgressAudit([path if path.is_absolute() else root / path for path in po_paths]).reports()

    if args.format == "json":
        ProgressAudit.write_json(reports, args.output)
    else:
        ProgressAudit.write_table(reports)

    if args.fail_on_empty and any(report.empty for report in reports):
        return 1
    if args.fail_on_same and any(report.same for report in reports):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
