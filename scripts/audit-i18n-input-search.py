#!/usr/bin/env python3
"""Audit i18n input/search boundaries for the PoB i18n lane."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Finding:
    id: str
    status: str
    file: str
    message: str


@dataclass(frozen=True)
class SurfaceRule:
    id: str
    file: str
    required: tuple[str, ...]
    message: str

    def check(self, root: Path) -> Finding | None:
        path = root / self.file
        if not path.exists():
            return Finding(self.id, "open", self.file, "file is missing")
        text = path.read_text(encoding="utf-8")
        missing = [needle for needle in self.required if needle not in text]
        if missing:
            return Finding(
                self.id,
                "open",
                self.file,
                f"{self.message}; missing: {', '.join(missing)}",
            )
        return None


class I18nInputSearchAuditor:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.rules = (
            SurfaceRule(
                id="lang-current-locale-alias-api",
                file="src/Modules/Lang.lua",
                required=(
                    "searchAliases",
                    "function lang:GetSearchAliases(domain, msgid)",
                    "function lang:SearchText(domain, msgid)",
                    "function lang:ItemSearchText(item)",
                    "function GetLocalizedSearchAliases(domain, text)",
                    "function GetLocalizedSearchText(domain, text)",
                    "function GetLocalizedItemSearchText(item)",
                ),
                message="Lang.lua must own raw English plus active-locale search aliases",
            ),
            SurfaceRule(
                id="item-db-name-filter-alias",
                file="src/Classes/ItemDBControl.lua",
                required=(
                    "GetLocalizedItemSearchText and GetLocalizedItemSearchText(item)",
                    "escapeSearchPattern(self.controls.search.buf)",
                    "itemSearchText(item):lower()",
                ),
                message="Item database name filter must search localized item aliases from item objects",
            ),
            SurfaceRule(
                id="gem-select-name-filter-alias",
                file="src/Classes/GemSelectControl.lua",
                required=(
                    'GetLocalizedSearchAliases("skills", text)',
                    'self.EditControl(anchor, rect, nil, nil, "%c")',
                    "skillNameMatches(gemData, pattern)",
                    "escapeSearchPattern(searchTerm)",
                ),
                message="Gem select name filter must accept Unicode input and search localized skill aliases",
            ),
        )

    def run(self) -> list[Finding]:
        findings: list[Finding] = []
        for rule in self.rules:
            finding = rule.check(self.root)
            if finding:
                findings.append(finding)
        return findings


class Report:
    def __init__(self, findings: Iterable[Finding]) -> None:
        self.findings = list(findings)

    def to_json(self) -> str:
        payload = {
            "open": len(self.findings),
            "findings": [finding.__dict__ for finding in self.findings],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def to_text(self) -> str:
        if not self.findings:
            return "i18n input/search gate: PASS"
        lines = ["i18n input/search gate: FAIL"]
        for finding in self.findings:
            lines.append(f"- {finding.id}: {finding.file}: {finding.message}")
        return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="PoB worktree root")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    auditor = I18nInputSearchAuditor(Path(args.root).resolve())
    report = Report(auditor.run())
    if args.format == "json":
        print(report.to_json())
    else:
        print(report.to_text())
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
