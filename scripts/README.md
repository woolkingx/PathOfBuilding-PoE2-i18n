# i18n scripts / 中文化腳本說明

These helper scripts support the localization workflow. Run them from the repo
root with `python3 scripts/<name>.py`. Most take `--help`.

這些腳本輔助中文化流程。請從專案根目錄執行：`python3 scripts/<名稱>.py`，
多數支援 `--help`。

---

## Everyday translation / 日常翻譯（最常用）

The normal loop is: **check progress → export what's untranslated → translate →
compile.**
一般循環：**看進度 → 匯出未翻 → 翻譯 → 編譯。**

| Script | What it does / 用途 |
|---|---|
| `compile-lang.py` | Compile a `.po` into the `.lua` table the program reads. 把 PO 編譯成程式讀取的 Lua 對照表。<br>`python3 scripts/compile-lang.py locale/zh_TW/LC_MESSAGES/pob.po src/Data/Lang/zh_TW/pob.lua`<br>Add `--check` to verify without writing. 加 `--check` 只檢查不寫入。 |
| `audit-po-translation-progress.py` | Report translation progress: how many entries are empty or untranslated. 統計翻譯進度：還有多少條目未翻或留空。 |
| `export-po-untranslated-batches.py` | Export untranslated entries into small batches for easier translating. 把未翻條目匯出成小批次，方便分批翻。 |
| `validate-po-batch.py` | Check a translated batch keeps the original msgids and placeholders intact. 檢查翻好的批次有沒有改壞原文 ID 或佔位符。 |
| `merge-po-batch.py` | Merge a reviewed batch back into the main locale PO file. 把校對好的批次合併回主 PO 檔。 |

---

## Batch helpers / 批次輔助工具

| Script | What it does / 用途 |
|---|---|
| `export-po-translation-batches.py` | Export untranslated candidates into review/model batches. 匯出未翻候選成審閱批次。 |
| `export-po-placeholder-batches.py` | Export entries where the translation still equals the source (placeholders). 匯出「譯文仍等於原文」的佔位條目。 |
| `fill-po-placeholders.py` | Fill empty translations with the source text as a placeholder. 用原文填入空翻譯當佔位。 |

---

## Maintainer tools / 維護者工具（建立與稽核翻譯框架）

You normally don't need these to translate — they build and audit the i18n
layer itself.
一般翻譯用不到——這些是建立與稽核 i18n 框架本身用的。

### Extract source strings / 從程式抽取詞條

| Script | What it does / 用途 |
|---|---|
| `extract-ui-msgids.py` | Extract UI strings from PoB Lua files. 從 Lua 介面檔抽 UI 詞條。 |
| `extract-item-msgids.py` | Extract item display names. 抽物品名稱。 |
| `extract-skill-msgids.py` | Extract skill / gem names. 抽技能 / 寶石名稱。 |
| `extract-passive-msgids.py` | Extract passive tree node names. 抽天賦樹節點名稱。 |
| `extract-stat-msgids.py` | Extract stat / modifier text. 抽屬性 / 詞綴文字。 |

### Audit coverage / 稽核覆蓋率

| Script | What it does / 用途 |
|---|---|
| `audit-zh-tw-display-closure.py` | Audit zh_TW display coverage for known surfaces. 稽核繁中顯示覆蓋率。 |
| `audit-display-identity-i18n.py` | Catch display-only labels generic scans miss. 抓一般掃描漏掉的純顯示標籤。 |
| `audit-domain-display-i18n.py` | Track display-boundary work per domain. 按領域追蹤顯示邊界翻譯。 |
| `audit-ui-message-i18n.py` | Check likely display strings against the UI PO catalog. 比對疑似顯示字串與 UI PO。 |
| `audit-i18n-input-search.py` | Audit input/search boundaries. 稽核輸入/搜尋邊界。 |
| `analyze-i18n-display-graph.py` | Build a static graph of dropdown display routing. 建立下拉顯示路由靜態圖。 |

### Stats & external import / 屬性與外部匯入

| Script | What it does / 用途 |
|---|---|
| `stats_token_po.py` | Token-based extraction/composition for stats. 屬性的 token 式抽取與組合。 |
| `compose-stats-token-candidates.py` | Compose stat translations from token PO. 用 token PO 組出屬性翻譯。 |
| `import-poecharm-po.py` | Import exact-match PoeCharm CSV translations into a PO catalog. 從 PoeCharm CSV 匯入完全相符的翻譯。 |
| `import-poecharm-ui.py` | Build a reviewable PO catalog from PoeCharm UI CSV. 用 PoeCharm UI CSV 建可審閱 PO。 |
