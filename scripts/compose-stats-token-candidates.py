#!/usr/bin/env python3
"""Compose stats translations from token PO for empty or identity entries."""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}|%\.[0-9]+f|%[0-9]+\$[sdif]|%[sdif]")
ENGLISH_RE = re.compile(r"[A-Za-z]")


def load_stats_token_module(root: Path) -> Any:
    path = root / "scripts/stats_token_po.py"
    spec = importlib.util.spec_from_file_location("stats_token_po", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class EmptyAwareComposer:
    def __init__(self, module: Any, stats_po: Path, token_po: Path) -> None:
        self.module = module
        self.composer = module.TokenPoComposer(stats_po=stats_po, token_po=token_po)

    DAMAGE = {
        "Chaos": "混沌傷害",
        "Cold": "冰冷傷害",
        "Elemental": "元素傷害",
        "Fire": "火焰傷害",
        "Lightning": "閃電傷害",
        "Physical": "物理傷害",
    }
    RESISTANCE = {
        "Chaos": "混沌抗性",
        "Cold": "冰冷抗性",
        "Fire": "火焰抗性",
        "Lightning": "閃電抗性",
    }
    RESOURCE = {
        "Armour": "護甲",
        "Dexterity": "敏捷",
        "Energy Shield": "能量護盾",
        "Evasion Rating": "閃避值",
        "Intelligence": "智慧",
        "Life": "生命",
        "Mana": "魔力",
        "Spirit": "精魂",
        "Strength": "力量",
    }
    AILMENT = {
        "Frozen": "冰凍",
        "Ignited": "點燃",
        "Shocked": "感電",
    }
    ACTOR = {
        "Companions": "同伴",
        "Minions": "召喚物",
        "Socketed Gems": "已鑲嵌的寶石",
        "Supported Skills": "被輔助技能",
        "Totems": "圖騰",
    }
    OP = {
        "additional": "額外",
        "increased": "增加",
        "less": "更少",
        "more": "更多",
        "reduced": "減少",
    }
    PHRASE_OVERRIDES = {
        "all Attack Skills": "所有攻擊技能",
        "all Bow Skill Gems": "所有弓技能寶石",
        "all Chaos Skills": "所有混沌技能",
        "all Corrupted Skill Gems": "所有腐化技能寶石",
        "all Corrupted Spell Skill Gems": "所有腐化法術技能寶石",
        "all Critical Support Gems": "所有暴擊輔助寶石",
        "all Crossbow Skill Gems": "所有十字弓技能寶石",
        "all Curse Skills": "所有詛咒技能",
        "all Elemental Skills": "所有元素技能",
        "all Link Skill Gems": "所有連結技能寶石",
        "all Mark Skills": "所有印記技能",
        "all Physical Skills": "所有物理技能",
        "all Raise Spectre Gems": "所有召喚靈體寶石",
        "all Raise Zombie Gems": "所有殭屍寶石",
        "Despair Skills": "絕望技能",
        "Elemental Weakness Skills": "元素要害技能",
        "Enfeeble Skills": "衰弱技能",
        "Socketed Elemental Gems": "已鑲嵌的元素寶石",
        "Socketed Skill Gems": "已鑲嵌的技能寶石",
        "Socketed Strength Gems": "已鑲嵌的力量寶石",
        "Socketed Support Gems": "已鑲嵌的輔助寶石",
        "Temporal Chains Skills": "時空鎖鏈技能",
        "Vulnerability Skills": "易傷技能",
        "Critical Damage Bonus": "暴擊傷害加成",
        "Damaging Ailments": "傷害型異常狀態",
        "Deflection Rating": "偏斜值",
        "Slowing Potency of Debuffs on You": "你身上減益的緩速效力",
    }

    @staticmethod
    def normalize(text: str) -> str:
        return " ".join(text.lower().split())

    def phrase(self, text: str, *classes: str) -> str:
        if text in self.PHRASE_OVERRIDES:
            return self.PHRASE_OVERRIDES[text]
        return self.composer._zh(self.normalize(text), *classes)

    @staticmethod
    def has_english_leftover(text: str) -> bool:
        return ENGLISH_RE.search(PLACEHOLDER_RE.sub("", text)) is not None

    def structured_render(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        renderers = (
            self.render_enemy_resistance,
            self.render_enemy_ailment_when_hit,
            self.render_level_of,
            self.render_avoid_damage_from_hits,
            self.render_damage_taken_from_hits,
            self.render_life_per_second,
            self.render_actor_regenerate_life,
            self.render_gain_charges_per_second,
            self.render_subject_have_stat,
            self.render_to_resistance_or_resource,
            self.render_armour_applies_to_damage,
            self.render_damage_recouped,
            self.render_damage_taken_as,
            self.render_gain_extra_damage,
            self.render_deflection_equal_to,
            self.render_while_at_least_stat,
            self.render_faster_ailment_damage,
            self.render_simple_unary_stat,
            self.render_misc_simple_patterns,
            self.render_damage_per_stat,
            self.render_increased_reduced_per_stat,
        )
        for renderer in renderers:
            rendered = renderer(msgid)
            if (
                rendered
                and not self.has_english_leftover(rendered[0])
                and self.module.placeholder_set(rendered[0]) == self.module.placeholder_set(msgid)
            ):
                return rendered
        return None

    def render_enemy_resistance(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"Nearby Enemies have (?P<amount>.+?) to (?P<element>Chaos|Cold|Fire|Lightning) Resistance", msgid)
        if not match:
            return None
        return (
            f"附近敵人有{match.group('amount')}{self.RESISTANCE[match.group('element')]}",
            ["nearby enemies", f"{match.group('element').lower()} resistance"],
            [],
        )

    def render_enemy_ailment_when_hit(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"Nearby Enemies have (?P<amount>.+?) chance to be (?P<ailment>Frozen|Ignited|Shocked) when Hit", msgid)
        if not match:
            return None
        return (
            f"附近敵人被擊中時有{match.group('amount')}機率被{self.AILMENT[match.group('ailment')]}",
            ["nearby enemies", "chance to", "when hit"],
            [],
        )

    def render_level_of(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"(?P<amount>[+\-]?(?:\([^)]+\)|\{[^}]+\}|\d+(?:\.\d+)?)) to Level of (?P<object>.+)", msgid, re.IGNORECASE)
        if not match:
            return None
        obj = self.phrase(match.group("object"), "skill", "mechanic", "word")
        if not obj:
            return None
        return (f"{obj}等級 {match.group('amount')}", [self.normalize(match.group("object")), "to level of"], [])

    def render_avoid_damage_from_hits(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"(?P<amount>.+?) chance to Avoid (?P<object>Chaos|Cold|Elemental|Fire|Lightning|Physical) Damage from Hits", msgid)
        if match:
            return (
                f"有{match.group('amount')}機率避免來自擊中的{self.DAMAGE[match.group('object')]}",
                [f"{match.group('object').lower()} damage", "from hits", "chance to avoid"],
                [],
            )
        match = re.fullmatch(r"(?P<amount>.+?) chance to Avoid Death from Hits", msgid)
        if not match:
            return None
        return (
            f"有{match.group('amount')}機率避免因擊中死亡",
            ["death from hits", "chance to avoid"],
            [],
        )

    def render_damage_taken_from_hits(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"(?P<amount>[+\\-]?.+?) (?P<element>Chaos|Cold|Fire|Lightning|Physical) Damage taken from Hits", msgid)
        if not match:
            return None
        return (
            f"承受來自擊中的{match.group('amount')}{self.DAMAGE[match.group('element')]}",
            [f"{match.group('element').lower()} damage", "from hits"],
            [],
        )

    def render_life_per_second(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"Lose (?P<amount>.+?) of maximum Life per second", msgid, re.IGNORECASE)
        if match:
            return (f"每秒失去最大生命的{match.group('amount')}", ["maximum life", "per second"], [])
        match = re.fullmatch(r"Minions Regenerate (?P<amount>.+?) of maximum Life per second", msgid, re.IGNORECASE)
        if match:
            return (f"召喚物每秒回復最大生命的{match.group('amount')}", ["minions", "maximum life", "per second"], [])
        match = re.fullmatch(r"(?P<amount>.+?) of Maximum Life taken as Chaos Damage per second", msgid, re.IGNORECASE)
        if match:
            return (f"每秒承受相當於最大生命{match.group('amount')}的混沌傷害", ["maximum life", "chaos damage", "per second"], [])
        match = re.fullmatch(r"your maximum Life as Physical damage per second", msgid, re.IGNORECASE)
        if match:
            return ("每秒承受相當於你最大生命的物理傷害", ["maximum life", "physical damage", "per second"], [])
        match = re.fullmatch(r"Body Armour grants regenerate (?P<amount>.+?) of maximum Life per second", msgid, re.IGNORECASE)
        if match:
            return (f"身體護甲賦予每秒回復最大生命的{match.group('amount')}", ["body armour grants", "maximum life", "per second"], [])
        return None

    def render_actor_regenerate_life(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"(?P<actor>Minions|Totems) Regenerate (?P<amount>.+?) of (?P<scope>maximum Life|Life) per second", msgid, re.IGNORECASE)
        if not match:
            return None
        scope = "最大生命" if match.group("scope").lower() == "maximum life" else "生命"
        return (
            f"{self.ACTOR[match.group('actor')]}每秒回復{scope}的{match.group('amount')}",
            [self.normalize(match.group("actor")), self.normalize(match.group("scope")), "per second"],
            [],
        )

    def render_gain_charges_per_second(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"(?P<actor>Charms|Life Flasks|Mana Flasks) gain (?P<amount>.+?) charges? per Second", msgid, re.IGNORECASE)
        if not match:
            return None
        actor = {
            "Charms": "護符",
            "Life Flasks": "生命藥劑",
            "Mana Flasks": "魔力藥劑",
        }[match.group("actor")]
        return (f"{actor}每秒獲得{match.group('amount')}充能", [self.normalize(match.group("actor")), "charges", "per second"], [])

    def render_subject_have_stat(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(
            r"(?P<actor>Companions|Minions|Socketed Gems|Supported Skills) have (?P<amount>.+?) to (?P<stat>Chaos Resistance|Cold Resistance|Fire Resistance|Lightning Resistance|Spirit)",
            msgid,
            re.IGNORECASE,
        )
        if match:
            stat = self.phrase(match.group("stat"), "mechanic", "resource", "word")
            if not stat:
                return None
            return (
                f"{self.ACTOR[match.group('actor')]}有{match.group('amount')}{stat}",
                [self.normalize(match.group("actor")), self.normalize(match.group("stat"))],
                [],
            )
        match = re.fullmatch(
            r"(?P<actor>Companions|Minions|Socketed Gems|Supported Skills) have (?P<amount>.+?) (?:(?P<op>additional|increased|reduced|more|less) )?(?P<stat>.+)",
            msgid,
            re.IGNORECASE,
        )
        if not match:
            return None
        stat = self.phrase(match.group("stat"), "mechanic", "resource", "word")
        if not stat:
            return None
        op = self.OP.get((match.group("op") or "").lower(), "")
        return (
            f"{self.ACTOR[match.group('actor')]}有{match.group('amount')}{op}{stat}",
            [self.normalize(match.group("actor")), self.normalize(match.group("stat"))],
            [],
        )

    def render_to_resistance_or_resource(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"(?P<amount>.+?) to (?P<stat>Chaos Resistance|Cold Resistance|Fire Resistance|Lightning Resistance|Spirit)", msgid, re.IGNORECASE)
        if not match:
            return None
        stat = self.phrase(match.group("stat"), "mechanic", "resource", "word")
        if not stat:
            return None
        return (f"{stat}{match.group('amount')}", [self.normalize(match.group("stat"))], [])

    def render_armour_applies_to_damage(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(
            r"(?P<amount>.+?) of (?P<source>Armour|Evasion Rating) also applies to (?P<damage>Chaos|Cold|Elemental|Fire|Lightning|Physical) Damage",
            msgid,
            re.IGNORECASE,
        )
        if not match:
            return None
        source = self.RESOURCE[match.group("source")]
        damage = self.DAMAGE[match.group("damage")]
        return (f"{source}的{match.group('amount')}同時套用至{damage}", [self.normalize(match.group("source")), f"{match.group('damage').lower()} damage"], [])

    def render_damage_recouped(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(
            r"(?P<amount>.+?) of (?P<source>(?:Chaos|Cold|Elemental|Fire|Lightning|Physical) Damage|Damage)(?: taken| prevented)? Recouped as (?P<target>Energy Shield|Life|Mana)",
            msgid,
            re.IGNORECASE,
        )
        if not match:
            return None
        source = "傷害" if match.group("source").lower() == "damage" else self.DAMAGE[match.group("source").split()[0]]
        target = self.RESOURCE[match.group("target")]
        return (f"{source}的{match.group('amount')}補償為{target}", [self.normalize(match.group("source")), self.normalize(match.group("target"))], [])

    def render_damage_taken_as(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(
            r"(?P<amount>.+?) of (?P<source>Chaos|Cold|Elemental|Fire|Lightning|Physical) Damage taken as (?P<target>Chaos|Cold|Elemental|Fire|Lightning|Physical) Damage",
            msgid,
            re.IGNORECASE,
        )
        if not match:
            return None
        source = self.DAMAGE[match.group("source")]
        target = self.DAMAGE[match.group("target")]
        return (f"承受的{source}有{match.group('amount')}視為{target}", [f"{match.group('source').lower()} damage", f"{match.group('target').lower()} damage"], [])

    def render_gain_extra_damage(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(
            r"Gain (?P<amount>.+?) of (?P<source>Damage|(?:Chaos|Cold|Elemental|Fire|Lightning|Physical) Damage) as [Ee]xtra (?P<target>Chaos|Cold|Elemental|Fire|Lightning|Physical) Damage(?P<tail> while you are missing Runic Ward)?",
            msgid,
            re.IGNORECASE,
        )
        if not match:
            return None
        source = "傷害" if match.group("source").lower() == "damage" else self.DAMAGE[match.group("source").split()[0]]
        target = self.DAMAGE[match.group("target")]
        prefix = "符文結界未滿時，" if match.group("tail") else ""
        return (f"{prefix}獲得{source}的{match.group('amount')}作為額外{target}", [self.normalize(match.group("source")), self.normalize(match.group("target"))], [])

    def render_deflection_equal_to(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"Gain Deflection Rating equal to (?P<amount>.+?) of (?P<source>Armour|Evasion Rating)", msgid, re.IGNORECASE)
        if not match:
            return None
        return (f"獲得等同{self.RESOURCE[match.group('source')]}{match.group('amount')}的偏斜值", ["deflection rating", self.normalize(match.group("source"))], [])

    def render_while_at_least_stat(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"(?P<amount>.+?) to Spirit while you have at least (?P<threshold>.+?) (?P<stat>Strength|Dexterity|Intelligence)", msgid, re.IGNORECASE)
        if not match:
            return None
        return (f"若你至少有{match.group('threshold')}{self.RESOURCE[match.group('stat')]}，精魂{match.group('amount')}", ["spirit", self.normalize(match.group("stat"))], [])

    def render_faster_ailment_damage(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"Damaging Ailments deal damage (?P<amount>.+?) faster", msgid, re.IGNORECASE)
        if not match:
            return None
        return (f"傷害型異常狀態造成傷害加快{match.group('amount')}", ["damaging ailments"], [])

    def render_simple_unary_stat(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"(?P<amount>.+?) (?P<op>increased|reduced|more|less) (?P<stat>.+)", msgid, re.IGNORECASE)
        if not match or any(word in msgid.lower() for word in (" if ", " while ", " per ", " with ", " against ", "\n")):
            return None
        stat = self.phrase(match.group("stat"), "mechanic", "resource", "word")
        if not stat and match.group("stat") in self.RESOURCE:
            stat = self.RESOURCE[match.group("stat")]
        if not stat:
            return None
        return (f"{match.group('amount')}{self.OP[match.group('op').lower()]}{stat}", [self.normalize(match.group("stat"))], [])

    def render_misc_simple_patterns(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(r"(?P<amount>.+?) (?P<resource>Life|Mana) gained when you Block", msgid, re.IGNORECASE)
        if match:
            return (f"格擋時獲得{match.group('amount')}{self.RESOURCE[match.group('resource')]}", [self.normalize(match.group("resource")), "block"], [])
        match = re.fullmatch(r"Hits against you have (?P<amount>.+?) reduced Critical Damage Bonus", msgid, re.IGNORECASE)
        if match:
            return (f"對你的擊中有{match.group('amount')}減少暴擊傷害加成", ["critical damage bonus"], [])
        match = re.fullmatch(r"Debuffs on you expire (?P<amount>.+?) faster", msgid, re.IGNORECASE)
        if match:
            return (f"你身上的減益消退速度加快{match.group('amount')}", ["debuffs"], [])
        match = re.fullmatch(r"Prevent (?P<amount>.+?) of Damage from Deflected Hits", msgid, re.IGNORECASE)
        if match:
            return (f"防止來自偏斜擊中的{match.group('amount')}傷害", ["deflected hits"], [])
        match = re.fullmatch(r"You take (?P<amount>.+?) of damage from Blocked Hits", msgid, re.IGNORECASE)
        if match:
            return (f"你承受來自已格擋擊中的{match.group('amount')}傷害", ["blocked hits"], [])
        match = re.fullmatch(r"Remnants can be collected from (?P<amount>.+?) further away", msgid, re.IGNORECASE)
        if match:
            return (f"可從{match.group('amount')}更遠處收集殘骸", ["remnants"], [])
        return None

    def render_damage_per_stat(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(
            r"(?P<amount>.+?) (?P<op>increased|reduced|more) (?P<damage>Damage|Elemental Damage|Projectile Attack Damage) per (?P<per>.+)",
            msgid,
            re.IGNORECASE,
        )
        if not match:
            return None
        damage = self.phrase(match.group("damage"), "mechanic", "damage", "word")
        per = self.phrase(match.group("per"), "mechanic", "resource", "word")
        if not damage or not per:
            return None
        op = {"increased": "增加", "reduced": "減少", "more": "更多"}[match.group("op").lower()]
        return (f"每{per}，{damage}{op}{match.group('amount')}", [self.normalize(match.group("damage")), self.normalize(match.group("per"))], [])

    def render_increased_reduced_per_stat(self, msgid: str) -> tuple[str, list[str], list[str]] | None:
        match = re.fullmatch(
            r"(?P<amount>.+?) (?P<op>increased|reduced|more|less) (?P<stat>.+?) per (?P<per>.+)",
            msgid,
            re.IGNORECASE,
        )
        if not match or "\n" in msgid or "," in match.group("per") or " while " in match.group("per").lower():
            return None
        stat = self.phrase(match.group("stat"), "mechanic", "damage", "resource", "word")
        per = self.phrase(match.group("per"), "mechanic", "resource", "word")
        if not stat or not per:
            return None
        op = self.OP[match.group("op").lower()]
        return (f"每{per}，{stat}{op}{match.group('amount')}", [self.normalize(match.group("stat")), self.normalize(match.group("per"))], [])

    def compose(self, limit: int | None, allow_partial: bool, require_phrase: bool, only_structured: bool) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        missing_counter: Counter[str] = Counter()
        skipped: Counter[str] = Counter()
        for entry in self.composer.stats_entries:
            if not entry.msgid:
                skipped["header"] += 1
                continue
            if entry.msgstr and entry.msgstr != entry.msgid:
                skipped["translated"] += 1
                continue
            structured = self.structured_render(entry.msgid)
            if only_structured and not structured:
                skipped["no_structured_rule"] += 1
                continue
            rendered, used, missing = structured if structured else self.composer._compose_one(entry.msgid)
            if not used:
                skipped["no_translated_token"] += 1
                missing_counter.update(missing)
                continue
            if require_phrase and not structured and not any(" " in phrase for phrase in used):
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
            if self.module.placeholder_set(rendered) != self.module.placeholder_set(entry.msgid):
                skipped["placeholder_drift"] += 1
                continue
            candidates.append(
                {
                    "msgid": entry.msgid,
                    "msgstr": rendered,
                    "used_tokens": used,
                    "missing_tokens": missing,
                    "method": "structured-token-transform" if structured else "token-po-compose-empty-aware",
                }
            )
            if limit and len(candidates) >= limit:
                break
        return {
            "token_translation_count": len(self.composer.translations),
            "candidate_count": len(candidates),
            "skipped": dict(skipped),
            "missing_tokens": missing_counter.most_common(100),
            "candidates": candidates,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--stats-po", type=Path, default=Path("locale/zh_TW/LC_MESSAGES/stats.po"))
    parser.add_argument("--token-po", type=Path, default=Path("work/pob/stats-ast/token.po"))
    parser.add_argument("--po-output", type=Path, default=Path("work/pob/stats-ast/token-render-empty-aware.po"))
    parser.add_argument("--json-output", type=Path, default=Path("work/pob/stats-ast/token-render-empty-aware.json"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--allow-single-word-only", action="store_true")
    parser.add_argument("--only-structured", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    module = load_stats_token_module(root)
    composer = EmptyAwareComposer(module, root / args.stats_po, root / args.token_po)
    report = composer.compose(
        limit=args.limit,
        allow_partial=args.allow_partial,
        require_phrase=not args.allow_single_word_only,
        only_structured=args.only_structured,
    )
    module.TokenPoComposer.write_outputs(report, root / args.json_output, root / args.po_output)
    print(
        "token_translations={token_translation_count} candidates={candidate_count} skipped={skipped}".format(
            **report
        )
    )
    print(f"wrote {root / args.po_output}")
    print(f"wrote {root / args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
