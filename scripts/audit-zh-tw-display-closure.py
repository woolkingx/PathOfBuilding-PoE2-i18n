#!/usr/bin/env python3
"""Audit zh_TW display closure for known PoB i18n surfaces."""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Finding:
    surface: str
    category: str
    path: str
    line: int
    msgid: str
    detail: str

    def row(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "category": self.category,
            "path": self.path,
            "line": self.line,
            "msgid": self.msgid,
            "detail": self.detail,
        }


class PoCatalog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries = self._read(path)

    def status(self, msgid: str) -> str:
        msgstr = self.entries.get(msgid)
        if msgstr is None:
            return "missing"
        if msgstr == "":
            return "empty"
        if msgstr == msgid:
            return "same"
        return "translated"

    @staticmethod
    def _read(path: Path) -> dict[str, str]:
        entries: dict[str, str] = {}
        msgid: str | None = None
        msgstr = ""
        active: str | None = None
        for raw in path.read_text(encoding="utf-8").splitlines() + [""]:
            line = raw.strip()
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


class LuaDisplayScanner:
    label_re = re.compile(r"\blabel\s*=\s*([\"'])(.*?)(?<!\\)\1")
    tree_name_re = re.compile(r"\bname\s*=\s*([\"'])(.*?)(?<!\\)\1")

    def __init__(self, root: Path, pob_catalog: PoCatalog, passive_catalog: PoCatalog, stats_catalog: PoCatalog) -> None:
        self.root = root
        self.pob_catalog = pob_catalog
        self.passive_catalog = passive_catalog
        self.stats_catalog = stats_catalog

    def scan(self) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self.scan_calc_labels())
        findings.extend(self.scan_tree_msgids())
        findings.extend(self.scan_raw_display_routes())
        return findings

    def scan_calc_labels(self) -> list[Finding]:
        findings: list[Finding] = []
        for rel in ("src/Modules/CalcSections.lua", "src/Modules/BuildDisplayStats.lua"):
            path = self.root / rel
            text = path.read_text(encoding="utf-8")
            for match in self.label_re.finditer(text):
                msgid = match.group(2)
                status = self.pob_catalog.status(msgid)
                if status in {"missing", "empty", "same"}:
                    findings.append(Finding(
                        surface="calcs_table",
                        category=f"po_{status}",
                        path=rel,
                        line=text[:match.start()].count("\n") + 1,
                        msgid=msgid,
                        detail="calc label must be present and translated in pob.po",
                    ))
        return findings

    def scan_tree_msgids(self) -> list[Finding]:
        findings: list[Finding] = []
        for path in sorted((self.root / "src/TreeData").glob("*/tree.lua")):
            rel = path.relative_to(self.root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in self.tree_name_re.finditer(text):
                msgid = ast.literal_eval(match.group(1) + match.group(2) + match.group(1))
                if msgid and self.passive_catalog.status(msgid) == "missing":
                    findings.append(Finding(
                        surface="passive_tree",
                        category="passive_msgid_missing",
                        path=rel,
                        line=text[:match.start()].count("\n") + 1,
                        msgid=msgid,
                        detail="tree node/class display name must exist in passives.po",
                    ))
            in_stats = False
            depth = 0
            for line_no, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if not in_stats and stripped.startswith("stats={"):
                    in_stats = True
                    depth = stripped.count("{") - stripped.count("}")
                    continue
                if not in_stats:
                    continue
                depth += stripped.count("{") - stripped.count("}")
                for match in re.finditer(r"([\"'])(?:\\.|(?!\1).)*\1", stripped):
                    msgid = ast.literal_eval(match.group(0))
                    if msgid and self.stats_catalog.status(msgid) == "missing":
                        findings.append(Finding(
                            surface="passive_tree",
                            category="stat_msgid_missing",
                            path=rel,
                            line=line_no,
                            msgid=msgid,
                            detail="tree stat display text must exist in stats.po",
                        ))
                if depth <= 0:
                    in_stats = False
                    depth = 0
        return findings

    def scan_raw_display_routes(self) -> list[Finding]:
        checks = [
            (
                "passive_tree",
                "src/Classes/TreeTab.lua",
                re.compile(r"\blabel\s*=\s*addition\.dn|\bdescriptions\s*=\s*copyTable\(addition\.sd\)"),
                "tree timeless/search display should translate dn/sd",
            ),
            (
                "passive_tree",
                "src/Classes/ItemsTab.lua",
                re.compile(r"tooltip:AddLine\([^,\n]+,\s*(?:colorCodes\.MAGIC\s*\.\.\s*node\.dn|['\"]\^x7F7F7F['\"]\s*\.\.\s*stat)"),
                "cluster node tooltip should translate node name/stat text",
            ),
            (
                "items_list",
                "src/Classes/ItemListControl.lua",
                re.compile(r"trItem\(item\.name\)"),
                "item list display should use component-aware TranslateItemDisplay(item)",
            ),
            (
                "items_list",
                "src/Classes/ItemDBControl.lua",
                re.compile(r"trItem\(item\.name\)|itemSearchText\(item\.name\)"),
                "item DB display/search should use item object helpers",
            ),
            (
                "items_list",
                "src/Classes/ItemSlotControl.lua",
                re.compile(r"trItem\(item\.name\)"),
                "item slot dropdown should use component-aware TranslateItemDisplay(item)",
            ),
        ]
        findings: list[Finding] = []
        for surface, rel, pattern, detail in checks:
            path = self.root / rel
            text = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    findings.append(Finding(surface, "raw_display_route", rel, line_no, "", detail))
                if (
                    surface == "passive_tree"
                    and "nodeSlider" in line
                    and ".sd[" in line
                    and "trStat(" not in line
                ):
                    findings.append(Finding(surface, "raw_display_route", rel, line_no, "", detail))

        skills_text = (self.root / "src/Classes/SkillsTab.lua").read_text(encoding="utf-8")
        if "local function displaySkill" not in skills_text or "slot.nameSpec.inactiveText = displaySkill" not in skills_text:
            findings.append(Finding(
                surface="skills_selected",
                category="raw_display_route",
                path="src/Classes/SkillsTab.lua",
                line=0,
                msgid="",
                detail="GemSelectControl selected field needs localized inactive display while keeping raw nameSpec",
            ))
        return findings


class ClosureReport:
    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings

    def as_json(self) -> str:
        summary: dict[str, int] = {}
        for finding in self.findings:
            key = f"{finding.surface}:{finding.category}"
            summary[key] = summary.get(key, 0) + 1
        return json.dumps({
            "open": len(self.findings),
            "summary": summary,
            "findings": [finding.row() for finding in self.findings],
        }, indent=2, ensure_ascii=False)

    def as_markdown(self) -> str:
        lines = ["# zh_TW Display Closure Audit", "", f"- open: `{len(self.findings)}`", ""]
        for finding in self.findings:
            loc = f"{finding.path}:{finding.line}" if finding.line else finding.path
            msgid = f" `{finding.msgid}`" if finding.msgid else ""
            lines.append(f"- `{finding.surface}` `{finding.category}` {loc}{msgid} - {finding.detail}")
        return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--format", choices=("json", "md"), default="md")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-open", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    pob = PoCatalog(root / "locale/zh_TW/LC_MESSAGES/pob.po")
    passives = PoCatalog(root / "locale/zh_TW/LC_MESSAGES/passives.po")
    stats = PoCatalog(root / "locale/zh_TW/LC_MESSAGES/stats.po")
    findings = LuaDisplayScanner(root, pob, passives, stats).scan()
    report = ClosureReport(findings)
    text = report.as_json() if args.format == "json" else report.as_markdown()
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text)
    if args.fail_on_open and findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
