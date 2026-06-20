#!/usr/bin/env python3
"""Audit display-only identity labels that generic UI scans can miss.

This gate checks identity strings whose source is data or slot keys rather than
plain UI literals: class/ascendancy names and item slot labels. It also checks a
small set of known display sinks so raw identity keys do not leak back into UI.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


CLASS_BLOCK_START_RE = re.compile(r"^\s*classes=\{\s*$")
CLASS_BLOCK_END_RE = re.compile(r"^\s*connectionArt=\{\s*$")
NAME_RE = re.compile(r'\bname="([^"]+)"')
SLOT_LABELS = (
    "Weapon 1",
    "Weapon 2",
    "Weapon 1 Swap",
    "Weapon 2 Swap",
    "Helmet",
    "Body Armour",
    "Gloves",
    "Boots",
    "Amulet",
    "Ring 1",
    "Ring 2",
    "Ring 3",
    "Belt",
    "Charm 1",
    "Charm 2",
    "Charm 3",
    "Flask 1",
    "Flask 2",
    "Arm 1",
    "Arm 2",
    "Leg 1",
    "Leg 2",
    "Socket",
)


@dataclass(frozen=True)
class AuditConfig:
    root: Path
    po_path: Path
    tree_path: Path
    output: Path
    output_format: str
    fail_on_open: bool
    include_sinks: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "AuditConfig":
        root = args.root.resolve()
        po_path = args.po if args.po.is_absolute() else root / args.po
        tree_path = args.tree if args.tree.is_absolute() else root / args.tree
        output = args.output if args.output.is_absolute() else root / args.output
        return cls(
            root=root,
            po_path=po_path,
            tree_path=tree_path,
            output=output,
            output_format=args.format,
            fail_on_open=args.fail_on_open,
            include_sinks=not args.no_sinks,
        )


@dataclass(frozen=True)
class Finding:
    category: str
    status: str
    path: str
    line: int
    msgid: str
    msgstr: str | None
    reason: str

    def row(self) -> dict[str, object]:
        return {
            "category": self.category,
            "status": self.status,
            "path": self.path,
            "line": self.line,
            "msgid": self.msgid,
            "msgstr": self.msgstr,
            "reason": self.reason,
        }


class PoCatalog:
    def __init__(self, path: Path) -> None:
        self.entries = self.read(path)

    def status(self, msgid: str) -> tuple[str, str | None]:
        msgstr = self.entries.get(msgid)
        if msgstr is None:
            return "missing", None
        if not msgstr:
            return "empty", msgstr
        if msgstr == msgid:
            return "same", msgstr
        return "translated", msgstr

    @staticmethod
    def read(path: Path) -> dict[str, str]:
        entries: dict[str, str] = {}
        msgid: str | None = None
        msgstr = ""
        active: str | None = None
        for raw_line in path.read_text(encoding="utf-8").splitlines() + [""]:
            line = raw_line.strip()
            if line.startswith("msgid "):
                if msgid is not None:
                    entries[msgid] = msgstr
                msgid = ast.literal_eval(line[6:].strip())
                msgstr = ""
                active = "msgid"
                continue
            if line.startswith("msgstr ") and msgid is not None:
                msgstr = ast.literal_eval(line[7:].strip())
                active = "msgstr"
                continue
            if line.startswith('"') and msgid is not None:
                if active == "msgid":
                    msgid += ast.literal_eval(line)
                elif active == "msgstr":
                    msgstr += ast.literal_eval(line)
                continue
            if not line and msgid is not None:
                entries[msgid] = msgstr
                msgid = None
                msgstr = ""
                active = None
        return entries


class IdentityCollector:
    def __init__(self, config: AuditConfig) -> None:
        self.config = config

    def class_labels(self) -> list[tuple[str, str, int]]:
        labels: dict[str, tuple[str, str, int]] = {}
        in_classes = False
        for line_no, line in enumerate(self.config.tree_path.read_text(encoding="utf-8").splitlines(), start=1):
            if CLASS_BLOCK_START_RE.match(line):
                in_classes = True
                continue
            if in_classes and CLASS_BLOCK_END_RE.match(line):
                break
            if not in_classes:
                continue
            match = NAME_RE.search(line)
            if match:
                labels.setdefault(match.group(1), ("class-label", self.config.tree_path.relative_to(self.config.root).as_posix(), line_no))
        return sorted((label, path, line_no) for label, (_, path, line_no) in labels.items())

    def slot_labels(self) -> list[tuple[str, str, int]]:
        return [(label, "src/Classes/ItemsTab.lua", 46) for label in SLOT_LABELS]


class SinkScanner:
    checks = (
        (
            "src/Classes/BuildListControl.lua",
            "build-list-class-display",
            re.compile(r"build\.ascendClassName|build\.className"),
            re.compile(r"\bui\s*\(\s*rawClassName\s*\)|displayClassName"),
            8,
        ),
        (
            "src/Classes/ImportTab.lua",
            "import-character-class-detail",
            re.compile(r"\bdetail\s*=\s*(?:string\.format|s_format|formatUI).*charClass"),
            re.compile(r"displayClass"),
            1,
        ),
        (
            "src/Classes/ItemsTab.lua",
            "item-set-tooltip-slot-label",
            re.compile(r"tooltip:AddLine.*slot\.slotName"),
            re.compile(r"\btr\s*\(\s*slot\.label|TranslateUI"),
            1,
        ),
        (
            "src/Classes/CompareTab.lua",
            "compare-slot-row-label",
            re.compile(r"DrawString\(.*\.\. label|drawCompactSlotRow\(drawY,\s*label\b"),
            re.compile(r"displayLabel"),
            1,
        ),
    )

    def __init__(self, root: Path) -> None:
        self.root = root

    def scan(self) -> list[Finding]:
        findings: list[Finding] = []
        for rel, reason, raw_re, translated_re, window in self.checks:
            path = self.root / rel
            lines = path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if not raw_re.search(line):
                    continue
                context = "\n".join(lines[index : index + window])
                if translated_re.search(context):
                    continue
                findings.append(Finding("raw-sink", "open", rel, index + 1, line.strip(), None, reason))
        return findings


class DisplayIdentityAuditor:
    def __init__(self, config: AuditConfig) -> None:
        self.config = config
        self.catalog = PoCatalog(config.po_path)
        self.collector = IdentityCollector(config)

    def run(self) -> int:
        findings = self.catalog_findings()
        if self.config.include_sinks:
            findings.extend(SinkScanner(self.config.root).scan())
        findings = sorted(findings, key=lambda item: (item.category, item.path, item.line, item.msgid))
        Reporter.write(self.config.output, self.config.output_format, findings)
        summary = Reporter.summary(findings)
        print(
            f"wrote {summary['open_count']} display identity findings to {self.config.output} "
            f"status={summary['by_status']} category={summary['by_category']}"
        )
        if self.config.fail_on_open and findings:
            return 1
        return 0

    def catalog_findings(self) -> list[Finding]:
        findings: list[Finding] = []
        for category, rows in (
            ("class-label", self.collector.class_labels()),
            ("slot-label", self.collector.slot_labels()),
        ):
            for msgid, path, line_no in rows:
                status, msgstr = self.catalog.status(msgid)
                if status == "translated":
                    continue
                findings.append(Finding(category, status, path, line_no, msgid, msgstr, "missing display identity translation"))
        return findings


class Reporter:
    @staticmethod
    def summary(findings: list[Finding]) -> dict[str, object]:
        return {
            "open_count": len(findings),
            "by_status": dict(sorted(Counter(finding.status for finding in findings).items())),
            "by_category": dict(sorted(Counter(finding.category for finding in findings).items())),
        }

    @staticmethod
    def write(path: Path, fmt: str, findings: list[Finding]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        summary = Reporter.summary(findings)
        if fmt == "json":
            path.write_text(json.dumps({**summary, "findings": [finding.row() for finding in findings]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return
        lines = [
            "# Display Identity i18n Audit",
            "",
            f"open_count: {summary['open_count']}",
            f"by_status: {summary['by_status']}",
            f"by_category: {summary['by_category']}",
            "",
        ]
        for finding in findings:
            lines.append(
                f"- `{finding.status}` `{finding.category}` {finding.path}:{finding.line} "
                f"`{finding.msgid}` ({finding.reason})"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--po", type=Path, default=Path("locale/zh_TW/LC_MESSAGES/pob.po"))
    parser.add_argument("--tree", type=Path, default=Path("src/TreeData/0_5/tree.lua"))
    parser.add_argument("--output", type=Path, default=Path("work/pob/display-identity-audit.md"))
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--no-sinks", action="store_true")
    parser.add_argument("--fail-on-open", action="store_true")
    args = parser.parse_args()
    return DisplayIdentityAuditor(AuditConfig.from_args(args)).run()


if __name__ == "__main__":
    raise SystemExit(main())
