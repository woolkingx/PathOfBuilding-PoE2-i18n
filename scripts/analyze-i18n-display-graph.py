#!/usr/bin/env python3
"""Build a static graph for dropdown display i18n routing.

The graph links:

    dropdown control -> list source -> label msgid -> translator route -> PO status

It is intentionally conservative. It reports display risks for labels that are
raw and not linked to a dropdown render path. Raw labels that feed
DropDownControl are treated as routed because DropDownControl translates labels
at draw/search time.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


SCAN_DIRS = ("src/Classes", "src/Modules")
SKIP_FILES = {
    "src/Classes/Item.lua",
    "src/Classes/ModDB.lua",
    "src/Classes/ModList.lua",
    "src/Modules/BuildDisplayStats.lua",
    "src/Modules/CalcDefence.lua",
    "src/Modules/CalcOffence.lua",
    "src/Modules/CalcSections.lua",
    "src/Modules/CalcSetup.lua",
    "src/Modules/CalcTriggers.lua",
    "src/Modules/Data.lua",
    "src/Modules/Lang.lua",
    "src/Modules/ModParser.lua",
}

LUA_STRING_RE = re.compile(r"(['\"])(?:\\.|(?!\1).)*\1")
TABLE_START_RE = re.compile(r"^\s*(?:local\s+)?([\w.:\[\]\"']+)\s*=\s*\{\s*(?:--.*)?$")
LABEL_RE = re.compile(
    r"\blabel\s*=\s*"
    r"(?:(?P<func>[\w.:]+)\s*\(\s*)?"
    r"(?P<string>\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*')"
)
INLINE_DROPDOWN_RE = re.compile(r"new\s*\(\s*['\"]DropDownControl['\"]")
TRANSLATOR_NAMES = {
    "tr": "ui",
    "ui": "ui",
    "translateUI": "ui",
    "TranslateUI": "ui",
    "formatUI": "ui-format",
    "FormatUI": "ui-format",
    "lang:Pob": "ui",
    "trItem": "items",
    "TranslateItem": "items",
    "trSkill": "skills",
    "TranslateSkill": "skills",
    "trStat": "stats",
    "TranslateStat": "stats",
    "trPassive": "passives",
    "TranslatePassive": "passives",
}
COMMON_DISPLAY_TOKENS = {
    "PoE2",
    "IPv4",
    "IPv6",
    "HTTP",
    "SOCKS",
    "SOCKS5H",
    "100%",
    "125%",
    "150%",
    "175%",
    "200%",
    "225%",
    "250%",
}


def lua_unquote(token: str) -> str:
    body = token[1:-1]
    out: list[str] = []
    index = 0
    while index < len(body):
        ch = body[index]
        if ch != "\\" or index + 1 >= len(body):
            out.append(ch)
            index += 1
            continue
        nxt = body[index + 1]
        if nxt == "n":
            out.append("\n")
        elif nxt == "t":
            out.append("\t")
        elif nxt == "r":
            out.append("\r")
        elif nxt in {"\\", "'", '"'}:
            out.append(nxt)
        else:
            out.append(nxt)
        index += 2
    return "".join(out)


def strip_comment(line: str) -> str:
    in_string: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
            continue
        if char in {"'", '"'}:
            in_string = char
            continue
        if char == "-" and index + 1 < len(line) and line[index + 1] == "-":
            return line[:index]
    return line


def brace_delta(line: str) -> int:
    stripped = re.sub(LUA_STRING_RE, '""', strip_comment(line))
    return stripped.count("{") - stripped.count("}")


def compact(text: str, limit: int = 90) -> str:
    text = " ".join(text.strip().split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


@dataclass(frozen=True)
class LabelNode:
    source_id: str
    path: str
    line: int
    msgid: str
    route: str
    raw_expr: str

    def key(self) -> str:
        return f"{self.path}:{self.line}:{self.msgid}"


@dataclass
class ListSource:
    source_id: str
    path: str
    line: int
    kind: str
    expression: str
    labels: list[LabelNode] = field(default_factory=list)


@dataclass(frozen=True)
class DropdownNode:
    control_id: str
    path: str
    line: int
    expression: str
    list_refs: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    severity: str
    risk: str
    path: str
    line: int
    dropdown: str
    source: str
    msgid: str
    route: str
    po_status: str
    msgstr: str | None

    def row(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "risk": self.risk,
            "path": self.path,
            "line": self.line,
            "dropdown": self.dropdown,
            "source": self.source,
            "msgid": self.msgid,
            "route": self.route,
            "po_status": self.po_status,
            "msgstr": self.msgstr,
        }


class PoCatalog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries = self._read(path)

    def status(self, msgid: str) -> tuple[str, str | None]:
        msgstr = self.entries.get(msgid)
        if msgstr is None:
            return "missing", None
        if msgstr == "":
            return "empty", msgstr
        if msgstr == msgid:
            return "same", msgstr
        return "translated", msgstr

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


class LuaScanner:
    def __init__(self, root: Path) -> None:
        self.root = root

    def files(self) -> list[Path]:
        files: list[Path] = []
        for scan_dir in SCAN_DIRS:
            base = self.root / scan_dir
            files.extend(sorted(base.rglob("*.lua")))
        return [path for path in files if path.relative_to(self.root).as_posix() not in SKIP_FILES]

    def scan(self) -> tuple[list[ListSource], list[DropdownNode]]:
        sources: list[ListSource] = []
        dropdowns: list[DropdownNode] = []
        for path in self.files():
            file_sources, file_dropdowns = self._scan_file(path)
            sources.extend(file_sources)
            dropdowns.extend(file_dropdowns)
        return sources, dropdowns

    def _scan_file(self, path: Path) -> tuple[list[ListSource], list[DropdownNode]]:
        rel = path.relative_to(self.root).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        sources: list[ListSource] = []
        dropdowns: list[DropdownNode] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if INLINE_DROPDOWN_RE.search(line):
                block, end_index = self._collect_block(lines, index, paren=True)
                control_id = f"{rel}:{index + 1}"
                inline_source = self._labels_from_block(control_id + ":inline", rel, index + 1, "inline-dropdown", block)
                if inline_source.labels:
                    sources.append(inline_source)
                refs = tuple(self._find_source_refs(block))
                dropdowns.append(DropdownNode(control_id, rel, index + 1, compact(line), refs))
                index = end_index + 1
                continue
            start = TABLE_START_RE.match(line)
            if start:
                block, end_index = self._collect_block(lines, index, paren=False)
                name = start.group(1)
                if "label" in block:
                    source_id = f"{rel}:{name}:{index + 1}"
                    source = self._labels_from_block(source_id, rel, index + 1, "table", block)
                    if source.labels:
                        sources.append(source)
                index = end_index + 1
                continue
            index += 1
        return sources, dropdowns

    def _collect_block(self, lines: list[str], start_index: int, paren: bool) -> tuple[str, int]:
        depth = 0
        chunks: list[str] = []
        for index in range(start_index, len(lines)):
            line = lines[index]
            chunks.append(line)
            depth += brace_delta(line)
            if paren:
                stripped = re.sub(LUA_STRING_RE, '""', strip_comment(line))
                depth += stripped.count("(") - stripped.count(")")
            if index > start_index and depth <= 0:
                return "\n".join(chunks), index
        return "\n".join(chunks), len(lines) - 1

    def _labels_from_block(self, source_id: str, rel: str, start_line: int, kind: str, block: str) -> ListSource:
        labels: list[LabelNode] = []
        for offset, line in enumerate(block.splitlines()):
            match = LABEL_RE.search(line)
            if not match:
                continue
            if line[: match.start()].rstrip().endswith("."):
                continue
            msgid = lua_unquote(match.group("string"))
            func = match.group("func")
            route = TRANSLATOR_NAMES.get(func or "", "raw")
            labels.append(LabelNode(source_id, rel, start_line + offset, msgid, route, compact(line)))
        return ListSource(source_id, rel, start_line, kind, compact(block.splitlines()[0]), labels)

    def _find_source_refs(self, block: str) -> list[str]:
        return sorted(set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", block)))


class DropdownGraph:
    def __init__(
        self,
        sources: list[ListSource],
        dropdowns: list[DropdownNode],
        catalog: PoCatalog,
        include_common_tokens: bool = False,
    ) -> None:
        self.sources = sources
        self.dropdowns = dropdowns
        self.catalog = catalog
        self.include_common_tokens = include_common_tokens
        self.sources_by_ref = self._index_sources(sources)

    @staticmethod
    def _index_sources(sources: list[ListSource]) -> dict[str, list[ListSource]]:
        index: dict[str, list[ListSource]] = {}
        for source in sources:
            parts = source.source_id.split(":")
            name = parts[-2] if len(parts) >= 3 else source.source_id
            index.setdefault(name.split(".")[-1], []).append(source)
            if source.kind == "inline-dropdown":
                index.setdefault(source.source_id, []).append(source)
        return index

    def findings(self) -> list[Finding]:
        rows: list[Finding] = []
        dropdown_by_inline_source = {d.control_id + ":inline": d for d in self.dropdowns}
        for source in self.sources:
            linked = self._linked_dropdowns(source, dropdown_by_inline_source)
            if not linked and source.kind != "inline-dropdown":
                continue
            for label in source.labels:
                if not self.include_common_tokens and label.msgid in COMMON_DISPLAY_TOKENS:
                    continue
                po_status, msgstr = self.catalog.status(label.msgid)
                route = self._effective_route(label.route, linked)
                severity, risk = self._risk(route, po_status)
                if severity == "ok":
                    continue
                dropdown_label = ", ".join(d.control_id for d in linked) or "(list source not linked)"
                rows.append(
                    Finding(
                        severity,
                        risk,
                        label.path,
                        label.line,
                        dropdown_label,
                        source.source_id,
                        label.msgid,
                        route,
                        po_status,
                        msgstr,
                    )
                )
        return sorted(rows, key=lambda row: (self._severity_order(row.severity), row.path, row.line, row.msgid))

    def _linked_dropdowns(self, source: ListSource, inline_map: dict[str, DropdownNode]) -> list[DropdownNode]:
        if source.kind == "inline-dropdown":
            dropdown = inline_map.get(source.source_id)
            return [dropdown] if dropdown else []
        name = source.source_id.split(":")[-2].split(".")[-1]
        return [dropdown for dropdown in self.dropdowns if name in dropdown.list_refs]

    @staticmethod
    def _effective_route(source_route: str, linked_dropdowns: list[DropdownNode]) -> str:
        if source_route != "raw":
            return source_route
        if linked_dropdowns:
            return "dropdown-render-ui"
        return source_route

    @staticmethod
    def _risk(route: str, po_status: str) -> tuple[str, str]:
        if route != "raw":
            if po_status == "missing":
                return "medium", "routed label has no UI PO entry"
            if po_status in {"empty", "same"}:
                return "medium", "routed label has untranslated UI PO entry"
            return "ok", "translated route"
        if po_status == "translated":
            return "high", "PO translation exists but dropdown label is not routed"
        if po_status in {"empty", "same"}:
            return "high", "dropdown label is raw and PO entry is untranslated"
        return "medium", "dropdown label is raw and missing from UI PO"

    @staticmethod
    def _severity_order(severity: str) -> int:
        return {"high": 0, "medium": 1, "low": 2, "ok": 3}.get(severity, 9)

    def graph_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        dropdown_by_inline_source = {d.control_id + ":inline": d for d in self.dropdowns}
        for source in self.sources:
            linked = self._linked_dropdowns(source, dropdown_by_inline_source)
            for label in source.labels:
                po_status, msgstr = self.catalog.status(label.msgid)
                route = self._effective_route(label.route, linked)
                severity, risk = self._risk(route, po_status)
                rows.append({
                    "source": source.source_id,
                    "source_kind": source.kind,
                    "dropdowns": [dropdown.control_id for dropdown in linked],
                    "path": label.path,
                    "line": label.line,
                    "msgid": label.msgid,
                    "source_route": label.route,
                    "effective_route": route,
                    "po_status": po_status,
                    "msgstr": msgstr,
                    "common_token": label.msgid in COMMON_DISPLAY_TOKENS,
                    "severity": severity,
                    "risk": risk,
                })
        return rows


class Reporter:
    def __init__(self, graph: DropdownGraph) -> None:
        self.graph = graph

    def json(self) -> str:
        findings = self.graph.findings()
        return json.dumps({
            "summary": self._summary(findings),
            "findings": [finding.row() for finding in findings],
            "graph": self.graph.graph_rows(),
        }, ensure_ascii=False, indent=2)

    def markdown(self) -> str:
        findings = self.graph.findings()
        lines = [
            "# Dropdown i18n Display Graph",
            "",
            "## Summary",
            "",
        ]
        summary = self._summary(findings)
        for key in sorted(summary):
            lines.append(f"- {key}: {summary[key]}")
        lines.extend(["", "## Findings", ""])
        if not findings:
            lines.append("No dropdown display i18n findings.")
            return "\n".join(lines) + "\n"
        lines.append("| Severity | Risk | Location | Msgid | PO | Route |")
        lines.append("|---|---|---|---|---|---|")
        for finding in findings:
            location = f"{finding.path}:{finding.line}"
            msgstr = f" -> {finding.msgstr}" if finding.msgstr else ""
            po = f"{finding.po_status}{msgstr}"
            lines.append(
                "| "
                + " | ".join([
                    finding.severity,
                    finding.risk,
                    location,
                    finding.msgid.replace("|", "\\|"),
                    po.replace("|", "\\|"),
                    finding.route,
                ])
                + " |"
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _summary(findings: list[Finding]) -> dict[str, int]:
        summary: dict[str, int] = {"findings": len(findings)}
        for finding in findings:
            summary[f"severity:{finding.severity}"] = summary.get(f"severity:{finding.severity}", 0) + 1
            summary[f"risk:{finding.risk}"] = summary.get(f"risk:{finding.risk}", 0) + 1
        return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--po", type=Path, default=Path("locale/zh_TW/LC_MESSAGES/pob.po"))
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-high", action="store_true")
    parser.add_argument("--include-common-tokens", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    po_path = args.po if args.po.is_absolute() else root / args.po
    catalog = PoCatalog(po_path)
    sources, dropdowns = LuaScanner(root).scan()
    graph = DropdownGraph(sources, dropdowns, catalog, include_common_tokens=args.include_common_tokens)
    reporter = Reporter(graph)
    text = reporter.json() if args.format == "json" else reporter.markdown()

    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(f"wrote dropdown i18n graph to {output}")
    else:
        print(text, end="")

    if args.fail_on_high and any(finding.severity == "high" for finding in graph.findings()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
