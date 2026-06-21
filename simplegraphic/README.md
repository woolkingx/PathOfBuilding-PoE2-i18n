# SimpleGraphic i18n patch (rendering engine)

Path of Building runs on the **SimpleGraphic** C++ engine. The Lua layer (repo
root) handles Chinese display and search; this engine layer is the other half —
it makes Chinese **input** and **rendering** actually work:

- **CJK text input** — type Chinese into input fields (search, name boxes).
- **Unicode font fallback** — draw glyphs the base font lacks.

## Source

Upstream:
[PathOfBuildingCommunity/PathOfBuilding-SimpleGraphic](https://github.com/PathOfBuildingCommunity/PathOfBuilding-SimpleGraphic),
baseline `c062b29`.

| File | Change |
|---|---|
| `ui_main.cpp` / `ui_main.h` | Encode Unicode codepoints to UTF-8 and pass them to Lua, so CJK characters can be typed into input fields. |
| `engine/render/r_font.cpp` / `r_font.h` | Unicode font fallback for CJK glyphs. |
| `engine/render/r_texture.cpp` | Supporting texture changes for fallback. |
