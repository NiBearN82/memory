# 尼貝爾直播紀錄館

VTuber 尼貝爾 Nibel 的直播紀錄網站：直播縮圖牆、時間軸搜尋、說書書單、議題、歌單、Shorts 精華。

網站每 4 小時（台灣時間 00:17、04:17、08:17、12:17、16:17、20:17）會自動到 YouTube 抓一次新的直播和 Shorts，有新內容才會更新。

## 第一次設定（只要做一次）

### 1. 申請 YouTube API 金鑰（免費）
1. 打開 [Google Cloud Console](https://console.cloud.google.com/)，建立一個新專案（名稱隨意，例如 `nibel-archive`）。
2. 到「API 和服務 → 程式庫」，搜尋 **YouTube Data API v3**，按「啟用」。
3. 到「API 和服務 → 憑證」，按「建立憑證 → API 金鑰」，複製金鑰。
4. 建議按「限制金鑰」，在「API 限制」只勾 YouTube Data API v3。

每天的用量大約 50 單位，免費額度是每天 10,000 單位，不會產生費用。

### 2. 把金鑰放進 GitHub
到這個 repo 的 **Settings → Secrets and variables → Actions → New repository secret**：
- Name：`YT_API_KEY`
- Secret：貼上剛剛的金鑰

### 3. 跑第一次
到 **Actions → 每日更新直播紀錄館 → Run workflow**。跑完之後網站就會更新。

## 想自己補資料的時候

人工整理的資料都在 `data/extra.json`，改完存檔，網站會自動重新產生：

| 欄位 | 內容 | 例子 |
|---|---|---|
| `books` | 說書書單 `[影片ID, 書名, 作者]` | `["AYebLRA-uQw", "人生只有兩件事…", "老楊的貓頭鷹"]` |
| `news` | 新聞久一點的專題名稱 | `"dTTdK0zDssQ": "黃仁勳離開輝達的未來"` |
| `setlists` | 歌單 `[時間, 歌名, 歌手]` | `["9:20", "怪獣の花唄", "Vaundy"]` |
| `shortCats` | Shorts 分類：`clip` 直播精華、`song` 翻唱、`topic` 議題短講 | `"zA15oPbPYZI": "topic"` |
| `shortTitles` | Shorts 在網站上顯示的標題 | |
| `shortSource` | 這支 Shorts 剪自哪一場直播 | `"NzJGNiaRYnU": "dl83b-kdftg"` |
| `hide` | 不想放進紀錄館的影片 ID | |

- 新的說書直播（標題有 `#尼看什麼`）會自動抓標題裡的《書名》。
- 新的新聞久一點會自動抓標題裡「○○專題」當作專題名稱。
- 說明欄有 3 行以上「時間 標題」的直播，會自動變成時間軸；歌回的時間軸會自動變成歌單。
- 會員限定直播用一般金鑰抓不到，原本已經收錄的會保留，新的會員場次可以手動加進 `site/data.json`。

## 檔案說明
- `site/index.html`：網站本體
- `site/data.json`：所有直播資料（自動產生，不用手動改）
- `scripts/update.py`：抓 YouTube 資料的程式
- `.github/workflows/update.yml`：每 4 小時自動執行的排程

## 封面（雲端硬碟）

1. 雲端硬碟資料夾裡開「書籍」「專輯」兩個子資料夾，檔名用書名或歌名（可加 `_作者`／`_歌手`）。
2. 資料夾連結貼到 `data/extra.json` 的 `coverFolder`。
3. 認證：GitHub Secrets 新增 `GDRIVE_SA_JSON`（服務帳戶 JSON 金鑰），並把資料夾共享給服務帳戶信箱（檢視者）。
4. 每 4 小時自動更新時會一起抓新封面，白邊會自動裁掉；雲端硬碟刪掉的圖，網站也會拿掉。

## 背景照片來源
- 書店：Pexels #1290141（Livraria Lello）
- 報攤：Pexels #36150701
- 唱片：Pexels #21821336
- 入口書架：Pexels #159711
皆為 Pexels License，可免費使用；網站上已做模糊與調暗處理。
