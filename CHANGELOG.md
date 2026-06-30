# Changelog

This changelog covers **only the i18n fork's own changes**. For the upstream
Path of Building 2 Community game/data history, see the
[official changelog](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/releases).

## PathOfBuilding-PoE2-i18n release draft (2026/06/20)

This fork starts from upstream commit
`b8048682ee361e5435e09d5507d45185c1d4be49`
(`Update Uniques to 0.5 (#2116)`) and adds an **i18n mechanism** to the engine,
so any language can be translated through plain PO files. Traditional Chinese
(`zh_TW`) ships as the first reference localization.

### Added

- Added a display-boundary i18n mechanism in `src/Modules/Lang.lua` that any
  locale can plug into.
- Added runtime translation helpers and locale selection.
- Added display-only translation routes for UI chrome, dropdown rows, tooltips,
  item/skill/passive labels, stat descriptions, and calculation labels.
- Added CJK font/runtime support and direct CJK text input/search.
- Added extraction, compile, and audit scripts for repeatable i18n validation.
- Added `zh_TW` PO catalogs and generated `src/Data/Lang/zh_TW/*.lua` runtime
  tables as the reference localization for UI, items, skills, passives, and stats.

### Boundary

- Raw build data, import/export payloads, trade API values, parser inputs, and
  calculation internals remain English/raw.
- Translation is applied at display boundaries only.
- `zh_CN` is not part of this release cleanup.
