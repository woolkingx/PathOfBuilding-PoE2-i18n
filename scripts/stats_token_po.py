#!/usr/bin/env python3
"""Token PO extraction and composition for zh_TW stats translation.

Pipeline:
  stats.po -> po-token-ast/token catalog -> token-terms.po
  translated token-terms.po -> review-only stats candidate PO

This script only writes work/pob artifacts. It never modifies canonical stats.po
or generated runtime Lua.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"(\{[^}]*\}|[+-]?\d+(?:\.\d+)?%?|[A-Za-z][A-Za-z0-9']*|\n|\s+|.)")
PLACEHOLDER_RE = re.compile(r"\{[^}]*\}")
NUMBER_RE = re.compile(r"[+-]?\d+(?:\.\d+)?%?")

TOKEN_CLASSES: dict[str, set[str]] = {
    "operator": {
        "add", "adds", "additional", "gain", "gained", "gains", "grant", "granted",
        "grants", "increased", "less", "lose", "loses", "more", "reduced", "recover",
        "regenerate", "take", "takes",
    },
    "damage_type": {"chaos", "cold", "elemental", "fire", "lightning", "physical"},
    "resource": {
        "armour", "charge", "charges", "energy", "evasion", "glory", "life", "mana",
        "rage", "shield", "spirit", "ward",
    },
    "actor": {
        "allies", "area", "enemy", "enemies", "minion", "minions", "monster",
        "monsters", "player", "players", "skill", "skills", "you", "your",
    },
    "mechanic": {
        "ailment", "attack", "bleeding", "block", "cast", "critical", "curse",
        "damage", "duration", "freeze", "hit", "hits", "poison", "projectile",
        "projectiles", "resistance", "speed", "spell",
    },
    "condition": {"during", "if", "on", "recently", "when", "while", "with", "without"},
    "unit": {"metre", "metres", "second", "seconds"},
    "connector": {"and", "as", "by", "for", "from", "in", "of", "per", "than", "the", "to", "up"},
}

AMBIGUOUS_SINGLE_WORDS = {
    "a",
    "an",
    "are",
    "as",
    "at",
    "by",
    "charge",
    "fire",
    "for",
    "from",
    "has",
    "have",
    "if",
    "in",
    "is",
    "of",
    "on",
    "per",
    "power",
    "rate",
    "rating",
    "the",
    "to",
    "up",
    "when",
    "while",
    "with",
}


def po_unquote(text: str) -> str:
    return ast.literal_eval(text)


def po_quote(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def po_comment(text: str) -> list[str]:
    safe = text.replace("\r\n", "\n").replace("\r", "\n")
    return [line for line in safe.split("\n") if line]


def token_class(word: str) -> str:
    for name, words in TOKEN_CLASSES.items():
        if word in words:
            return name
    return "word"


def phrase_class(phrase: str) -> str:
    classes = {token_class(word) for word in phrase.split()}
    if len(classes) == 1:
        return next(iter(classes))
    return "mixed"


def placeholder_set(text: str) -> set[str]:
    return set(PLACEHOLDER_RE.findall(text))


@dataclass
class TokenTerm:
    phrase: str
    cls: str
    source_kinds: set[str] = field(default_factory=set)
    frequency: int = 0
    votes: int = 0
    learned_zh: Counter[str] = field(default_factory=Counter)
    examples: list[str] = field(default_factory=list)

    def merge(self, source_kind: str, frequency: int = 0, votes: int = 0, zh: str = "", examples: list[str] | None = None) -> None:
        self.source_kinds.add(source_kind)
        self.frequency = max(self.frequency, frequency)
        self.votes = max(self.votes, votes)
        if zh:
            self.learned_zh[zh] += max(votes, 1)
        if examples:
            for example in examples:
                if example not in self.examples and len(self.examples) < 5:
                    self.examples.append(example)

    def msgctxt(self) -> str:
        source = ",".join(sorted(self.source_kinds))
        return f"class={self.cls};source={source};freq={self.frequency};votes={self.votes}"

    def best_zh(self) -> str:
        return self.learned_zh.most_common(1)[0][0] if self.learned_zh else ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "phrase": self.phrase,
            "class": self.cls,
            "source_kinds": sorted(self.source_kinds),
            "frequency": self.frequency,
            "votes": self.votes,
            "learned_zh": self.learned_zh.most_common(5),
            "examples": self.examples,
        }


@dataclass(frozen=True)
class PoEntry:
    msgid: str
    msgstr: str
    msgctxt: str = ""

    @property
    def identity(self) -> bool:
        return bool(self.msgid) and self.msgstr == self.msgid


class PoReader:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> list[PoEntry]:
        entries: list[PoEntry] = []
        msgctxt: str | None = None
        msgid: str | None = None
        msgstr: str | None = None
        active: str | None = None

        def flush() -> None:
            nonlocal msgctxt, msgid, msgstr, active
            if msgid:
                entries.append(PoEntry(msgid=msgid, msgstr=msgstr or "", msgctxt=msgctxt or ""))
            msgctxt = None
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
            if line.startswith("msgctxt "):
                flush()
                msgctxt = po_unquote(line[8:].strip())
                active = "msgctxt"
                continue
            if line.startswith("msgid "):
                msgid = po_unquote(line[6:].strip())
                active = "msgid"
                continue
            if line.startswith("msgstr "):
                if msgid is None:
                    raise ValueError(f"{self.path}:{line_no}: msgstr before msgid")
                msgstr = po_unquote(line[7:].strip())
                active = "msgstr"
                continue
            if line.startswith('"') and active == "msgctxt":
                msgctxt = (msgctxt or "") + po_unquote(line)
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


class TokenPoExtractor:
    def __init__(self, catalog_path: Path, rules_path: Path, min_frequency: int, min_votes: int, include_learned: bool) -> None:
        self.catalog_path = catalog_path
        self.rules_path = rules_path
        self.min_frequency = min_frequency
        self.min_votes = min_votes
        self.include_learned = include_learned

    def extract(self) -> dict[str, TokenTerm]:
        terms: dict[str, TokenTerm] = {}

        def get_term(phrase: str, cls: str | None = None) -> TokenTerm:
            phrase = " ".join(phrase.lower().split())
            if phrase not in terms:
                terms[phrase] = TokenTerm(phrase=phrase, cls=cls or phrase_class(phrase))
            return terms[phrase]

        catalog = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        for item in catalog.get("phrase_counts", []):
            phrase = " ".join(item.get("phrase", []))
            count = int(item.get("count", 0))
            if phrase and count >= self.min_frequency:
                get_term(phrase).merge("frequent", frequency=count)
        for item in catalog.get("high_frequency_unmapped", []):
            phrase = " ".join(item.get("phrase", []))
            count = int(item.get("count", 0))
            if phrase and count >= self.min_frequency:
                get_term(phrase).merge("unmapped", frequency=count)

        rules = json.loads(self.rules_path.read_text(encoding="utf-8")).get("rules", [])
        for rule in rules:
            phrase = " ".join(rule.get("phrase", []))
            votes = int(rule.get("votes", 0))
            if not phrase or votes < self.min_votes:
                continue
            cls = str(rule.get("class") or phrase_class(phrase))
            term = get_term(phrase, cls=cls)
            zh = str(rule.get("zh", "")) if self.include_learned else ""
            term.merge("learned", votes=votes, zh=zh, examples=rule.get("examples", []))
        return terms

    @staticmethod
    def write_po(path: Path, terms: dict[str, TokenTerm], prefill_learned: bool, batch_size: int, batches_dir: Path | None) -> None:
        sorted_terms = sorted(terms.values(), key=lambda term: (-term.frequency, -term.votes, term.cls, term.phrase))
        TokenPoExtractor._write_po_file(path, sorted_terms, prefill_learned)
        if batches_dir and batch_size > 0:
            batches_dir.mkdir(parents=True, exist_ok=True)
            for index in range(0, len(sorted_terms), batch_size):
                batch = sorted_terms[index:index + batch_size]
                batch_path = batches_dir / f"token-terms-{index // batch_size + 1:03d}.po"
                TokenPoExtractor._write_po_file(batch_path, batch, prefill_learned)

    @staticmethod
    def _write_po_file(path: Path, terms: list[TokenTerm], prefill_learned: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# zh_TW stats token terms.",
            "# Translate msgstr values, then compose review-only stats candidates.",
            "",
        ]
        for term in terms:
            if term.best_zh():
                for comment_line in po_comment(term.best_zh()):
                    lines.append(f"#. learned: {comment_line}")
            for example in term.examples[:3]:
                for comment_line in po_comment(example):
                    lines.append(f"#. example: {comment_line}")
            lines.append(f"msgctxt {po_quote(term.msgctxt())}")
            lines.append(f"msgid {po_quote(term.phrase)}")
            lines.append(f"msgstr {po_quote(term.best_zh() if prefill_learned else '')}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def write_json(path: Path, terms: dict[str, TokenTerm]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        by_class = Counter(term.cls for term in terms.values())
        by_source = Counter(source for term in terms.values() for source in term.source_kinds)
        payload = {
            "term_count": len(terms),
            "by_class": dict(by_class.most_common()),
            "by_source": dict(by_source.most_common()),
            "terms": [term.as_dict() for term in sorted(terms.values(), key=lambda item: item.phrase)],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class TokenPoComposer:
    def __init__(self, stats_po: Path, token_po: Path) -> None:
        self.stats_entries = PoReader(stats_po).read()
        self.token_entries = PoReader(token_po).read()
        self.translation_entries = self._translation_entries()
        self.translations = self._translations()
        self.max_phrase_len = max((len(phrase.split()) for phrase in self.translations), default=1)

    MANUAL_PHRASES = {
        "accuracy rating": "命中值",
        "accuracy rating against unique enemies": "對傳奇敵人的命中值",
        "aura gems": "光環寶石",
        "armour evasion and energy shield from equipped shield": "來自已裝備盾牌的護甲、閃避與能量護盾",
        "attack damage": "攻擊傷害",
        "attack speed": "攻擊速度",
        "bleeding duration": "流血持續時間",
        "bleeding duration on you": "你身上的流血持續時間",
        "block": "格擋",
        "block attack damage": "格擋攻擊傷害",
        "chance to inflict ailments": "施加異常狀態機率",
        "chaos damage": "混沌傷害",
        "chaos resistance": "混沌抗性",
        "cold damage": "冰冷傷害",
        "cold resistance": "冰冷抗性",
        "critical hit chance": "暴擊率",
        "curse gems": "詛咒寶石",
        "damage": "傷害",
        "despair skills": "絕望技能",
        "elemental weakness skills": "元素要害技能",
        "enfeeble skills": "衰弱技能",
        "endurance charge": "耐力球",
        "endurance charges": "耐力球",
        "energy shield": "能量護盾",
        "explosion area of effect": "爆炸範圍效果",
        "explicit elemental damage modifier magnitudes": "明示元素傷害詞綴幅度",
        "fire damage": "火焰傷害",
        "fire resistance": "火焰抗性",
        "flame golem elemental resistances": "火焰魔像元素抗性",
        "flask mana recovery rate": "藥劑魔力恢復率",
        "flasks": "藥劑",
        "frenzy charge": "狂怒球",
        "frenzy charges": "狂怒球",
        "gems": "寶石",
        "grenade duration": "手榴彈持續時間",
        "intelligence requirement": "智慧需求",
        "life": "生命",
        "lightning damage": "閃電傷害",
        "lightning resistance": "閃電抗性",
        "mana": "魔力",
        "mana regeneration rate": "魔力回復率",
        "maximum cold resistances": "最大冰冷抗性",
        "maximum divinity": "最大神性",
        "maximum energy shield": "最大能量護盾",
        "maximum fire resistances": "最大火焰抗性",
        "maximum lightning resistances": "最大閃電抗性",
        "maximum mana": "最大魔力",
        "minions": "召喚物",
        "physical damage": "物理傷害",
        "physical damage taken over time": "承受物理持續傷害",
        "power charge": "暴擊球",
        "power charges": "暴擊球",
        "recovery": "恢復",
        "skeleton duration": "骸骨持續時間",
        "skeleton movement speed": "骸骨移動速度",
        "skills": "技能",
        "socketed aura gems": "插槽中的光環寶石",
        "socketed curse gems": "插槽中的詛咒寶石",
        "socketed elemental gems": "插槽中的元素寶石",
        "socketed gems": "插槽中的寶石",
        "socketed herald gems": "插槽中的捷技能寶石",
        "socketed support gems": "插槽中的輔助寶石",
        "socketed vaal gems": "插槽中的瓦爾寶石",
        "spell damage": "法術傷害",
        "strength and intelligence requirement": "力量與智慧需求",
        "strength requirement": "力量需求",
        "supported skills": "被輔助技能",
        "thorns critical hit chance": "荊棘暴擊率",
        "trap trigger radius": "陷阱觸發範圍",
        "trap trigger area of effect": "陷阱觸發範圍效果",
    }

    @staticmethod
    def _normalize_phrase(phrase: str) -> str:
        return " ".join(phrase.lower().split())

    @staticmethod
    def _context_value(msgctxt: str, key: str) -> str:
        for part in msgctxt.split(";"):
            name, sep, value = part.partition("=")
            if sep and name.strip() == key:
                return value.strip()
        return ""

    def _translation_entries(self) -> dict[str, list[PoEntry]]:
        entries: dict[str, list[PoEntry]] = defaultdict(list)
        for entry in self.token_entries:
            phrase = self._normalize_phrase(entry.msgid)
            if phrase and entry.msgstr and entry.msgstr != entry.msgid:
                entries[phrase].append(entry)
        return dict(entries)

    def _lookup(self, phrase: str, class_hint: str = "") -> str:
        phrase = self._normalize_phrase(phrase)
        entries = self.translation_entries.get(phrase, [])
        if not entries:
            return ""
        if class_hint:
            for entry in entries:
                if self._context_value(entry.msgctxt, "class") == class_hint:
                    return entry.msgstr
        values = {entry.msgstr for entry in entries}
        if len(values) == 1:
            return next(iter(values))
        return ""

    def _zh(self, phrase: str, *class_hints: str) -> str:
        key = self._normalize_phrase(phrase)
        if key in self.MANUAL_PHRASES:
            return self.MANUAL_PHRASES[key]
        for hint in class_hints:
            value = self._lookup(key, hint)
            if value and not re.search(r"[A-Za-z]", value):
                return value
        value = self.translations.get(key, "")
        if value and not re.search(r"[A-Za-z]", value):
            return value
        return ""

    def _translations(self) -> dict[str, str]:
        translations: dict[str, str] = {}
        for phrase, entries in self.translation_entries.items():
            if phrase in AMBIGUOUS_SINGLE_WORDS:
                continue
            values = {entry.msgstr for entry in entries}
            if len(values) != 1:
                continue
            translations[phrase] = next(iter(values))
        return translations

    @staticmethod
    def _tokens(text: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for raw in TOKEN_RE.findall(text):
            if raw.isspace() and raw != "\n":
                continue
            if PLACEHOLDER_RE.fullmatch(raw):
                out.append(("literal", raw))
            elif NUMBER_RE.fullmatch(raw):
                out.append(("literal", raw))
            elif raw == "\n":
                out.append(("literal", raw))
            elif re.fullmatch(r"[A-Za-z][A-Za-z0-9']*", raw):
                out.append(("word", raw.lower()))
            else:
                out.append(("literal", raw))
        return out

    def _render_chance_on_hit(self, msgid: str) -> tuple[str, list[str]] | None:
        action_re = r"(?:inflict Withered|inflict Bleeding|cause Bleeding|Poison|Maim|Shock|Freeze|Ignite)"
        chance_re = r"(?:[+-]?\(\d+(?:\.\d+)?-\d+(?:\.\d+)?\)%?|[+-]?\d+(?:\.\d+)?%?|\{[^}]*\}%?|\{\}%?)"
        patterns = (
            re.compile(rf"^(?P<subject>Minions|Supported Skills) have (?P<chance>{chance_re}) chance to (?P<action>{action_re}) on Hit$", re.IGNORECASE),
            re.compile(rf"^(?P<prefix>Buff grants) (?P<chance>{chance_re}) chance to (?P<action>{action_re}) on Hit$", re.IGNORECASE),
            re.compile(rf"^(?P<chance>{chance_re}) chance to (?P<action>{action_re}) on Hit$", re.IGNORECASE),
        )
        for pattern in patterns:
            match = pattern.fullmatch(msgid)
            if not match:
                continue
            chance = match.group("chance")
            action = self._normalize_phrase(match.group("action"))
            action_zh = self._lookup(action, "verb")
            if not action_zh:
                return None
            used = ["chance to", "on hit", action]
            prefix = ""
            subject = match.groupdict().get("subject")
            if subject:
                subject_key = self._normalize_phrase(subject)
                subject_have_key = subject_key + " have"
                subject_zh = self._lookup(subject_have_key, "actor") or self._lookup(subject_key, "actor")
                if not subject_zh:
                    return None
                prefix = subject_zh[:-1] if subject_zh.endswith("有") else subject_zh
                used.append(subject_have_key if self._lookup(subject_have_key, "actor") else subject_key)
            elif match.groupdict().get("prefix"):
                prefix_key = self._normalize_phrase(match.group("prefix"))
                prefix_zh = self._lookup(prefix_key, "actor")
                if not prefix_zh:
                    return None
                prefix = prefix_zh
                used.append(prefix_key)
            return f"{prefix}擊中時有{chance}機率{action_zh}", sorted(set(used))
        return None

    def _render_while_chance(self, msgid: str) -> tuple[str, list[str]] | None:
        pattern = re.compile(r"^(?P<chance>.+?) Chance to (?P<object>Block Attack Damage) while (?P<condition>Dual Wielding)$", re.IGNORECASE)
        match = pattern.fullmatch(msgid)
        if not match:
            return None
        object_key = self._normalize_phrase(match.group("object"))
        condition_key = "while " + self._normalize_phrase(match.group("condition"))
        object_zh = self._lookup(object_key, "mechanic")
        condition_zh = self._lookup(condition_key, "condition")
        if not object_zh or not condition_zh:
            return None
        chance = match.group("chance")
        return f"{condition_zh}有{chance}機率{object_zh}", sorted({object_key, condition_key})

    def _render_to_maximum(self, msgid: str) -> tuple[str, list[str]] | None:
        pattern = re.compile(r"^(?:(?P<prefix>Buff grants) )?(?P<amount>\{[^}]*\}|[+-]?\d+(?:\.\d+)?)(?P<percent>%?) to maximum (?P<object>.+)$", re.IGNORECASE)
        match = pattern.fullmatch(msgid)
        if not match:
            return None
        object_key = "maximum " + self._normalize_phrase(match.group("object"))
        object_zh = self._zh(object_key, "mechanic", "resource", "word")
        if not object_zh:
            return None
        used = [object_key]
        prefix = ""
        if match.group("prefix"):
            prefix_key = self._normalize_phrase(match.group("prefix"))
            prefix_zh = self._lookup(prefix_key, "actor")
            if not prefix_zh:
                return None
            prefix = prefix_zh
            used.append(prefix_key)
        amount = match.group("amount") + match.group("percent")
        return f"{prefix}{object_zh}{amount}", sorted(set(used))

    def _render_have_to_maximum(self, msgid: str) -> tuple[str, list[str]] | None:
        pattern = re.compile(r"^(?P<subject>Minions|Supported Skills) have (?P<amount>[+-]?\{[^}]*\}%?|[+-]?\d+(?:\.\d+)?%?|\([^)]+\)%?|\{\}%?) to Maximum (?P<object>.+)$", re.IGNORECASE)
        match = pattern.fullmatch(msgid)
        if not match:
            return None
        subject_key = self._normalize_phrase(match.group("subject"))
        object_key = "maximum " + self._normalize_phrase(match.group("object"))
        subject_zh = self._zh(subject_key, "actor")
        object_zh = self._zh(object_key, "mechanic", "resource", "word")
        if not subject_zh or not object_zh:
            return None
        return f"{subject_zh}有{match.group('amount')}{object_zh}", [subject_key, object_key]

    def _render_per_second(self, msgid: str) -> tuple[str, list[str]] | None:
        damage_re = r"(?:Chaos|Cold|Fire|Lightning|Physical)"
        subject_pattern = re.compile(rf"^(?P<subject>Nearby Enemies|Enemies|Monsters) take (?P<amount>.+?) (?P<damage>{damage_re}) Damage per second$", re.IGNORECASE)
        match = subject_pattern.fullmatch(msgid)
        if match:
            subject_key = self._normalize_phrase(match.group("subject"))
            damage_key = self._normalize_phrase(match.group("damage") + " Damage")
            subject_zh = self._lookup(subject_key, "actor")
            damage_zh = self._lookup(damage_key, "damage")
            if not subject_zh or not damage_zh:
                return None
            amount = match.group("amount")
            return f"{subject_zh}每秒承受{amount}{damage_zh}", sorted({subject_key, damage_key, "per second"})

        taken_pattern = re.compile(rf"^(?P<amount>.+?) (?P<damage>{damage_re}) Damage taken per second$", re.IGNORECASE)
        match = taken_pattern.fullmatch(msgid)
        if match:
            damage_key = self._normalize_phrase(match.group("damage") + " Damage")
            damage_zh = self._lookup(damage_key, "damage")
            if not damage_zh:
                return None
            amount = match.group("amount")
            return f"每秒承受{amount}{damage_zh}", sorted({damage_key, "per second"})
        return None

    def _render_level_of(self, msgid: str) -> tuple[str, list[str]] | None:
        pattern = re.compile(r"^(?P<amount>[+-]?\{[^}]*\}|[+-]?\d+(?:\.\d+)?|\([^)]+\)) to Level of (?P<object>.+)$", re.IGNORECASE)
        match = pattern.fullmatch(msgid)
        if not match:
            return None
        object_key = self._normalize_phrase(match.group("object"))
        object_zh = self._zh(object_key, "skill", "mechanic", "word")
        if not object_zh:
            return None
        return f"{object_zh}等級{match.group('amount')}", [object_key, "to level of"]

    def _render_damage_taken_from_hits(self, msgid: str) -> tuple[str, list[str]] | None:
        pattern = re.compile(r"^(?P<amount>[+-]?\{[^}]*\}|[+-]?\d+(?:\.\d+)?|\([^)]+\)) (?P<damage>Chaos|Cold|Fire|Lightning|Physical) Damage taken from Hits(?P<tail>.*)$", re.IGNORECASE)
        match = pattern.fullmatch(msgid)
        if not match:
            return None
        damage_key = self._normalize_phrase(match.group("damage") + " Damage")
        damage_zh = self._zh(damage_key, "damage")
        if not damage_zh:
            return None
        tail = self._normalize_phrase(match.group("tail"))
        suffix = ""
        used = [damage_key, "from hits"]
        if tail == "":
            pass
        elif tail == "by animals":
            suffix = "（來自動物）"
            used.append("by animals")
        elif tail == "per level":
            suffix = "（每等級）"
            used.append("per level")
        else:
            return None
        return f"承受來自擊中的{match.group('amount')}{damage_zh}{suffix}", used

    def _render_charges_on_use(self, msgid: str) -> tuple[str, list[str]] | None:
        pattern = re.compile(r"^Consumes (?P<amount>.+?) (?P<charge>Endurance Charge|Frenzy Charge|Power Charge) on use$", re.IGNORECASE)
        match = pattern.fullmatch(msgid)
        if not match:
            return None
        charge_key = self._normalize_phrase(match.group("charge"))
        charge_zh = self._zh(charge_key, "resource")
        if not charge_zh:
            return None
        return f"使用時消耗{match.group('amount')}{charge_zh}", [charge_key, "on use"]

    def _render_gain_charge_per_second(self, msgid: str) -> tuple[str, list[str]] | None:
        pattern = re.compile(r"^(?:(?P<subject>Flasks) gain|Gain) (?P<amount>.+?) (?P<object>Endurance Charge|Frenzy Charge|Power Charge|charge|charges) per Second(?P<tail>.*)$", re.IGNORECASE)
        match = pattern.fullmatch(msgid)
        if not match:
            return None
        object_key = self._normalize_phrase(match.group("object"))
        object_zh = self._zh(object_key, "resource") or ("充能" if object_key in {"charge", "charges"} else "")
        if not object_zh:
            return None
        prefix = ""
        used = [object_key, "per second"]
        if match.group("subject"):
            subject_key = self._normalize_phrase(match.group("subject"))
            subject_zh = self._zh(subject_key, "actor")
            if not subject_zh:
                return None
            prefix = subject_zh
            used.append(subject_key)
        tail = self._normalize_phrase(match.group("tail"))
        condition = ""
        if tail == "":
            pass
        elif tail == "during effect":
            condition = "效果期間"
            used.append("during effect")
        else:
            return None
        return f"{condition}{prefix}每秒獲得{match.group('amount')}{object_zh}", used

    def _render_basic_have_stat(self, msgid: str) -> tuple[str, list[str]] | None:
        pattern = re.compile(r"^(?P<subject>Minions|Socketed Gems|Supported Skills) have (?P<amount>[+-]?\{[^}]*\}%?|[+-]?\d+(?:\.\d+)?%?|\([^)]+\)%?|\{\}%?) (?P<stat>.+)$", re.IGNORECASE)
        match = pattern.fullmatch(msgid)
        if not match:
            return None
        subject_key = self._normalize_phrase(match.group("subject"))
        stat_key = self._normalize_phrase(match.group("stat"))
        subject_zh = self._zh(subject_key, "actor")
        stat_zh = self._zh(stat_key, "mechanic", "resource", "word")
        if not subject_zh or not stat_zh:
            return None
        return f"{subject_zh}有{match.group('amount')}{stat_zh}", [subject_key, stat_key]

    def _render_increased_reduced_stat(self, msgid: str) -> tuple[str, list[str]] | None:
        pattern = re.compile(r"^(?P<amount>[+-]?\{[^}]*\}%?|\{\}%?|[+-]?\d+(?:\.\d+)?%?|\([^)]+\)%?) (?P<op>increased|reduced) (?P<stat>.+)$", re.IGNORECASE)
        match = pattern.fullmatch(msgid)
        if not match:
            return None
        stat_key = self._normalize_phrase(match.group("stat"))
        stat_zh = self._zh(stat_key, "mechanic", "resource", "word")
        if not stat_zh:
            return None
        op_zh = "增加" if match.group("op").lower() == "increased" else "減少"
        return f"{match.group('amount')}{op_zh}{stat_zh}", [stat_key, match.group("op").lower()]

    def _render_structured(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        for renderer in (
            self._render_chance_on_hit,
            self._render_while_chance,
            self._render_to_maximum,
            self._render_have_to_maximum,
            self._render_per_second,
            self._render_level_of,
            self._render_damage_taken_from_hits,
            self._render_charges_on_use,
            self._render_gain_charge_per_second,
            self._render_basic_have_stat,
            self._render_increased_reduced_stat,
        ):
            rendered = renderer(msgid)
            if rendered:
                msgstr, used = rendered
                return msgstr, used, []
        return None

    def _compose_one(self, msgid: str) -> tuple[str, list[str], list[str]]:
        structured = self._render_structured(msgid)
        if structured:
            return structured
        tokens = self._tokens(msgid)
        out: list[str] = []
        used: list[str] = []
        missing: list[str] = []
        index = 0
        while index < len(tokens):
            kind, value = tokens[index]
            if kind != "word":
                out.append(value)
                index += 1
                continue
            match_phrase = ""
            match_zh = ""
            max_end = min(len(tokens), index + self.max_phrase_len)
            for end in range(max_end, index, -1):
                span = tokens[index:end]
                if any(span_kind != "word" for span_kind, _ in span):
                    continue
                phrase = " ".join(span_value for _, span_value in span)
                if phrase in self.translations:
                    match_phrase = phrase
                    match_zh = self.translations[phrase]
                    break
            if match_phrase:
                out.append(match_zh)
                used.append(match_phrase)
                index += len(match_phrase.split())
            else:
                missing.append(value)
                index += 1
        return "".join(out), sorted(set(used)), sorted(set(missing))

    def compose(self, limit: int | None = None, allow_partial: bool = False, require_phrase: bool = True) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        missing_counter: Counter[str] = Counter()
        skipped = Counter()
        for entry in self.stats_entries:
            if not entry.identity:
                skipped["not_identity"] += 1
                continue
            rendered, used, missing = self._compose_one(entry.msgid)
            if not used:
                skipped["no_translated_token"] += 1
                missing_counter.update(missing)
                continue
            if require_phrase and not any(" " in phrase for phrase in used):
                skipped["no_phrase_rule"] += 1
                missing_counter.update(missing)
                continue
            if missing and not allow_partial:
                skipped["missing_token"] += 1
                missing_counter.update(missing)
                continue
            if rendered == entry.msgid:
                skipped["same_output"] += 1
                continue
            if placeholder_set(rendered) != placeholder_set(entry.msgid):
                skipped["placeholder_drift"] += 1
                continue
            candidates.append(
                {
                    "msgid": entry.msgid,
                    "msgstr": rendered,
                    "used_tokens": used,
                    "missing_tokens": missing,
                    "method": "token-po-compose",
                }
            )
            if limit and len(candidates) >= limit:
                break
        return {
        "token_translation_count": len(self.translations),
            "ambiguous_single_words": sorted(AMBIGUOUS_SINGLE_WORDS),
            "candidate_count": len(candidates),
            "skipped": dict(skipped.most_common()),
            "missing_tokens": dict(missing_counter.most_common(200)),
            "candidates": candidates,
        }

    @staticmethod
    def write_outputs(report: dict[str, Any], json_output: Path, po_output: Path) -> None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = ["# Review-only stats candidates composed from token PO.", ""]
        for item in report["candidates"]:
            lines.append(f"#. method: {item['method']}")
            lines.append(f"#. used_tokens: {', '.join(item['used_tokens'])}")
            if item["missing_tokens"]:
                lines.append(f"#. missing_tokens: {', '.join(item['missing_tokens'])}")
            lines.append(f"msgid {po_quote(item['msgid'])}")
            lines.append(f"msgstr {po_quote(item['msgstr'])}")
            lines.append("")
        po_output.write_text("\n".join(lines), encoding="utf-8")


class TokenPoBatchMerger:
    def __init__(self, base_token_po: Path, batch_glob: str) -> None:
        self.base_entries = PoReader(base_token_po).read()
        self.batch_glob = batch_glob

    def merge(self) -> tuple[list[PoEntry], dict[str, Any]]:
        translations: dict[str, str] = {}
        batch_paths = sorted(Path().glob(self.batch_glob))
        for path in batch_paths:
            for entry in PoReader(path).read():
                phrase = " ".join(entry.msgid.lower().split())
                if phrase and entry.msgstr and entry.msgstr != entry.msgid:
                    translations[phrase] = entry.msgstr

        merged: list[PoEntry] = []
        updated = 0
        for entry in self.base_entries:
            phrase = " ".join(entry.msgid.lower().split())
            msgstr = translations.get(phrase, entry.msgstr)
            if msgstr and msgstr != entry.msgstr:
                updated += 1
            merged.append(PoEntry(msgctxt=entry.msgctxt, msgid=entry.msgid, msgstr=msgstr))
        return merged, {"batch_count": len(batch_paths), "translation_count": len(translations), "updated_count": updated}

    @staticmethod
    def write_po(path: Path, entries: list[PoEntry]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# zh_TW stats token terms merged from translated batches.",
            "",
        ]
        for entry in entries:
            if entry.msgctxt:
                lines.append(f"msgctxt {po_quote(entry.msgctxt)}")
            lines.append(f"msgid {po_quote(entry.msgid)}")
            lines.append(f"msgstr {po_quote(entry.msgstr)}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")


class TokenPoBuilder:
    """Build the full composition token PO from inventory, seeds, and overlay."""

    def __init__(self, inventory_po: Path, seed_po: Path | None, overlay_po: Path | None) -> None:
        self.inventory_po = inventory_po
        self.seed_po = seed_po
        self.overlay_po = overlay_po
        self.inventory_entries = PoReader(inventory_po).read()
        self.seed_entries = PoReader(seed_po).read() if seed_po and seed_po.exists() else []
        self.overlay_entries = PoReader(overlay_po).read() if overlay_po and overlay_po.exists() else []

    @staticmethod
    def _normalize_phrase(phrase: str) -> str:
        return " ".join(phrase.lower().split())

    @staticmethod
    def _context_value(msgctxt: str, key: str) -> str:
        for part in msgctxt.split(";"):
            name, sep, value = part.partition("=")
            if sep and name.strip() == key:
                return value.strip()
        return ""

    @classmethod
    def _entry_key(cls, entry: PoEntry) -> tuple[str, str]:
        return (cls._context_value(entry.msgctxt, "class"), cls._normalize_phrase(entry.msgid))

    @classmethod
    def _phrase_key(cls, entry: PoEntry) -> str:
        return cls._normalize_phrase(entry.msgid)

    @staticmethod
    def _translated(entries: list[PoEntry]) -> list[PoEntry]:
        return [entry for entry in entries if entry.msgstr and entry.msgstr != entry.msgid]

    def _unique_phrase_translations(self, entries: list[PoEntry]) -> dict[str, str]:
        buckets: dict[str, set[str]] = defaultdict(set)
        for entry in self._translated(entries):
            buckets[self._phrase_key(entry)].add(entry.msgstr)
        return {phrase: next(iter(values)) for phrase, values in buckets.items() if len(values) == 1}

    def build(self) -> tuple[list[PoEntry], dict[str, Any]]:
        seed_by_key = {self._entry_key(entry): entry.msgstr for entry in self._translated(self.seed_entries)}
        seed_by_phrase = self._unique_phrase_translations(self.seed_entries)
        overlay_by_key = {self._entry_key(entry): entry.msgstr for entry in self._translated(self.overlay_entries)}
        overlay_by_phrase = self._unique_phrase_translations(self.overlay_entries)

        output: list[PoEntry] = []
        seen_keys: set[tuple[str, str]] = set()
        source_counts = Counter()
        for entry in self.inventory_entries:
            key = self._entry_key(entry)
            phrase = self._phrase_key(entry)
            msgstr = ""
            source = "empty"
            if key in seed_by_key:
                msgstr = seed_by_key[key]
                source = "seed-key"
            elif phrase in seed_by_phrase:
                msgstr = seed_by_phrase[phrase]
                source = "seed-phrase"
            if key in overlay_by_key:
                msgstr = overlay_by_key[key]
                source = "overlay-key"
            elif phrase in overlay_by_phrase:
                msgstr = overlay_by_phrase[phrase]
                source = "overlay-phrase"
            output.append(PoEntry(msgctxt=entry.msgctxt, msgid=entry.msgid, msgstr=msgstr))
            seen_keys.add(key)
            source_counts[source] += 1

        overlay_added = 0
        for entry in self.overlay_entries:
            key = self._entry_key(entry)
            if key in seen_keys:
                continue
            output.append(entry)
            seen_keys.add(key)
            overlay_added += 1

        translated_count = sum(1 for entry in output if entry.msgstr and entry.msgstr != entry.msgid)
        report = {
            "inventory": str(self.inventory_po),
            "seed": str(self.seed_po) if self.seed_po else "",
            "overlay": str(self.overlay_po) if self.overlay_po else "",
            "inventory_count": len(self.inventory_entries),
            "seed_count": len(self.seed_entries),
            "seed_translated_count": len(self._translated(self.seed_entries)),
            "overlay_count": len(self.overlay_entries),
            "overlay_translated_count": len(self._translated(self.overlay_entries)),
            "overlay_added_count": overlay_added,
            "output_count": len(output),
            "translated_count": translated_count,
            "empty_count": len(output) - translated_count,
            "source_counts": dict(source_counts.most_common()),
        }
        return output, report

    @staticmethod
    def write_po(path: Path, entries: list[PoEntry]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# zh_TW stats composition token source.",
            "# Generated from full token inventory plus translated seeds and curated overlay.",
            "# Edit msgstr values here, then run stats_token_po.py compose.",
            "",
        ]
        for entry in entries:
            if entry.msgctxt:
                lines.append(f"msgctxt {po_quote(entry.msgctxt)}")
            lines.append(f"msgid {po_quote(entry.msgid)}")
            lines.append(f"msgstr {po_quote(entry.msgstr)}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def write_json(path: Path, report: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class TokenRenderQualityGate:
    """Classify token-rendered stats candidates before any canonical PO merge."""

    REJECT_ZH_SUBSTRINGS = {
        "到最大": "to_maximum_literal",
        "承受每秒": "per_second_tail_literal",
        "傷害每秒": "per_second_tail_literal",
        "冷卻時間使用": "context_heavy_single_token",
        "每...": "machine_translation_artifact",
        "於...時": "machine_translation_artifact",
        "有機率格擋": "machine_translation_artifact",
        "至等級": "machine_translation_artifact",
        "每能量球": "machine_translation_artifact",
        "最大每點": "machine_translation_artifact",
        "一個額外": "machine_translation_artifact",
        "被支援": "machine_translation_artifact",
        "在...": "machine_translation_artifact",
        "以...": "machine_translation_artifact",
        "承受的冰冷傷害來自擊中": "machine_translation_artifact",
        "傷害承受來自擊中": "machine_translation_artifact",
        "承受火焰傷害來自擊中": "machine_translation_artifact",
        "對定身敵人": "machine_translation_artifact",
    }
    CONDITION_PATTERNS = (
        " on hit",
        " while ",
        " when ",
        " if ",
        " with hits",
        " during ",
    )
    CONDITION_TAILS = ("擊中時", "命中時", "時")
    CONTEXT_HEAVY_SINGLE_TOKENS = {
        "block",
        "chance",
        "damage",
        "enemies",
        "enemy",
        "grants",
        "hits",
        "minions",
        "resistance",
        "use",
    }

    def __init__(self, report_path: Path) -> None:
        self.report_path = report_path
        self.report = json.loads(report_path.read_text(encoding="utf-8"))

    @staticmethod
    def _issue(severity: str, rule: str, detail: str) -> dict[str, str]:
        return {"severity": severity, "rule": rule, "detail": detail}

    def _classify_one(self, candidate: dict[str, Any]) -> dict[str, Any]:
        msgid = str(candidate.get("msgid", ""))
        msgstr = str(candidate.get("msgstr", ""))
        used_tokens = [str(token) for token in candidate.get("used_tokens", [])]
        lowered = f" {msgid.lower()} "
        issues: list[dict[str, str]] = []

        if placeholder_set(msgid) != placeholder_set(msgstr):
            issues.append(self._issue("reject", "placeholder_drift", "placeholder set changed"))

        if "to maximum" in lowered and "到最大" in msgstr:
            issues.append(self._issue("reject", "to_maximum_literal", "`to maximum` rendered as `到最大`"))

        if "per second" in lowered and msgstr.endswith("每秒"):
            issues.append(self._issue("reject", "per_second_tail_literal", "`per second` rendered as a sentence-tail literal"))

        if any(pattern in lowered for pattern in self.CONDITION_PATTERNS) and msgstr.endswith(self.CONDITION_TAILS):
            issues.append(self._issue("reject", "condition_suffix_tail", "English condition phrase rendered after the object"))

        if " if " in lowered and "如果" in msgstr and not msgstr.startswith("如果"):
            issues.append(self._issue("reject", "condition_suffix_tail", "`if` condition rendered after the object"))

        if " from hits" in lowered and "來自擊中" in msgstr:
            issues.append(self._issue("reject", "from_hits_tail_literal", "`from Hits` rendered as a literal tail"))

        if " during " in lowered and msgstr.endswith("效果期間內"):
            issues.append(self._issue("reject", "condition_suffix_tail", "`during` condition rendered as a sentence-tail literal"))

        if " while " in lowered and "雙持時" in msgstr and not msgstr.startswith("雙持時"):
            issues.append(self._issue("reject", "condition_suffix_tail", "`while` condition rendered after the object"))

        if " per " in lowered and re.search(r"(格擋攻擊傷害|傷害|半徑|速度|效果|持續時間)(每個|每顆|每有一個)", msgstr):
            issues.append(self._issue("reject", "per_tail_literal", "`per` phrase rendered as a sentence-tail literal"))

        if " per " in lowered and "per second" not in lowered:
            issues.append(self._issue("reject", "per_unhandled", "`per` phrase requires a phrase renderer before merge"))

        if " to level of " in lowered:
            issues.append(self._issue("reject", "level_phrase_unhandled", "`to Level of` phrase requires a phrase renderer before merge"))

        if " while affected by " in lowered:
            issues.append(self._issue("reject", "condition_suffix_tail", "`while affected by` requires a phrase renderer before merge"))

        for zh, rule in self.REJECT_ZH_SUBSTRINGS.items():
            if zh in msgstr and not any(issue["rule"] == rule for issue in issues):
                issues.append(self._issue("reject", rule, f"contains `{zh}`"))

        single_tokens = [token for token in used_tokens if " " not in token]
        heavy_tokens = [token for token in single_tokens if token in self.CONTEXT_HEAVY_SINGLE_TOKENS]
        if heavy_tokens:
            issues.append(
                self._issue(
                    "review",
                    "context_heavy_single_token",
                    "single-token translations need phrase renderer context: " + ", ".join(sorted(set(heavy_tokens))),
                )
            )
        if len(single_tokens) >= 3:
            issues.append(
                self._issue(
                    "review",
                    "too_many_single_tokens",
                    "candidate relies on three or more single-token translations",
                )
            )

        status = "accepted"
        if any(issue["severity"] == "reject" for issue in issues):
            status = "rejected"
        elif issues:
            status = "review"

        out = dict(candidate)
        out["quality_status"] = status
        out["quality_issues"] = issues
        return out

    def run(self) -> dict[str, Any]:
        classified = [self._classify_one(candidate) for candidate in self.report.get("candidates", [])]
        counts = Counter(item["quality_status"] for item in classified)
        issue_counts = Counter(issue["rule"] for item in classified for issue in item["quality_issues"])
        examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in classified:
            for issue in item["quality_issues"]:
                bucket = examples[issue["rule"]]
                if len(bucket) < 5:
                    bucket.append(
                        {
                            "status": item["quality_status"],
                            "msgid": item["msgid"],
                            "msgstr": item["msgstr"],
                            "detail": issue["detail"],
                        }
                    )
        return {
            "input": str(self.report_path),
            "candidate_count": len(classified),
            "counts": {
                "accepted": counts.get("accepted", 0),
                "review": counts.get("review", 0),
                "rejected": counts.get("rejected", 0),
            },
            "issue_counts": dict(issue_counts.most_common()),
            "examples": dict(examples),
            "candidates": classified,
        }

    @staticmethod
    def write_json(path: Path, report: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def write_markdown(path: Path, report: dict[str, Any]) -> None:
        lines = [
            "# Token Render Quality Report",
            "",
            f"- input: `{report['input']}`",
            f"- candidates: `{report['candidate_count']}`",
            f"- accepted: `{report['counts']['accepted']}`",
            f"- review: `{report['counts']['review']}`",
            f"- rejected: `{report['counts']['rejected']}`",
            "",
            "## Issue Counts",
            "",
        ]
        for rule, count in report["issue_counts"].items():
            lines.append(f"- `{rule}`: `{count}`")
        lines.extend(["", "## Examples", ""])
        for rule, examples in report["examples"].items():
            lines.append(f"### {rule}")
            lines.append("")
            for example in examples:
                lines.append(f"- `{example['status']}` {example['msgid']} => {example['msgstr']}")
                lines.append(f"  - {example['detail']}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def write_accepted_po(path: Path, report: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Review-only accepted token-render stats candidates.", ""]
        for item in report["candidates"]:
            if item["quality_status"] != "accepted":
                continue
            lines.append("#. quality_status: accepted")
            lines.append(f"#. used_tokens: {', '.join(item.get('used_tokens', []))}")
            lines.append(f"msgid {po_quote(item['msgid'])}")
            lines.append(f"msgstr {po_quote(item['msgstr'])}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")


def cmd_extract(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    extractor = TokenPoExtractor(
        catalog_path=root / args.catalog,
        rules_path=root / args.rules,
        min_frequency=args.min_frequency,
        min_votes=args.min_votes,
        include_learned=True,
    )
    terms = extractor.extract()
    TokenPoExtractor.write_json(root / args.json_output, terms)
    TokenPoExtractor.write_po(
        root / args.po_output,
        terms,
        prefill_learned=args.prefill_learned,
        batch_size=args.batch_size,
        batches_dir=(root / args.batches_dir) if args.batches_dir else None,
    )
    by_class = Counter(term.cls for term in terms.values())
    print(f"terms={len(terms)} classes={dict(by_class.most_common())}")
    print(f"wrote {root / args.po_output}")
    print(f"wrote {root / args.json_output}")
    if args.batches_dir:
        print(f"wrote batches under {root / args.batches_dir}")
    return 0


def cmd_merge_batches(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    old_cwd = Path.cwd()
    try:
        import os

        os.chdir(root)
        merger = TokenPoBatchMerger(base_token_po=root / args.base_token_po, batch_glob=str(args.batch_glob))
        entries, report = merger.merge()
    finally:
        os.chdir(old_cwd)
    output = root / args.output
    TokenPoBatchMerger.write_po(output, entries)
    print(
        "batches={batch_count} translations={translation_count} updated={updated_count}".format(
            **report
        )
    )
    print(f"wrote {output}")
    return 0


def cmd_build_token_po(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    builder = TokenPoBuilder(
        inventory_po=root / args.inventory_po,
        seed_po=(root / args.seed_po) if args.seed_po else None,
        overlay_po=(root / args.overlay_po) if args.overlay_po else None,
    )
    entries, report = builder.build()
    output = root / args.output
    report_output = root / args.report_output
    TokenPoBuilder.write_po(output, entries)
    TokenPoBuilder.write_json(report_output, report)
    print(
        "inventory={inventory_count} seed_translated={seed_translated_count} "
        "overlay_translated={overlay_translated_count} overlay_added={overlay_added_count} "
        "output={output_count} translated={translated_count} empty={empty_count}".format(**report)
    )
    print(f"wrote {output}")
    print(f"wrote {report_output}")
    return 0


def cmd_compose(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    composer = TokenPoComposer(stats_po=root / args.stats_po, token_po=root / args.token_po)
    report = composer.compose(limit=args.limit, allow_partial=args.allow_partial, require_phrase=not args.allow_single_word_only)
    TokenPoComposer.write_outputs(report, root / args.json_output, root / args.po_output)
    print(
        "token_translations={token_translation_count} candidates={candidate_count} skipped={skipped}".format(
            **report
        )
    )
    print(f"wrote {root / args.po_output}")
    print(f"wrote {root / args.json_output}")
    return 0


def cmd_quality(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    gate = TokenRenderQualityGate(root / args.input)
    report = gate.run()
    TokenRenderQualityGate.write_json(root / args.json_output, report)
    TokenRenderQualityGate.write_markdown(root / args.md_output, report)
    if args.accepted_po_output:
        TokenRenderQualityGate.write_accepted_po(root / args.accepted_po_output, report)
    print(
        "candidates={candidate_count} accepted={accepted} review={review} rejected={rejected}".format(
            candidate_count=report["candidate_count"],
            **report["counts"],
        )
    )
    print(f"wrote {root / args.json_output}")
    print(f"wrote {root / args.md_output}")
    if args.accepted_po_output:
        print(f"wrote {root / args.accepted_po_output}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    extract = sub.add_parser("extract")
    extract.add_argument("--root", type=Path, default=Path("."))
    extract.add_argument("--catalog", type=Path, default=Path("work/pob/stats-ast/token-catalog.json"))
    extract.add_argument("--rules", type=Path, default=Path("work/pob/stats-ast/token-rules.json"))
    extract.add_argument("--po-output", type=Path, default=Path("work/pob/stats-ast/token-terms.po"))
    extract.add_argument("--json-output", type=Path, default=Path("work/pob/stats-ast/token-terms.json"))
    extract.add_argument("--batches-dir", type=Path, default=Path("work/pob/stats-ast/token-term-batches"))
    extract.add_argument("--batch-size", type=int, default=300)
    extract.add_argument("--min-frequency", type=int, default=50)
    extract.add_argument("--min-votes", type=int, default=3)
    extract.add_argument("--prefill-learned", action="store_true")
    extract.set_defaults(func=cmd_extract)

    merge_batches = sub.add_parser("merge-batches")
    merge_batches.add_argument("--root", type=Path, default=Path("."))
    merge_batches.add_argument("--base-token-po", type=Path, default=Path("work/pob/stats-ast/token-terms.po"))
    merge_batches.add_argument("--batch-glob", type=Path, default=Path("work/pob/stats-ast/token-term-batches/*.po"))
    merge_batches.add_argument("--output", type=Path, default=Path("work/pob/stats-ast/token-terms.merged.po"))
    merge_batches.set_defaults(func=cmd_merge_batches)

    build_token_po = sub.add_parser("build-token-po")
    build_token_po.add_argument("--root", type=Path, default=Path("."))
    build_token_po.add_argument("--inventory-po", type=Path, default=Path("work/pob/stats-ast/token-terms.po"))
    build_token_po.add_argument("--seed-po", type=Path, default=Path("work/pob/stats-ast/token-terms.merged.po"))
    build_token_po.add_argument("--overlay-po", type=Path, default=Path("work/pob/stats-ast/token.po"))
    build_token_po.add_argument("--output", type=Path, default=Path("work/pob/stats-ast/token.po"))
    build_token_po.add_argument("--report-output", type=Path, default=Path("work/pob/stats-ast/token-build-report.json"))
    build_token_po.set_defaults(func=cmd_build_token_po)

    compose = sub.add_parser("compose")
    compose.add_argument("--root", type=Path, default=Path("."))
    compose.add_argument("--stats-po", type=Path, default=Path("locale/zh_TW/LC_MESSAGES/stats.po"))
    compose.add_argument("--token-po", type=Path, default=Path("work/pob/stats-ast/token.po"))
    compose.add_argument("--po-output", type=Path, default=Path("work/pob/stats-ast/token-render-preview.po"))
    compose.add_argument("--json-output", type=Path, default=Path("work/pob/stats-ast/token-render-preview.json"))
    compose.add_argument("--limit", type=int)
    compose.add_argument("--allow-partial", action="store_true")
    compose.add_argument("--allow-single-word-only", action="store_true")
    compose.set_defaults(func=cmd_compose)

    quality = sub.add_parser("quality")
    quality.add_argument("--root", type=Path, default=Path("."))
    quality.add_argument("--input", type=Path, default=Path("work/pob/stats-ast/token-render-preview.json"))
    quality.add_argument("--json-output", type=Path, default=Path("work/pob/stats-ast/token-render-quality.json"))
    quality.add_argument("--md-output", type=Path, default=Path("work/pob/stats-ast/token-render-quality.md"))
    quality.add_argument("--accepted-po-output", type=Path, default=Path("work/pob/stats-ast/token-render-accepted.po"))
    quality.set_defaults(func=cmd_quality)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
