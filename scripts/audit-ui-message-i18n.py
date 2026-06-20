#!/usr/bin/env python3
"""Audit likely display strings against the zh_TW UI PO catalog.

This is a gate script, not a translator. It finds source strings that are
already on a display path and reports whether the UI PO catalog is missing,
empty, or still equal to English.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


SCAN_DIRS = ("src/Classes", "src/Modules")
CONFIG_OPTIONS_FILE = "src/Modules/ConfigOptions.lua"
SKIP_FILES = {
    "src/Classes/Item.lua",
    "src/Classes/ModDB.lua",
    "src/Classes/ModList.lua",
    "src/Classes/PoEAPI.lua",
    "src/Classes/TradeQueryGenerator.lua",
    "src/Classes/TradeQueryRequests.lua",
    "src/Modules/BuildDisplayStats.lua",
    "src/Modules/BuildSiteTools.lua",
    "src/Modules/CalcDefence.lua",
    "src/Modules/CalcOffence.lua",
    "src/Modules/CalcSections.lua",
    "src/Modules/CalcSetup.lua",
    "src/Modules/CalcTriggers.lua",
    "src/Modules/Data.lua",
    "src/Modules/DataLegionLookUpTableHelper.lua",
    "src/Modules/Lang.lua",
    "src/Modules/ModParser.lua",
}
CONTROL_CLASSES = {
    "ButtonControl",
    "CheckBoxControl",
    "DropDownControl",
    "EditControl",
    "LabelControl",
    "ListControl",
    "SectionControl",
}
SKIP_STRINGS = CONTROL_CLASSES | {
    "",
    " ",
    "LEFT",
    "RIGHT",
    "CENTER",
    "CENTER_X",
    "CENTER_Y",
    "TOP",
    "TOPLEFT",
    "TOPRIGHT",
    "BOTTOM",
    "BOTTOMLEFT",
    "BOTTOMRIGHT",
    "VAR",
    "VAR BOLD",
    "FIXED",
    "FIXED BOLD",
    "FONTIN SC",
    "FONTIN ITALIC",
    "FONTIN SC ITALIC",
    "cancel",
    "close",
    "confirm",
    "create",
    "edit",
    "enabled",
    "font",
    "height",
    "IPv4",
    "IPv6",
    "label",
    "open",
    "save",
    "tooltip",
    "visible",
    "width",
    "x",
    "y",
    "^x",
}
REVIEWED_RAW = {
    "Abberath's Horn",
    "Distilled",
    "Evasion",
    "Glimpse of Chaos",
    "Goat's Horn",
    "Radius",
    "Rarity: %w+",
    "Scholar's Platinum Kris of Joy",
    "True",
    "Ward",
}

LUA_STRING_RE = re.compile(r"(['\"])(?:\\.|(?!\1).)*\1")
LUA_LONG_STRING_START_RE = re.compile(r"\[(=*)\[")
DISPLAY_FIELD_RE = re.compile(
    r"\b(label|tooltip|tooltipText|inactiveText|defaultText|noMatchesText|"
    r"statusText|stateText|noticeText|detail|title)\s*=\s*"
)
CONFIG_FIELD_RE = re.compile(r"\b(section|label|tooltip|inactiveText)\s*=\s*")
CONTROL_NEW_RE = re.compile(
    r"\bnew\s*\(\s*['\"]("
    + "|".join(sorted(CONTROL_CLASSES))
    + r")['\"]"
)
DISPLAY_CALL_RE = re.compile(
    r"\b(DrawString|AddLine|addTooltipLine|AddStatComparesToTooltip|"
    r"OpenPopup|OpenMessagePopup|OpenConfirmPopup|SetText|SetPlaceholder)\s*\("
)
WORD_RE = re.compile(r"[A-Za-z]")
COLOR_PREFIX_RE = re.compile(r"^(\^(?:x[0-9A-Fa-f]{6}|[0-9]))+")
FORMAT_FRAGMENT_RE = re.compile(r"^[%0-9+\-.,: ]*[cdfgiosuxXqEG][%0-9+\-.,: cdfgiosuxXqEG]*$")
LUA_PATTERN_RE = re.compile(r"[%^$*+?.\[\]-]")
INTERNAL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CAMEL_INTERNAL_RE = re.compile(r"(?:[a-z][A-Z]|[A-Z][a-z]+[A-Z])")
DATA_KEY_RE = re.compile(r"^(?:\d+[A-Za-z]|[A-Za-z]+:[A-Za-z0-9_:]+|\{[^}]+:)")
RAW_FIELD_RE = re.compile(
    r"\b(ifSkill|ifFlag|ifCond|ifOption|ifMod|ifStat|ifEnemyCond|"
    r"flag|var|val|stat|source|apply|protocol|scheme|theme|locale|"
    r"sortMode|sortVal|sortDir|type|base|id|key|name)\s*=\s*$"
)
CONTROL_KEY_FRAGMENT_RE = re.compile(r"controls\s*\[[^\]]*$")
LUA_BLOCK_OPEN_RE = re.compile(r"\b(function|then|do|repeat)\b")
LUA_BLOCK_CLOSE_RE = re.compile(r"\b(end|until)\b")


@dataclass(frozen=True)
class SourceCandidate:
    surface: str
    path: str
    line: int
    msgid: str
    reason: str


@dataclass(frozen=True)
class Finding:
    id: str
    surface: str
    status: str
    domain: str
    path: str
    line: int
    msgid: str
    msgstr: str | None
    reason: str


class PoCatalog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries = self._read_entries(path)

    def translation_status(self, msgid: str) -> tuple[str, str | None]:
        msgstr = self.entries.get(msgid)
        if msgstr is None:
            return "missing", None
        if msgstr == "":
            return "empty", msgstr
        if msgstr == msgid:
            return "same", msgstr
        return "translated", msgstr

    @staticmethod
    def _read_entries(path: Path) -> dict[str, str]:
        entries: dict[str, str] = {}
        msgid: str | None = None
        msgstr = ""
        active: str | None = None
        for raw_line in path.read_text(encoding="utf-8").splitlines() + [""]:
            line = raw_line.strip()
            if line.startswith("msgid "):
                if msgid is not None:
                    entries[msgid] = msgstr
                msgid = decode_lua_string(line[6:].strip())
                msgstr = ""
                active = "msgid"
                continue
            if line.startswith("msgstr ") and msgid is not None:
                msgstr = decode_lua_string(line[7:].strip())
                active = "msgstr"
                continue
            if line.startswith('"') and msgid is not None:
                if active == "msgid":
                    msgid += decode_lua_string(line)
                elif active == "msgstr":
                    msgstr += decode_lua_string(line)
                continue
            if not line and msgid is not None:
                entries[msgid] = msgstr
                msgid = None
                msgstr = ""
                active = None
        return entries


class LuaText:
    @staticmethod
    def decode(token: str) -> str:
        return decode_lua_string(token)

    @staticmethod
    def clean(text: str) -> str:
        return COLOR_PREFIX_RE.sub("", text.strip()).strip()

    @staticmethod
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

    @staticmethod
    def block_delta(line: str) -> int:
        stripped = re.sub(LUA_STRING_RE, '""', LuaText.strip_comment(line))
        opens = len(LUA_BLOCK_OPEN_RE.findall(stripped)) - len(re.findall(r"\belseif\b", stripped))
        return opens - len(LUA_BLOCK_CLOSE_RE.findall(stripped))

    @staticmethod
    def field_value(lines: list[str], line_index: int, start: int) -> tuple[str | None, int]:
        line = lines[line_index]
        pos = start
        while pos < len(line) and line[pos].isspace():
            pos += 1
        string_match = LUA_STRING_RE.match(line, pos)
        if string_match:
            tail = line[string_match.end():].lstrip()
            if tail.startswith(".."):
                return None, line_index
            return LuaText.decode(string_match.group(0)), line_index
        long_match = LUA_LONG_STRING_START_RE.match(line, pos)
        if not long_match:
            return None, line_index
        close = "]" + long_match.group(1) + "]"
        start_pos = long_match.end()
        end = line.find(close, start_pos)
        if end >= 0:
            return line[start_pos:end], line_index
        long_lines = [line[start_pos:]]
        cur_index = line_index + 1
        while cur_index < len(lines):
            next_line = lines[cur_index]
            end = next_line.find(close)
            if end >= 0:
                long_lines.append(next_line[:end])
                return "\n".join(long_lines), cur_index
            long_lines.append(next_line)
            cur_index += 1
        return None, line_index


class CandidatePolicy:
    @staticmethod
    def is_candidate(text: str) -> bool:
        if text in SKIP_STRINGS or text in REVIEWED_RAW:
            return False
        if not WORD_RE.search(text) or len(text) < 2:
            return False
        if FORMAT_FRAGMENT_RE.fullmatch(text) or DATA_KEY_RE.match(text):
            return False
        if text.startswith(("]] ..", "%", "^The", "-", "Metadata/", "Art/", "https://", "http://", "file://")):
            return False
        if text.endswith(("-", ".lua", ".xml", ".png", ".jpg", ".otf", ".ttf")):
            return False
        if "/" in text and not text.startswith("<"):
            return False
        if text.count("%") > 4:
            return False
        if LUA_PATTERN_RE.search(text) and text.count("%") + text.count("[") + text.count("^") >= 2:
            return False
        if INTERNAL_IDENTIFIER_RE.fullmatch(text):
            if text[0].islower() or text.isupper() or CAMEL_INTERNAL_RE.search(text):
                return False
        if text.endswith(("Control", "Tab", "Class", "List", "Lib")) and " " not in text:
            return False
        return True

    @staticmethod
    def skip_string_position(line: str, match: re.Match[str]) -> bool:
        before = line[: match.start()]
        if RAW_FIELD_RE.search(before):
            return True
        if CONTROL_KEY_FRAGMENT_RE.search(before):
            return True
        if re.search(r"\b(?:LoadModule|require|PCall|string\.(?:match|gsub|find)|s_(?:match|gsub|find))\s*\([^)]*$", before):
            return True
        return False

    @staticmethod
    def domain_for(candidate: SourceCandidate) -> str:
        if candidate.path in {"src/Classes/TreeTab.lua", "src/Classes/TimelessJewelListControl.lua"} and candidate.surface == "dropdown-label":
            return "domain-review"
        if candidate.surface in {
            "config-dropdown-label",
            "dropdown-label",
            "display-field",
            "display-call",
            "control-constructor",
            "label-function-body",
        }:
            return "ui"
        return "domain-review"


class LuaDisplayScanner:
    def __init__(self, root: Path, catalog: PoCatalog) -> None:
        self.root = root
        self.catalog = catalog

    def scan(self) -> list[Finding]:
        findings: dict[str, Finding] = {}
        for path in self.iter_files():
            for candidate in self.scan_file(path):
                status, msgstr = self.catalog.translation_status(candidate.msgid)
                if status == "translated":
                    continue
                domain = CandidatePolicy.domain_for(candidate)
                finding = Finding(
                    id=self.finding_id(candidate.path, candidate.line, candidate.surface, candidate.msgid),
                    surface=candidate.surface,
                    status=status,
                    domain=domain,
                    path=candidate.path,
                    line=candidate.line,
                    msgid=candidate.msgid,
                    msgstr=msgstr,
                    reason=candidate.reason,
                )
                findings[finding.id] = finding
        return sorted(findings.values(), key=lambda item: (item.domain, item.path, item.line, item.msgid))

    def iter_files(self) -> list[Path]:
        files: list[Path] = []
        for scan_dir in SCAN_DIRS:
            base = self.root / scan_dir
            if base.exists():
                files.extend(path for path in base.glob("*.lua") if path.is_file())
        return sorted(path for path in files if path.relative_to(self.root).as_posix() not in SKIP_FILES)

    def scan_file(self, path: Path) -> list[SourceCandidate]:
        rel = path.relative_to(self.root).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if rel == CONFIG_OPTIONS_FILE:
            return self.scan_config_options(lines)
        return self.scan_display_file(rel, lines)

    def scan_config_options(self, lines: list[str]) -> list[SourceCandidate]:
        rows: list[SourceCandidate] = []
        in_list = False
        depth = 0
        for index, raw_line in enumerate(lines):
            line = LuaText.strip_comment(raw_line)
            if not line.strip():
                continue
            for match in CONFIG_FIELD_RE.finditer(line):
                field_name = match.group(1)
                raw_msgid, _ = LuaText.field_value(lines, index, match.end())
                self.add_candidate(rows, CONFIG_OPTIONS_FILE, index + 1, f"config-options-{field_name}", "display-field", raw_msgid)
            scan_from = 0
            if re.search(r"\blist\s*=", line):
                in_list = True
                depth = 0
                scan_from = line.find("list")
            elif not in_list:
                continue
            search_line = line[scan_from:]
            for match in re.finditer(r"\blabel\s*=\s*", search_line):
                raw_msgid, _ = LuaText.field_value(lines, index, scan_from + match.end())
                self.add_candidate(
                    rows,
                    CONFIG_OPTIONS_FILE,
                    index + 1,
                    "config-options-dropdown-label",
                    "config-dropdown-label",
                    raw_msgid,
                )
            depth += line.count("{") - line.count("}")
            if in_list and depth <= 0:
                in_list = False
        return rows

    def scan_display_file(self, rel: str, lines: list[str]) -> list[SourceCandidate]:
        rows: list[SourceCandidate] = []
        label_function_depth = 0
        dropdown_depth = 0
        for index, raw_line in enumerate(lines):
            line = LuaText.strip_comment(raw_line)
            if not line.strip():
                continue
            in_label_function = label_function_depth > 0
            in_dropdown = dropdown_depth > 0
            if CONTROL_NEW_RE.search(line):
                self.extract_literals(rows, rel, index + 1, line, "control-constructor")
            if DISPLAY_CALL_RE.search(line):
                self.extract_literals(rows, rel, index + 1, line, "display-call")
            for match in DISPLAY_FIELD_RE.finditer(line):
                raw_msgid, _ = LuaText.field_value(lines, index, match.end())
                surface = "dropdown-label" if in_dropdown and match.group(1) == "label" else "display-field"
                self.add_candidate(rows, rel, index + 1, f"{match.group(1)}-field", surface, raw_msgid)
            if in_label_function:
                self.extract_literals(rows, rel, index + 1, line, "label-function-body")
            elif re.search(r"\blabel\s*=\s*function\s*\(", line):
                label_function_depth = max(0, LuaText.block_delta(line))
            if "DropDownControl" in line:
                dropdown_depth = max(1, line.count("{") - line.count("}"))
            elif in_dropdown:
                dropdown_depth += line.count("{") - line.count("}")
                if dropdown_depth <= 0:
                    dropdown_depth = 0
            if in_label_function and label_function_depth > 0:
                label_function_depth += LuaText.block_delta(line)
                if label_function_depth <= 0:
                    label_function_depth = 0
        return rows

    def extract_literals(self, rows: list[SourceCandidate], rel: str, line_no: int, line: str, surface: str) -> None:
        for match in LUA_STRING_RE.finditer(line):
            if CandidatePolicy.skip_string_position(line, match):
                continue
            self.add_candidate(rows, rel, line_no, surface, surface, LuaText.decode(match.group(0)))

    def add_candidate(
        self,
        rows: list[SourceCandidate],
        rel: str,
        line_no: int,
        reason: str,
        surface: str,
        raw_msgid: str | None,
    ) -> None:
        if raw_msgid is None:
            return
        msgid = LuaText.clean(raw_msgid)
        if not CandidatePolicy.is_candidate(msgid):
            return
        rows.append(SourceCandidate(surface=surface, path=rel, line=line_no, msgid=msgid, reason=reason))

    @staticmethod
    def finding_id(path: str, line: int, surface: str, msgid: str) -> str:
        digest = hashlib.sha1(f"{path}:{line}:{surface}:{msgid}".encode("utf-8")).hexdigest()
        return "UIMSG-" + digest[:10].upper()


class Reporter:
    @staticmethod
    def write(findings: list[Finding], output: Path, fmt: str) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        summary = Reporter.summary(findings)
        if fmt == "json":
            payload = {
                **summary,
                "findings": [finding.__dict__ for finding in findings],
            }
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return
        if fmt == "po":
            lines = [
                "# Review-only UI/message i18n audit candidates.",
                "# Generated by scripts/audit-ui-message-i18n.py.",
                "",
            ]
            for finding in findings:
                lines.append(f"#. {finding.id} {finding.domain} {finding.surface} {finding.status}")
                lines.append(f"#: {finding.path}:{finding.line} {finding.reason}")
                lines.append(f"msgid {Reporter.po_quote(finding.msgid)}")
                lines.append('msgstr ""')
                lines.append("")
            output.write_text("\n".join(lines), encoding="utf-8")
            return
        lines = [
            "# UI/message i18n audit",
            "",
            f"open_count: {summary['open_count']}",
            f"by_domain: {summary['by_domain']}",
            f"by_surface: {summary['by_surface']}",
            f"by_status: {summary['by_status']}",
            "",
        ]
        for finding in findings:
            lines.append(
                f"- {finding.id} `{finding.status}` `{finding.domain}` `{finding.surface}` "
                f"{finding.path}:{finding.line} `{finding.msgid}`"
            )
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def summary(findings: list[Finding]) -> dict[str, object]:
        return {
            "open_count": len(findings),
            "by_domain": dict(sorted(Counter(item.domain for item in findings).items())),
            "by_surface": dict(sorted(Counter(item.surface for item in findings).items())),
            "by_status": dict(sorted(Counter(item.status for item in findings).items())),
        }

    @staticmethod
    def po_quote(text: str) -> str:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def decode_lua_string(token: str) -> str:
    try:
        return ast.literal_eval(token)
    except (SyntaxError, ValueError):
        body = token[1:-1]
        out: list[str] = []
        index = 0
        while index < len(body):
            char = body[index]
            if char != "\\" or index + 1 >= len(body):
                out.append(char)
                index += 1
                continue
            nxt = body[index + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
            index += 2
        return "".join(out)


def filter_findings(findings: list[Finding], args: argparse.Namespace) -> list[Finding]:
    if args.surface:
        allowed = set(args.surface)
        findings = [finding for finding in findings if finding.surface in allowed]
    if args.domain:
        allowed = set(args.domain)
        findings = [finding for finding in findings if finding.domain in allowed]
    if args.status:
        allowed = set(args.status)
        findings = [finding for finding in findings if finding.status in allowed]
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--existing-po", type=Path, default=Path("locale/zh_TW/LC_MESSAGES/pob.po"))
    parser.add_argument("--output", type=Path, default=Path("work/pob/ui-message-audit.md"))
    parser.add_argument("--format", choices=("md", "json", "po"), default="md")
    parser.add_argument("--surface", action="append", help="only include the named surface; can be repeated")
    parser.add_argument("--domain", action="append", choices=("ui", "domain-review"), help="only include the named domain; can be repeated")
    parser.add_argument("--status", action="append", choices=("missing", "empty", "same"), help="only include the named PO status; can be repeated")
    parser.add_argument("--fail-on-open", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    po_path = args.existing_po if args.existing_po.is_absolute() else root / args.existing_po
    output = args.output if args.output.is_absolute() else root / args.output
    findings = LuaDisplayScanner(root, PoCatalog(po_path)).scan()
    findings = filter_findings(findings, args)
    Reporter.write(findings, output, args.format)
    summary = Reporter.summary(findings)
    print(
        f"wrote {summary['open_count']} UI/message findings to {output} "
        f"status={summary['by_status']} surface={summary['by_surface']} domain={summary['by_domain']}"
    )
    if args.fail_on_open and findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
