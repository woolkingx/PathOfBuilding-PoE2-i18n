# Path of Building 2 — i18n Mechanism

[繁體中文說明](README.zh-TW.md)

This fork adds an **internationalization (i18n) mechanism** to
[Path of Building 2 Community](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2),
built into the engine itself rather than overlaid from outside. It is based on
the upstream `dev` snapshot `b8048682` (`Update Uniques to 0.5 (#2116)`).

**The point of this project is the mechanism, not any single language.** Once
the i18n layer is in place, any language can be translated through plain
gettext-style **PO files** — no Lua and no engine internals required. Because the
mechanism lives inside the engine, it also supports things an external overlay
cannot: typing CJK text directly and searching by translated text.

**Traditional Chinese (`zh_TW`) ships as the first reference localization** — a
demonstration that the mechanism works end to end, not the focus of the project.
The upstream project remains the owner of Path of Building 2 Community; this fork
is published as a reusable i18n patch/release branch for maintainers or players
who want to inspect, test, reuse, or extend the mechanism.

![Path of Building 2 i18n Traditional Chinese screenshot](docs/assets/pob2-i18n.png)

## What This Fork Adds

- A display-boundary i18n mechanism in `src/Modules/Lang.lua` that any locale
  can plug into.
- Runtime locale selection for any PO-provided language (Traditional Chinese
  ships as the reference locale).
- Standard gettext-style PO catalogs (the reference set lives under
  `locale/zh_TW/LC_MESSAGES/`).
- Generated Lua translation tables under `src/Data/Lang/<locale>/`.
- CJK runtime font support and direct CJK text input/search.
- Scripted extraction, compilation, and audit gates for localization coverage.

## Translating to Another Language

You do not need the maintainer for the translation side, and you do not need to
touch any Lua. The reference `zh_TW` PO catalogs are the template:

1. Copy `locale/zh_TW/LC_MESSAGES/*.po` to your locale (e.g. `zh_CN`, `ko`, `ja`).
2. Translate the entries — they are plain text; a translation tool or script can
   give you a fast first pass to refine from.
3. Compile to runtime tables with `scripts/compile-lang.py`.

The maintainer focuses on the **i18n mechanism** (display, input, search), not on
translation wording. Issues about rendering, IME/input, or search not matching
are very welcome; translation content is best owned by each language's
translators.

## Boundary

The i18n layer is display-only. Raw build data stays compatible with upstream
Path of Building:

- Import/export payloads remain English/raw.
- Saved build identities remain English/raw.
- Trade API values and parser inputs remain English/raw.
- Calculation internals remain English/raw.
- UI labels, dropdown rows, tooltips, table labels, and visible item/skill/stat
  names are translated at display boundaries.

## Branch Model

The intended public branch shape is:

```text
dev      -> upstream clone baseline b8048682
release  -> i18n release branch
```

Use GitHub compare to inspect the patch:

```text
dev...release
```

## Verification

The current i18n release is checked with:

```bash
python3 scripts/compile-lang.py --check locale/zh_TW/LC_MESSAGES/pob.po src/Data/Lang/zh_TW/pob.lua
python3 scripts/audit-zh-tw-display-closure.py --root . --format json --fail-on-open
python3 scripts/audit-display-identity-i18n.py --root . --format json --output work/pob/display-identity-audit.json --fail-on-open
python3 scripts/analyze-i18n-display-graph.py --root . --format md --output work/pob/dropdown-i18n-graph.md --fail-on-high
python3 scripts/audit-ui-message-i18n.py --root . --domain ui --format json --output work/pob/ui-message-audit-ui.json --fail-on-open
```

## Upstream

Original project:
[PathOfBuildingCommunity/PathOfBuilding-PoE2](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2)

Original license: MIT. See [LICENSE.md](LICENSE.md).
