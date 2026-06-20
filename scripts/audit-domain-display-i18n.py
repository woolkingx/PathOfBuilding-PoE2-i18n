#!/usr/bin/env python3
"""Audit and track display-boundary domain i18n work.

This is a reusable work-queue helper, not an automatic fixer. It scans
UI/display sinks, reports lines that appear to use raw item/skill/stat data,
and maintains a small state file so repeated runs show new, open, ignored,
deferred, and resolved candidates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditConfig:
    root: Path
    output: Path | None
    state_path: Path
    update_state: bool
    suggestions: int
    domains: set[str] | None
    statuses: set[str] | None
    output_format: str
    list_ids: bool
    marks: list[str]
    fail_on_candidates: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "AuditConfig":
        root = args.root.resolve()
        output = args.output
        if output and not output.is_absolute():
            output = root / output
        state_path = args.state
        if not state_path.is_absolute():
            state_path = root / state_path
        return cls(
            root=root,
            output=output,
            state_path=state_path,
            update_state=args.update_state,
            suggestions=args.suggestions,
            domains=set(args.domain) if args.domain else None,
            statuses=set(args.status) if args.status else None,
            output_format=args.format,
            list_ids=args.list_ids,
            marks=args.mark,
            fail_on_candidates=args.fail_on_candidates,
        )


@dataclass(frozen=True)
class Finding:
    category: str
    path: Path
    line_no: int
    text: str
    sink: str

    @property
    def id(self) -> str:
        normalized = re.sub(r"\s+", " ", self.text)
        payload = f"{self.category}\0{self.path}\0{normalized}".encode("utf-8")
        return hashlib.sha1(payload).hexdigest()[:12]

    def row(self, status: str) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": status,
            "category": self.category,
            "sink": self.sink,
            "path": self.path,
            "line": self.line_no,
            "text": self.text,
        }


@dataclass
class AuditState:
    data: dict[str, Any] = field(default_factory=lambda: {"version": 1, "findings": {}})

    @classmethod
    def load(cls, path: Path) -> "AuditState":
        if not path.exists():
            return cls()
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @property
    def records(self) -> dict[str, dict[str, Any]]:
        return self.data.setdefault("findings", {})

    @property
    def last_run(self) -> str | None:
        value = self.data.get("last_run")
        return str(value) if value else None

    def update_from_findings(self, findings: list[Finding]) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        current_ids = {finding.id for finding in findings}
        for finding in findings:
            record = self.records.get(finding.id, {})
            status = record.get("status", "open")
            if status == "resolved":
                status = "open"
            self.records[finding.id] = {
                **record,
                "id": finding.id,
                "status": status,
                "category": finding.category,
                "sink": finding.sink,
                "path": str(finding.path),
                "line": finding.line_no,
                "text": finding.text,
                "first_seen": record.get("first_seen", now),
                "last_seen": now,
                "seen_count": int(record.get("seen_count", 0)) + 1,
            }
        for finding_id, record in self.records.items():
            if finding_id in current_ids:
                continue
            if record.get("status") in {"ignored", "deferred"}:
                continue
            if record.get("status") != "resolved":
                record["status"] = "resolved"
                record["resolved_at"] = now
        self.data["last_run"] = now

    def mark(self, marks: list[str]) -> None:
        if not marks:
            return
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for mark in marks:
            if ":" not in mark:
                raise SystemExit(f"--mark expects ID:status, got {mark!r}")
            finding_id, status = mark.split(":", 1)
            if status not in {"open", "deferred", "ignored", "resolved"}:
                raise SystemExit(f"unsupported status {status!r} for {finding_id}")
            record = self.records.get(finding_id)
            if not record:
                raise SystemExit(f"cannot mark unknown finding id {finding_id!r}; run with --update-state first")
            record["status"] = status
            record["marked_at"] = now

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def status_for(self, finding: Finding) -> str:
        return str(self.records.get(finding.id, {}).get("status", "open"))

    def resolved_count(self) -> int:
        return sum(1 for record in self.records.values() if record.get("status") == "resolved")

    def historical_rows(self, domains: set[str] | None, statuses: set[str] | None, seen_ids: set[str]) -> list[dict[str, Any]]:
        if not statuses:
            return []
        rows: list[dict[str, Any]] = []
        for finding_id, record in self.records.items():
            if finding_id in seen_ids:
                continue
            status = record.get("status", "open")
            category = record.get("category")
            if status not in statuses:
                continue
            if domains and category not in domains:
                continue
            rows.append({
                "id": finding_id,
                "status": status,
                "category": category,
                "sink": record.get("sink", "display"),
                "path": Path(record.get("path", "")),
                "line": record.get("line", 0),
                "text": record.get("text", ""),
            })
        return rows


class DomainDisplayAuditor:
    scan_dirs = ("src/Classes", "src/Modules")
    display_sink_re = re.compile(
        r"("
        r"new\([\"'](?:LabelControl|DropDownControl|ListControl)|"
        r"DrawString\(|"
        r"(?:tooltip|self\.tooltip):AddLine\(|"
        r"Open(?:ConfirmPopup|MessagePopup|Popup)\(|"
        r"\bt_insert\([^,\n]*(?:list|\.list)|"
        r"\b(?:label|sourceLabel|sourceName|tooltipText)\s*=(?!=)|"
        r"\bSetText\(|"
        r"\bSetList\("
        r")"
    )
    raw_patterns = {
        "item": [
            re.compile(r"\b(?:row\.item|item|newItem|sourceItem|sourceSingle|jewel)\.(?:name|baseName|title)\b"),
            re.compile(r"\bitem\.baseName\b"),
        ],
        "skill": [
            re.compile(r"\b(?:activeEffect|grantedEffect|skillEffect\.grantedEffect|minionSkill\.activeEffect\.grantedEffect)\.name\b"),
            re.compile(r"\b(?:gemData|gemInstance\.gemData)\.name\b"),
            re.compile(r"\b(?:gemInstance|srcInstance|skillEffect\.srcInstance)\.nameSpec\b"),
        ],
        "stat": [
            re.compile(r"\bmodLine\.line\b"),
            re.compile(r"\bnode\.sd\b"),
            re.compile(r"\bdesc\.text\b"),
        ],
    }
    translated_markers = {
        "item": ("trItem(", "TranslateItem("),
        "skill": ("trSkill(", "TranslateSkill("),
        "stat": ("trStat(", "TranslateStat(", "formatModLine(", ", true)"),
    }
    ignore_line_re = re.compile(
        r"("
        r"queryTable\.query|"
        r"tradeHelpers\.|"
        r"BuildRaw\(|"
        r"ParseRaw\(|"
        r"FindSkillGem\(|"
        r"itemLib\.wiki|"
        r"ConPrintf\(|"
        r"nameSpec:SetText\("
        r")"
    )
    sink_weights = {
        "popup": 0,
        "label": 1,
        "list": 1,
        "source-label": 1,
        "tooltip": 2,
        "draw": 2,
        "control-update": 3,
        "display": 4,
    }
    category_weights = {"item": 0, "skill": 1, "stat": 2}

    def __init__(self, config: AuditConfig):
        self.config = config
        self.state = AuditState.load(config.state_path)

    def run(self) -> int:
        findings = self.scan()
        self.state.update_from_findings(findings)
        self.state.mark(self.config.marks)
        if self.config.update_state:
            self.state.save(self.config.state_path)
        rows = self.rows_for_report(findings)
        if self.config.output_format == "json":
            self.write_json(rows)
        else:
            self.write_markdown(rows)
        active_rows = [row for row in rows if row["status"] not in {"ignored", "deferred", "resolved"}]
        return 1 if self.config.fail_on_candidates and active_rows else 0

    def scan(self) -> list[Finding]:
        findings: list[Finding] = []
        for scan_dir in self.scan_dirs:
            for path in sorted((self.config.root / scan_dir).rglob("*.lua")):
                findings.extend(self.scan_file(path))
        return findings

    def scan_file(self, path: Path) -> list[Finding]:
        findings: list[Finding] = []
        rel = path.relative_to(self.config.root)
        for line_no, raw_line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            finding = self.finding_for_line(rel, line_no, raw_line)
            if finding:
                findings.append(finding)
        return findings

    def finding_for_line(self, rel: Path, line_no: int, raw_line: str) -> Finding | None:
        line = raw_line.strip()
        if not line or line.startswith("--"):
            return None
        if self.ignore_line_re.search(line):
            return None
        if not self.is_display_sink(line):
            return None
        for category, patterns in self.raw_patterns.items():
            if self.is_translated(category, line):
                continue
            if any(pattern.search(line) for pattern in patterns):
                return Finding(category, rel, line_no, line, self.sink_name(line))
        return None

    def is_display_sink(self, line: str) -> bool:
        return bool(self.display_sink_re.search(line))

    def is_translated(self, category: str, line: str) -> bool:
        if category == "stat" and "formatModLine(" in line:
            return ", true" in line
        return any(marker in line for marker in self.translated_markers[category])

    def sink_name(self, line: str) -> str:
        if "OpenConfirmPopup(" in line or "OpenMessagePopup(" in line or "OpenPopup(" in line:
            return "popup"
        if "DrawString(" in line:
            return "draw"
        if "AddLine(" in line:
            return "tooltip"
        if "sourceLabel" in line or "sourceName" in line:
            return "source-label"
        if "t_insert(" in line and "list" in line:
            return "list"
        if "new(\"LabelControl\"" in line or "new('LabelControl'" in line:
            return "label"
        if "SetText(" in line or "SetList(" in line:
            return "control-update"
        return "display"

    def rows_for_report(self, findings: list[Finding]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for finding in findings:
            status = self.state.status_for(finding)
            if self.config.domains and finding.category not in self.config.domains:
                continue
            if self.config.statuses and status not in self.config.statuses:
                continue
            seen_ids.add(finding.id)
            rows.append(finding.row(status))
        rows.extend(self.state.historical_rows(self.config.domains, self.config.statuses, seen_ids))
        return rows

    def priority(self, row: dict[str, Any]) -> tuple[int, str, str]:
        sink_weight = self.sink_weights.get(str(row["sink"]), 5)
        category_weight = self.category_weights.get(str(row["category"]), 3)
        return sink_weight + category_weight, str(row["path"]), str(row["line"])

    def suggestion(self, row: dict[str, Any]) -> str:
        category = row["category"]
        if category == "item":
            return "display-only: wrap the shown name with trItem/TranslateItem; keep item ids/raw text/query payloads raw"
        if category == "skill":
            return "display-only: wrap the shown name with trSkill/TranslateSkill; keep nameSpec/search/build data raw"
        if category == "stat":
            return "display-only: use trStat/TranslateStat or formatModLine(..., ..., true); keep parser/trade/calculation lines raw"
        return "review display-only boundary"

    def write_json(self, rows: list[dict[str, Any]]) -> None:
        payload = {
            "last_run": self.state.last_run,
            "current_candidates": len(rows),
            "rows": [
                {
                    **row,
                    "path": str(row["path"]),
                }
                for row in rows
            ],
        }
        self.write_output(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def write_markdown(self, rows: list[dict[str, Any]]) -> None:
        lines = [
            "# Domain Display i18n Audit",
            "",
            "This report lists display-sink lines that still appear to use raw item/skill/stat data.",
            "State is keyed by stable finding IDs so repeated runs can track progress.",
            "",
        ]
        if self.state.last_run:
            lines.append(f"- last_run: `{self.state.last_run}`")
        lines.append(f"- current_candidates: `{len(rows)}`")
        lines.append(f"- resolved_total: `{self.state.resolved_count()}`")
        lines.append("")
        self.add_summary(lines, rows)
        self.add_suggestions(lines, rows)
        self.add_ids(lines, rows)
        self.add_all_candidates(lines, rows)
        self.write_output("\n".join(lines) + "\n")

    def add_summary(self, lines: list[str], rows: list[dict[str, Any]]) -> None:
        counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for row in rows:
            counts[row["category"]] = counts.get(row["category"], 0) + 1
            status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        if not counts:
            lines.extend(["No candidates found.", ""])
            return
        lines.extend(["## Summary", ""])
        for category in sorted(counts):
            lines.append(f"- {category}: {counts[category]}")
        for status in sorted(status_counts):
            lines.append(f"- status/{status}: {status_counts[status]}")
        lines.append("")

    def add_suggestions(self, lines: list[str], rows: list[dict[str, Any]]) -> None:
        active_rows = [row for row in rows if row["status"] not in {"ignored", "deferred"}]
        active_rows.sort(key=self.priority)
        if not active_rows:
            return
        lines.extend(["## Suggested Next Work", ""])
        for row in active_rows[: self.config.suggestions]:
            lines.append(f"- `{row['id']}` `{row['category']}` `{row['sink']}` {row['path']}:{row['line']}")
            lines.append(f"  - suggestion: {self.suggestion(row)}")
            lines.append(f"  - line: `{row['text']}`")
        lines.append("")

    def add_ids(self, lines: list[str], rows: list[dict[str, Any]]) -> None:
        if not self.config.list_ids or not rows:
            return
        lines.extend(["## IDs", ""])
        for row in sorted(rows, key=self.priority):
            lines.append(f"- `{row['id']}` {row['status']} {row['category']} {row['path']}:{row['line']}")
        lines.append("")

    def add_all_candidates(self, lines: list[str], rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        lines.extend(["## All Current Candidates", ""])
        for row in sorted(rows, key=self.priority):
            lines.append(f"- `{row['id']}` `{row['status']}` `{row['category']}` `{row['sink']}` {row['path']}:{row['line']}")
            lines.append(f"  `{row['text']}`")

    def write_output(self, text: str) -> None:
        if self.config.output:
            self.config.output.parent.mkdir(parents=True, exist_ok=True)
            self.config.output.write_text(text, encoding="utf-8")
        print(text, end="")


def parse_args() -> AuditConfig:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--state", type=Path, default=Path("work/pob/domain-display-audit-state.json"))
    parser.add_argument("--update-state", action="store_true")
    parser.add_argument("--suggestions", type=int, default=12)
    parser.add_argument("--domain", action="append", choices=("item", "skill", "stat"))
    parser.add_argument("--status", action="append", choices=("open", "deferred", "ignored", "resolved"))
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--list-ids", action="store_true")
    parser.add_argument("--mark", action="append", default=[], metavar="ID:STATUS")
    parser.add_argument("--fail-on-candidates", action="store_true")
    return AuditConfig.from_args(parser.parse_args())


def main() -> int:
    return DomainDisplayAuditor(parse_args()).run()


if __name__ == "__main__":
    raise SystemExit(main())
