# Path of Building 2 — 中文化（i18n）

[English README](README.md)

這是
[Path of Building 2 Community](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2)
的中文化版本。PoB2 是流亡黯道 2（Path of Exile 2）最多人用的配裝規劃工具。

- **繁體中文（`zh_TW`）** — 完整翻譯。
- **簡體中文（`zh_CN`）** — 僅部分示範，尚未完成。

![繁體中文介面截圖](docs/assets/pob2-i18n.png)

## 這個專案真正做了什麼

中文化 PoB 的難點從來不是技術，而是「量」——幾萬條詞條，沒有任何一個維護者
能獨力翻完。這完全可以理解，也正是上游一直沒做翻譯的原因。

這個 fork 解決的是真正需要工程師處理的那一塊：**把 i18n 機制（多語言框架）加
進去**，讓程式能在顯示層載入翻譯文字。一旦這個機制存在，翻譯本身就變成單純的
改文字工作，**任何用戶都能做**，任何語言都行，完全不用寫程式。

中文只是第一個示範。同一套機制為其他所有語言打開了門。我們的期望是上游能採用
這個 i18n 層，之後社群就能自己接力把各種語言填進去。

---

## 給玩家：直接下載就能用

[最新 Release](../../releases/latest) 附了一份 Windows 免安裝版。下載 `.zip`、
解壓縮、直接執行 Path of Building 就好，**不用自己編譯**。語言在程式設定裡切換。

中文化是**只翻顯示**：你看到的介面、物品、技能、天賦、屬性說明都是中文，但你的
配裝、匯入/匯出代碼、交易資料維持原本的英文，這樣才能跟原版 PoB 完全相容、互通。

---

## 給想幫忙翻譯的人：怎麼修改或更新翻譯

所有文字都放在純文字的 **PO 檔**（標準翻譯格式）裡。你不需要懂 Lua 或程式內部，
只要會改文字就能參與。

### 文字放在哪

```text
locale/zh_TW/LC_MESSAGES/    繁體中文
locale/zh_CN/LC_MESSAGES/    簡體中文（部分）

  pob.po        介面、選單、按鈕、提示
  items.po      物品名稱
  skills.po     技能 / 寶石名稱
  passives.po   天賦樹節點
  stats.po      屬性 / 詞綴文字
```

### 怎麼改翻譯

1. 用任何文字編輯器（或 Poedit 這類 PO 專用編輯器）打開要改的 `.po` 檔。
2. 找到 `msgid` 底下的英文原文，把 `msgstr` 底下的中文改成你要的：

   ```po
   msgid "Total Life"
   msgstr "總生命"
   ```

3. 存檔。

### 怎麼讓改動生效

PO 檔要編譯成程式讀取的對照表。改完後執行：

```bash
python3 scripts/compile-lang.py locale/zh_TW/LC_MESSAGES/pob.po src/Data/Lang/zh_TW/pob.lua
```

你改了哪個檔就對哪個跑（`items`、`skills`、`passives`、`stats` 同理）。若只想
檢查檔案是否最新、不實際寫入，加上 `--check`。

整個流程就這樣：**改 `.po`、跑編譯腳本、完成。** 然後重新執行程式就看得到改動。

### 把成果貢獻回來

fork 這個倉庫，把你改好的 `.po`（以及重新產生的 `.lua`）提交，然後開 pull
request。只改翻譯的 PR 很歡迎。

---

## 給開發者：自己編譯

這個倉庫**只放原始碼**——沒有編譯好的二進位檔或 DLL。你可以檢視每一處改動、
自己編譯，這正是重點：不需要盲目信任任何人給的執行檔。

`release` 分支有兩個提交：

```text
commit 1  -> 上游原版 clone（b8048682，未改動的英文版）
commit 2  -> 中文化補丁
```

看第二個提交就能看到相對乾淨原版的完整中文化 diff。補丁只動顯示層；配裝資料、
匯入/匯出內容、交易數值、計算核心都沒動。

`scripts/` 底下的輔助腳本涵蓋擷取、編譯、翻譯覆蓋率稽核，核心就是上面的
`compile-lang.py`。

---

## 上游與授權

原始專案：
[PathOfBuildingCommunity/PathOfBuilding-PoE2](https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2)。
上游擁有 Path of Building 2 Community；本專案是非官方的中文化 fork。
授權：MIT — 見 [LICENSE.md](LICENSE.md)。
