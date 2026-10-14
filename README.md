# Dressmaker 繁體中文化補丁

把 Steam 版《Dressmaker》的官方簡體中文改成**繁體中文（台灣用語）**：

- 全部文字轉成繁中台灣用語
- 字型換成思源宋體／思源黑體 TC
- 語言選單顯示「繁體中文」
- 傳單、報紙等圖片換成繁中版，標題 Logo 改用英文版

## 安裝

1. 到 [Releases → 安裝程式](../../releases/tag/launcher) 下載 `Dressmaker繁體中文化補丁.exe`
2. 先關閉遊戲，再執行安裝程式（會自動找到 Steam 的遊戲資料夾），然後按「安裝繁體中文」
3. 進遊戲後在「選項 → 語言」選「繁體中文」

安裝程式會依照遊戲目前的 Steam 版本，從這裡自動下載對應的補丁資料（約 27 MB）。
**遊戲更新之後，等這裡出新版補丁資料，再用同一個安裝程式安裝一次就好，不用重新下載安裝程式。**

- 原始檔案會備份在遊戲資料夾的 `_zhTW_backup`，按「還原原版」可以還原
- 如果遊戲剛更新、補丁還沒跟上，安裝程式會顯示「尚未支援目前的遊戲版本」
- 只支援 Windows 的 Steam 版

## 這個 repo 的內容

補丁資料只包含**差分**：譯文、思源字型（SIL OFL 1.1）、重新製作的繁中圖片，以及「從原檔哪裡複製多少 bytes」的指令，
**不包含任何遊戲原始檔案**。原版內容（例如英文 Logo）由安裝程式在玩家電腦上，從玩家自己的遊戲檔讀取。

| 路徑 | 內容 |
|---|---|
| `translations/strings.json` | 字串表譯文：`{表: {m_Id: {sc: 簡中原文, tc: 繁中譯文}}}` |
| `tools/build.py` | 從遊戲原檔產生補丁資料（delta） |
| `tools/Dressmaker_zhTW.py` | 線上安裝程式 |
| `tools/unityfs.py` | UnityFS bundle 解壓（純 Python） |
| `tools/release.py` | 打包補丁資料、建立 Release、更新 `index.json` |
| `index.json` | 安裝程式讀取的版本清單（buildid → 補丁資料下載網址） |

## 維護：遊戲更新後

1. 準備一份新版遊戲的**未修改**檔案（Steam 驗證完整性後複製 `Dressmaker_Data`，或拿 `_zhTW_backup` 裡的原檔來補）
2. `python tools/build.py <原檔dir> <上一版 payload> <TC 字型來源 resources.assets> <out> --version X.Y.Z --buildid N`
   - 原檔沒變的項目會直接沿用上一版
   - 字串有新增或改動時，會寫出 `untranslated.json` 並停止；把譯文補進 `translations/strings.json` 後再跑一次
3. 用 `--payload <out> --cli install <遊戲dir>` 在本機測試，再進遊戲確認
4. `python tools/release.py <out> <owner/repo>`，然後 commit 並 push `index.json`

安裝程式本身的邏輯（`Dressmaker_zhTW.py`）改了才需要重新打包 exe：`pyinstaller tools/launcher.spec`。
新的 exe 不相容舊版補丁資料時，把 `index.json` 的 `min_launcher` 調高。

## 授權

- 思源宋體／思源黑體：SIL Open Font License 1.1（見補丁資料裡的 `OFL_*.txt`）
- 《Dressmaker》及其內容的權利屬於原開發商；這是非官方的玩家自製補丁
