# 華語圈投稿文案

專案連結:https://github.com/yamantaka520/Agent-Memory-OS

---

## 1. HelloGitHub 投稿

> 到 https://github.com/521xueweihan/HelloGitHub 開 issue(用「我要投稿」範本),
> 或走官網投稿表單。以下對應範本欄位。

**項目地址**
https://github.com/yamantaka520/Agent-Memory-OS

**項目類別**
機器學習 / AI 工具(MCP server)

**推薦理由(一句話)**
給 AI Agent 團隊用的本地優先記憶引擎:一個 SQLite 檔就跑,不需要 LLM、不需要向量資料庫、資料不出你的機器。

**詳細介紹(150–300 字)**
Agent Memory OS 是一套完全在本機執行的 AI Agent 記憶引擎。多數同類方案都要雲端帳號、embedding/LLM 金鑰,還要架一套向量資料庫才能讓 agent「記住事情」;這個專案反過來——`pip install "agent-memory-os[mcp]"` 就能離線運作,底層只是一個 SQLite 檔(FTS5 全文檢索),預設路徑不需要任何模型。

它的設計目標是**一群 agent 協作**而不是單一 chatbot:每一條記憶都有 private / team / project / agent / global 的可見度 ACL,在讀取路徑上硬性把關,兩個 agent 可以共享專案記憶又各自保有私人筆記;還支援跨機器的聯邦同步(bundle 匯出匯入 + peer mesh),不需要中央伺服器。回憶採「關鍵字 + 關聯共振」雙軌:記憶會和一起被喚起的記憶連結、連結會隨時間衰減、回饋會強化或削弱它們。原生支援 MCP(12 個工具),另有 Web UI 與 CLI。純 Python、Apache-2.0。

---

## 2. 阮一峰《科技愛好者周刊》投稿

> 到 https://github.com/ruanyf/weekly 開 issue,標題用「[週刊投稿] ...」。
> 阮一峰偏好:一句話講清楚是什麼 + 連結,不要行銷腔。

**投稿內容**

Agent Memory OS:一個本地優先的 AI Agent 記憶引擎,整套記憶就是一個 SQLite 檔,不需要 LLM 或向量資料庫,離線可用;為多 agent 協作設計,每條記憶有 private/team/project 可見度控管,並可跨機器聯邦同步。原生支援 MCP,另有 Web UI 與 CLI。Apache-2.0 開源。

連結:https://github.com/yamantaka520/Agent-Memory-OS

---

## 3. 其他華語管道(自行斟酌,文案可重用上面的詳細介紹)

- **V2EX** → 「分享創造」節點:標題「[開源] 本地優先的 AI Agent 記憶引擎,一個 SQLite 檔搞定」
- **掘金 / 開源中國 (oschina) / SegmentFault** → 發一篇「為什麼我做了一個 local-first 的 agent 記憶引擎」,內容用下面 comparison 那篇改寫
- **少數派** → 偏應用場景:「讓 Claude Code / Cursor 跨 session 記住你的專案」
