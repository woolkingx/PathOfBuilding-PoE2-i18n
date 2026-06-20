#!/usr/bin/env python3
"""Extract reviewable UI msgid candidates from PoB Lua interface files."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path


SCAN_DIRS = ("src/Classes", "src/Modules")
CONFIG_OPTIONS_FILE = "src/Modules/ConfigOptions.lua"
SKIP_FILES = {
    "src/Modules/BuildDisplayStats.lua",
    "src/Modules/BuildSiteTools.lua",
    "src/Modules/CalcDefence.lua",
    "src/Modules/CalcOffence.lua",
    "src/Modules/CalcSections.lua",
    "src/Modules/CalcSetup.lua",
    "src/Modules/CalcTriggers.lua",
    CONFIG_OPTIONS_FILE,
    "src/Modules/Data.lua",
    "src/Modules/Lang.lua",
}
CONTROL_CLASSES = {
    "ButtonControl",
    "CheckBoxControl",
    "DropDownControl",
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
    "label",
    "open",
    "save",
    "tooltip",
    "enabled",
    "visible",
    "font",
    "x",
    "y",
    "width",
    "height",
    "^x",
}
REVIEWED_NON_UI_MSGIDS = {
    "Abberath's Horn",
    "Distilled",
    "Evasion",
    "Goat's Horn",
    "Radius",
    "Rarity: %w+",
    "Scholar's Platinum Kris of Joy",
    "True",
    "Ward",
}
CALC_LABEL_FILES = (
    "src/Modules/CalcSections.lua",
    "src/Modules/BuildDisplayStats.lua",
)

LUA_STRING_RE = re.compile(r"(['\"])(?:\\.|(?!\1).)*\1")
LUA_LONG_STRING_START_RE = re.compile(r"\[(=*)\[")
CONFIG_FIELD_RE = re.compile(r"\b(section|label|tooltip|inactiveText)\s*=\s*")
WORD_RE = re.compile(r"[A-Za-z]")
COLOR_PREFIX_RE = re.compile(r"^(\^(?:x[0-9A-Fa-f]{6}|[0-9]))+")
FORMAT_FRAGMENT_RE = re.compile(r"^[%0-9+\-.,: ]*[cdfgiosuxXqEG][%0-9+\-.,: cdfgiosuxXqEG]*$")
INTERNAL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CAMEL_INTERNAL_RE = re.compile(r"(?:[a-z][A-Z]|[A-Z][a-z]+[A-Z])")
DATA_KEY_RE = re.compile(r"^(?:\d+[A-Za-z]|[A-Za-z]+:[A-Za-z0-9_:]+|\{[^}]+:)")
CONTROL_KEY_FRAGMENT_RE = re.compile(r"controls\s*\[[^\]]*$")
LUA_BLOCK_OPEN_RE = re.compile(r"\b(function|then|do|repeat)\b")
LUA_BLOCK_CLOSE_RE = re.compile(r"\b(end|until)\b")


@dataclass
class Candidate:
    msgid: str
    refs: set[tuple[str, int, str]] = field(default_factory=set)


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


def existing_msgids(path: Path | None) -> set[str]:
    if not path or not path.exists():
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


def existing_entries(path: Path | None) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    entries: dict[str, str] = {}
    active_field: str | None = None
    msgid: str | None = None
    msgstr = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("msgid "):
            if msgid:
                entries[msgid] = msgstr
            msgid = decode_lua_string(line[6:].strip())
            msgstr = ""
            active_field = "msgid"
            continue
        if line.startswith("msgstr ") and msgid is not None:
            msgstr = decode_lua_string(line[7:].strip())
            active_field = "msgstr"
            continue
        if line.startswith('"') and msgid is not None:
            if active_field == "msgid":
                msgid += decode_lua_string(line)
            elif active_field == "msgstr":
                msgstr += decode_lua_string(line)
            continue
        if not line and msgid:
            entries[msgid] = msgstr
            msgid = None
            msgstr = ""
            active_field = None
    if msgid:
        entries[msgid] = msgstr
    return entries


def strip_color_prefix(text: str) -> str:
    return COLOR_PREFIX_RE.sub("", text.strip()).strip()


def classify_line(line: str, include_tooltips: bool = False) -> str | None:
    if "TranslateUI(" in line:
        return "translate-ui"
    if any(f'new("{name}"' in line or f"new('{name}'" in line for name in CONTROL_CLASSES):
        return "control-constructor"
    if re.search(r"\blabel\s*=", line):
        return "label-field"
    if re.search(r"\b(defaultText|noMatchesText)\s*=", line):
        return "control-default-text"
    if re.search(r"\bSet(?:Placeholder|Text)\s*\(", line):
        return "control-set-text"
    if re.search(r"\b(?:stateText|statusText|noticeText)\s*=", line):
        return "status-text"
    if re.search(r"\bOpen(?:Popup|ConfirmPopup|MessagePopup)\s*\(", line):
        return "popup"
    if "DrawString(" in line:
        return "draw-string"
    if include_tooltips and re.search(r"\btooltipText\s*=", line):
        return "tooltip-text"
    if include_tooltips and "AddLine(" in line:
        return "tooltip-line"
    if include_tooltips and "addTooltipLine(" in line:
        return "tooltip-helper-line"
    if include_tooltips and "AddStatComparesToTooltip(" in line:
        return "stat-compare-tooltip-header"
    return None


def is_candidate(text: str) -> bool:
    if text in SKIP_STRINGS:
        return False
    if text in REVIEWED_NON_UI_MSGIDS:
        return False
    if FORMAT_FRAGMENT_RE.fullmatch(text):
        return False
    if DATA_KEY_RE.match(text):
        return False
    if text.startswith(("]] ..", "%^", "^The", "-")) or text.endswith("-"):
        return False
    if text.startswith("%"):
        return False
    if INTERNAL_IDENTIFIER_RE.fullmatch(text):
        if text[0].islower() or text.isupper() or CAMEL_INTERNAL_RE.search(text):
            return False
    if not WORD_RE.search(text):
        return False
    if len(text.strip()) < 2:
        return False
    if text.startswith(("Metadata/", "Art/", "https://", "http://")):
        return False
    if "/" in text and not text.startswith("<"):
        return False
    if text.endswith((".lua", ".xml", ".png", ".jpg", ".otf", ".ttf")):
        return False
    if text.count("%") > 4:
        return False
    return True


def is_config_options_candidate(text: str) -> bool:
    if text in SKIP_STRINGS:
        return False
    if text in REVIEWED_NON_UI_MSGIDS:
        return False
    if FORMAT_FRAGMENT_RE.fullmatch(text):
        return False
    if text.startswith(("]] ..", "%^", "^The", "-")) or text.endswith("-"):
        return False
    if text.startswith("%"):
        return False
    if not WORD_RE.search(text):
        return False
    if len(text.strip()) < 2:
        return False
    if text.startswith(("Metadata/", "Art/", "https://", "http://")):
        return False
    if "/" in text and not text.startswith("<"):
        return False
    if text.endswith((".lua", ".xml", ".png", ".jpg", ".otf", ".ttf")):
        return False
    if text.count("%") > 4:
        return False
    return True


def is_control_key_fragment(line: str, start: int) -> bool:
    before = line[:start]
    return bool(CONTROL_KEY_FRAGMENT_RE.search(before))


def lua_block_delta(line: str) -> int:
    line = re.sub(LUA_STRING_RE, '""', line)
    line = re.sub(r"--.*$", "", line)
    opens = len(LUA_BLOCK_OPEN_RE.findall(line)) - len(re.findall(r"\belseif\b", line))
    return opens - len(LUA_BLOCK_CLOSE_RE.findall(line))


def iter_lua_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for scan_dir in SCAN_DIRS:
        base = root / scan_dir
        if not base.exists():
            continue
        files.extend(path for path in base.rglob("*.lua") if path.is_file())
    return sorted(path for path in files if path.relative_to(root).as_posix() not in SKIP_FILES)


def collect_candidates(root: Path, known: set[str], include_tooltips: bool = False) -> dict[str, Candidate]:
    candidates: dict[str, Candidate] = {}
    known_normalized = known | {strip_color_prefix(msgid) for msgid in known}
    for path in iter_lua_files(root):
        rel = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        line_index = 0
        label_function_depth = 0
        while line_index < len(lines):
            line_no = line_index + 1
            line = lines[line_index]
            line_index += 1
            if line.lstrip().startswith("--"):
                continue
            in_label_function = label_function_depth > 0
            reason = "label-function-body" if in_label_function else classify_line(line, include_tooltips)
            if not in_label_function and re.search(r"\blabel\s*=\s*function\s*\(", line):
                label_function_depth = lua_block_delta(line)
            if not reason:
                continue
            raw_msgids: list[str] = []
            long_match = LUA_LONG_STRING_START_RE.search(line)
            if long_match:
                close = "]" + long_match.group(1) + "]"
                start = long_match.end()
                end = line.find(close, start)
                if end >= 0:
                    raw_msgids.append(line[start:end])
                else:
                    long_lines = [line[start:]]
                    while line_index < len(lines):
                        next_line = lines[line_index]
                        line_index += 1
                        end = next_line.find(close)
                        if end >= 0:
                            long_lines.append(next_line[:end])
                            break
                        long_lines.append(next_line)
                    raw_msgids.append("\n".join(long_lines))
            else:
                for match in LUA_STRING_RE.finditer(line):
                    if is_control_key_fragment(line, match.start()):
                        continue
                    raw_msgids.append(decode_lua_string(match.group(0)))

            for raw_msgid in raw_msgids:
                msgid = strip_color_prefix(raw_msgid)
                if msgid in known_normalized or not is_candidate(msgid):
                    continue
                candidates.setdefault(msgid, Candidate(msgid)).refs.add((rel, line_no, reason))
            if in_label_function:
                label_function_depth += lua_block_delta(line)
    return dict(sorted(candidates.items(), key=lambda item: item[0].lower()))


def extract_config_field_value(lines: list[str], line_index: int, start: int) -> tuple[str | None, int]:
    line = lines[line_index]
    pos = start
    while pos < len(line) and line[pos].isspace():
        pos += 1
    string_match = LUA_STRING_RE.match(line, pos)
    if string_match:
        tail = line[string_match.end():].lstrip()
        if tail.startswith(".."):
            return None, line_index
        return decode_lua_string(string_match.group(0)), line_index
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


def collect_config_options_candidates(root: Path, known: set[str]) -> dict[str, Candidate]:
    candidates: dict[str, Candidate] = {}
    known_normalized = known | {strip_color_prefix(msgid) for msgid in known}
    path = root / CONFIG_OPTIONS_FILE
    if not path.exists():
        return candidates
    rel = CONFIG_OPTIONS_FILE
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line_index, line in enumerate(lines):
        if line.lstrip().startswith("--"):
            continue
        for match in CONFIG_FIELD_RE.finditer(line):
            field_name = match.group(1)
            raw_msgid, end_index = extract_config_field_value(lines, line_index, match.end())
            if raw_msgid is None:
                continue
            msgid = strip_color_prefix(raw_msgid.strip())
            if msgid in known_normalized or not is_config_options_candidate(msgid):
                continue
            reason = f"config-options-{field_name}"
            candidates.setdefault(msgid, Candidate(msgid)).refs.add((rel, line_index + 1, reason))
            line_index = end_index
    return dict(sorted(candidates.items(), key=lambda item: item[0].lower()))


def collect_config_options_dropdown_candidates(root: Path, entries: dict[str, str]) -> dict[str, Candidate]:
    candidates: dict[str, Candidate] = {}
    translated = {
        msgid for msgid, msgstr in entries.items()
        if msgstr and msgstr != msgid
    }
    translated_normalized = translated | {strip_color_prefix(msgid) for msgid in translated}
    path = root / CONFIG_OPTIONS_FILE
    if not path.exists():
        return candidates
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_list = False
    depth = 0
    for line_index, line in enumerate(lines):
        if line.lstrip().startswith("--"):
            continue
        scan_from = 0
        if re.search(r"\blist\s*=", line):
            in_list = True
            scan_from = line.find("list")
            depth = 0
        elif not in_list:
            continue
        search_line = line[scan_from:]
        for match in re.finditer(r"\blabel\s*=\s*", search_line):
            raw_msgid, _ = extract_config_field_value(lines, line_index, scan_from + match.end())
            if raw_msgid is None:
                continue
            msgid = strip_color_prefix(raw_msgid.strip())
            if msgid in translated_normalized or not is_config_options_candidate(msgid):
                continue
            candidates.setdefault(msgid, Candidate(msgid)).refs.add(
                (CONFIG_OPTIONS_FILE, line_index + 1, "config-options-dropdown-label")
            )
        depth += line.count("{") - line.count("}")
        if in_list and depth <= 0:
            in_list = False
    return dict(sorted(candidates.items(), key=lambda item: item[0].lower()))


def collect_calc_label_candidates(root: Path, known: set[str]) -> dict[str, Candidate]:
    candidates: dict[str, Candidate] = {}
    known_normalized = known | {strip_color_prefix(msgid) for msgid in known}
    label_re = re.compile(r"\blabel\s*=\s*(['\"])(.*?)(?<!\\)\1")
    for rel in CALC_LABEL_FILES:
        path = root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in label_re.finditer(text):
            msgid = decode_lua_string(match.group(1) + match.group(2) + match.group(1))
            if msgid in known_normalized:
                continue
            if msgid in SKIP_STRINGS or not WORD_RE.search(msgid) or len(msgid.strip()) < 2:
                continue
            line_no = text[:match.start()].count("\n") + 1
            candidates.setdefault(msgid, Candidate(msgid)).refs.add((rel, line_no, "calc-label"))
    return dict(sorted(candidates.items(), key=lambda item: item[0].lower()))


def append_missing_msgids(candidates: dict[str, Candidate], po_path: Path) -> int:
    existing = existing_msgids(po_path)
    missing = [candidate for msgid, candidate in candidates.items() if msgid not in existing]
    if not missing:
        return 0
    lines = [po_path.read_text(encoding="utf-8").rstrip(), ""]
    for candidate in missing:
        for rel, line_no, reason in sorted(candidate.refs):
            lines.append(f"#: {rel}:{line_no} {reason}")
        lines.append(f"msgid {po_quote(candidate.msgid)}")
        lines.append('msgstr ""')
        lines.append("")
    po_path.write_text("\n".join(lines), encoding="utf-8")
    return len(missing)


def write_po(candidates: dict[str, Candidate], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Review-only UI msgid candidates.",
        "# Generated by scripts/extract-ui-msgids.py; merge into locale/*.po after review.",
        "",
    ]
    for candidate in candidates.values():
        for rel, line_no, reason in sorted(candidate.refs):
            lines.append(f"#: {rel}:{line_no} {reason}")
        lines.append(f"msgid {po_quote(candidate.msgid)}")
        lines.append('msgstr ""')
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--existing-po", type=Path, default=Path("locale/zh_TW/LC_MESSAGES/pob.po"))
    parser.add_argument("--output", type=Path, default=Path("work/pob/ui-msgids-candidates.po"))
    parser.add_argument("--include-tooltips", action="store_true", help="also scan Tooltip:AddLine display strings for review")
    parser.add_argument("--include-config-options", action="store_true", help="also scan ConfigOptions.lua field values rendered by ConfigTab")
    parser.add_argument("--append-missing-to", type=Path, help="append missing msgids to an existing PO while preserving translations")
    args = parser.parse_args()

    root = args.root.resolve()
    existing_po = root / args.existing_po if not args.existing_po.is_absolute() else args.existing_po
    known = existing_msgids(existing_po)
    entries = existing_entries(existing_po)
    candidates = collect_candidates(root, known, args.include_tooltips)
    candidates.update(collect_calc_label_candidates(root, known))
    if args.include_config_options:
        candidates.update(collect_config_options_candidates(root, known))
        candidates.update(collect_config_options_dropdown_candidates(root, entries))
        candidates = dict(sorted(candidates.items(), key=lambda item: item[0].lower()))
    output = root / args.output if not args.output.is_absolute() else args.output
    write_po(candidates, output)
    print(f"wrote {len(candidates)} candidate msgids to {output}")
    if args.append_missing_to:
        append_target = root / args.append_missing_to if not args.append_missing_to.is_absolute() else args.append_missing_to
        appended = append_missing_msgids(candidates, append_target)
        print(f"appended {appended} missing msgids to {append_target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
