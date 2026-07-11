<p align="center">
  <img src="https://raw.githubusercontent.com/yamantaka520/Agent-Memory-OS/main/assets/agent-memory-os-logo-integrated-v2.png" alt="Agent Memory OS" width="560">
</p>

<p align="center">
  <a href="https://pypi.org/project/agent-memory-os/"><img src="https://img.shields.io/pypi/v/agent-memory-os?color=4F46E5" alt="PyPI"></a>
  <a href="https://pypi.org/project/agent-memory-os/"><img src="https://img.shields.io/pypi/pyversions/agent-memory-os" alt="Python"></a>
  <a href="https://github.com/yamantaka520/Agent-Memory-OS/actions"><img src="https://img.shields.io/github/actions/workflow/status/yamantaka520/Agent-Memory-OS/ci.yml?branch=main&label=CI" alt="CI"></a>
  <a href="https://hub.docker.com/r/yamantaka520/agent-memory-os"><img src="https://img.shields.io/docker/pulls/yamantaka520/agent-memory-os?color=2496ED&logo=docker&logoColor=white" alt="Docker Pulls"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="License"></a>
  <a href="https://glama.ai/mcp/servers/yamantaka520/Agent-Memory-OS"><img src="https://glama.ai/mcp/servers/yamantaka520/Agent-Memory-OS/badges/score.svg" alt="Glama score"></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <b>繁體中文</b>
</p>

一套**在地優先(local-first)、為 AI-agent 團隊打造的記憶系統**——不只是給單一 agent 一份記憶,而是為協同工作的**一群** agent 提供共享記憶織網:private、team、project 分層的記憶都在一道硬性 ACL 之後,配上關聯式召回,以及讓多節點(連同其組織結構)保持一致的聯邦同步。一個 SQLite 檔、零必要依賴、Apache-2.0。

<p align="center">
  <a href="#為什麼">為什麼</a> · <a href="#與其他方案的定位差異">定位比較</a> · <a href="#安裝">安裝</a> · <a href="#快速上手">快速上手</a> · <a href="#功能特色">功能</a> · <a href="#聯邦多主機同步">聯邦</a> · <a href="#web-主控台">Web&nbsp;主控台</a> · <a href="docs/USER_GUIDE.md">使用手冊</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/yamantaka520/Agent-Memory-OS/main/assets/console-demo.gif" alt="AgentMemoryOS web 主控台 — 儀表板、瀏覽、關聯圖" width="820">
  <br><sub>內建 web 主控台:依 agent/team/project 的 token 用量、記憶瀏覽、ACL 安全的關聯圖。</sub>
</p>

## 為什麼

真正的工作發生在**一群 agent 組成的團隊**裡——一個專案可能同時混用 Claude Code、Codex、OpenClaw 與數個 Hermes 設定檔,橫跨多個 team 與 project,在一台或多台機器上。它們需要把**對的知識**分享給**對的隊友**,同時把該保密的留在私有範圍:

- **每個 agent 自己的記憶**是地板而非天花板:跨 session 存活的事實、偏好、程序與教訓。
- **team 與 project 記憶**才是重點:一個 team 看得到 `team:<id>` 記憶;一個 project(team 的子集)看得到 `project:<id>` 記憶;跨界不外洩。成員資格是一等公民、可管理,並驅動 ACL。
- **聯邦**讓整個 mesh 保持誠實:記憶**與**組織結構(teams/projects/成員)在節點間收斂,所以 `project:<id>` 在每個節點都代表同一件事。
- **在地優先**避開了雲端記憶平台在延遲、成本與隱私上的取捨——記憶存在本機的 SQLite 檔裡,每個 prompt 只拿到相關、經預算裁切的那一片。

## 功能特色

- **在地優先、零依賴核心**——一個 SQLite 檔(FTS5),不需 server。`pip install` 就能跑。
- **teams 與 projects 為一等公民**——team 是節點成員的集合;project 的成員是其 team 的子集。`team:<id>` 記憶送達整個 team,`project:<id>` 記憶只到該 project——一道硬性 ACL,可在主控台/CLI/API 管理。移除成員即時重新界定召回範圍;刪除範圍即撤銷其記憶。
- **跨節點聯邦,配上真正的信任模型**——可攜 bundle + peer 同步,讓記憶、關聯、設定檔**與組織結構**(teams/projects/成員)以 last-writer-wins + tombstone 收斂。每個 peer 的 policy(`shared`/`full`/`team:`/`project:`)是一道**強制授權範圍**:一個 peer 只能主張自己範圍內的成員資格,且只能*縮小*記憶可見度、不能放大——bundle 無法造成跨範圍提權。
- **會傳播的撤銷**——一個獨立的 ACL 時鐘把事後的 share/revoke 帶過整個 mesh,所以撤銷存取會真的在已同步該記憶的 peer 上收回——且不擾動衰減時鐘。
- **依請求者判定的 ACL**——每個 agent 都有 private、agent、team、project、global 記憶;可見度是排序**之前**就執行的硬性閘門,不是軟性分數。候選索引只回傳 ID,內容一律穿過閘門重新讀取。
- **動態 context pack**——每個 prompt 都做 token 預算內、可稽核的記憶挑選(`context_pack_report()` 解釋每一筆的納入/排除決策)。
- **真相仲裁**——重複抑制、矛盾偵測(`CONFLICT` 標記),並為核心記憶保留預算。
- **關聯式召回(resonance)**——一張具權威性的 `memory_links` 圖,讓相關記憶即使沒有共同關鍵字也能浮現;走訪是 ACL 安全的(看不見的節點無法被走訪)。
- **Hebbian 強化**——一起被召回的記憶會長出更強的連結(`record_recall`,或 context pack 上的 `auto_reinforce=True`);沒幫助的召回會弱化連結與信心(`helpful=False`)。
- **每個 agent 的召回設定檔**——不同 agent 人格對記憶類型有不同權重(工程師偏重 `procedure`,陪伴型偏重 `preference`);設定檔存在資料庫,只重新加權排序,絕不繞過 ACL。
- **記憶生命週期**——指數/線性衰減、釘選、硬性到期,以及寫入側的 `consolidate()`,合併重複並把高度共同召回的叢集綜合成概念記憶。
- **可選 sidecar**——語意向量候選(turbovec)、MCP server、FastAPI Web UI,全都在 extras 之後;每個候選都重新併回 SQLite 並通過硬性閘門才會被使用。

## 與其他方案的定位差異

多數 agent 記憶系統為「LLM 驅動的抽取 + 託管規模」而優化。AgentMemoryOS 優化的是另一個點:**在地優先、團隊分層、可聯邦**——由你自己運行、在一群 agent 間以硬性 ACL 共享的記憶。這是**定位**比較(架構層面,不是跑分);每一列請以各專案的最新文件為準。

| | **AgentMemoryOS** | Mem0 | Zep / Graphiti |
|---|---|---|---|
| **怎麼跑** | 一個 SQLite 檔,`pip install` | 自架(需設定 LLM + 向量庫)或託管 | Zep Cloud,或在 Neo4j/FalkorDB 上自架 Graphiti |
| **核心需要 LLM** | **不需要**(FTS5 + 可選本地向量) | 需要(LLM 抽取,如 gpt-5-mini) | 需要(LLM 建構時序圖) |
| **外部服務** | **不需要** | LLM API + 向量庫 | 圖資料庫 + LLM + embedding(自架需 3+ 個系統) |
| **範圍 / ACL 模型** | private / agent / **team / project** / global——排序前硬性閘門 | 依 user / agent / session id | 依 user / session 圖 |
| **跨節點聯邦** | **有**——記憶**與**組織結構收斂;撤銷會傳播 | 集中式儲存 | 集中式(Cloud 或你的圖資料庫) |
| **內建 MCP server** | **有** | 透過 SDK | 透過 SDK |
| **授權 / 自架** | Apache-2.0,完全開源 | 開源核心;圖與進階功能為付費層 | Community Edition 已停止維護;自架 = 裸用 Graphiti |

Mem0 與 Zep 在 LLM 抽取與託管規模召回上很強——那些正是 AgentMemoryOS 刻意不做的。當你想要一份**依賴輕、由你擁有、能在一群 agent 間正確共享、離線照跑、按你的條件同步**的記憶時,就選 AgentMemoryOS。

## 安裝

```bash
pip install 'agent-memory-os[full]'    # 建議:全部(Web UI、MCP、turbovec)
```

或挑選零件:`agent-memory-os`(核心,零依賴)、`[api]`(Web UI)、`[mcp]`(MCP server)、`[semantic]`(turbovec 向量召回)。

**Docker:** 預建的 multi-arch 映像就是完整的 AgentMemoryOS(web console + MCP server + CLI);第一個參數決定模式:

```bash
docker run -p 8000:8000 -v amos-data:/data yamantaka520/agent-memory-os        # web console(預設)
docker run -i --rm yamantaka520/agent-memory-os mcp                            # stdio MCP server
docker run --rm -v amos-data:/data yamantaka520/agent-memory-os check          # 任何 CLI 指令
```

或 `docker compose up -d`。主控台在 http://localhost:8000,記憶持久化在 volume。詳見 [Docker 指南](docs/DOCKER.md)(Docker Hub 映像 + 雙節點同步 mesh)。

需要 Python 3.11+ 且具備 SQLite FTS5(標準 CPython 建置皆內含)。

安裝後,執行兩個指令:

```bash
agent-memory doctor          # 驗證 FTS5、turbovec 與其他 extras
                             # (加 --install 自動補齊缺少的)
agent-memory token create    # 用 bearer token 保護 Web UI API
```

Token 存在 `<home>/web_token`(權限 600);`agent-memory-web` 會自動讀取,主控台首次使用時會提示輸入。之後用 `agent-memory token show|rotate|disable` 管理。

## 快速上手

```python
from agent_memory_os import MemoryClient, RecallProfile

client = MemoryClient(home="~/.agent-memory")

# 寫入記憶,帶擁有者與可見度
client.add("User prefers dark mode.", owner="mizuki", type="preference",
           visibility=[])                      # 僅擁有者私有
client.add("Deploy target is port 8000.", owner="neo", type="environment",
           visibility=["global"])              # 每個 agent 可見

# 依請求者判定的搜尋:每個 agent 只看得到它能看的
hits = client.search("deploy port", requester_agent_id="neo")

# 為 prompt 做 token 預算內的 context pack,並閉合強化迴路
pack = client.context_pack("deploy port", requester_agent_id="neo",
                           max_tokens=1200, auto_reinforce=True)

# 關聯記憶;有連結的記憶會在未來召回中共鳴浮現
a = client.add("Staging deploy failed with database lock.", visibility=["global"])
b = client.add("Always snapshot before schema changes.", visibility=["global"])
client.link(a.id, b.id, relation="caused_by", weight=0.8)

# 持久化 agent 人格:對每種記憶類型的軟性排序偏好
client.save_profile(RecallProfile(agent_id="neo",
                                  type_weights={"procedure": 1.5, "note": 0.7}))

# 定期整理:合併重複、綜合概念記憶
client.consolidate()
```

## 架構

```text
query
  -> candidate providers (FTS5 | vector sidecar | resonance graph | fallback)
  -> merge/dedupe by stable memory_id
  -> rejoin authoritative rows from SQLite
  -> ACL hard gate -> expires_at hard gate
  -> scoring (relevance x importance x confidence x freshness x reinforcement)
  -> per-agent profile re-weighting (soft)
  -> truth arbitration + context budget allocation
```

設計不變式:

- SQLite `memories` 表是唯一真相來源;FTS/向量索引是可拋棄、可重建的(`rebuild_indexes()`)。
- 候選 provider 只回傳 ID 與分數——內容一律穿過 SQLite、在 ACL 與到期硬性閘門之後重新讀取。
- 關聯邊(`memory_links`)是權威資料,能撐過索引重建、閒置時衰減,且絕不讓一筆看不見的記憶橋接兩筆看得見的。

完整合約見 [SPEC.md](SPEC.md)。

## 儲存引擎:SQLite + turbovec

AgentMemoryOS 使用**兩個權威性嚴格不同的儲存層**:

- **SQLite**(永遠開啟)是唯一真相來源:記憶、連結、設定檔與 FTS5 詞彙索引全存在一個 `memories.db` 檔裡。
- **turbovec**(隨 `[full]` / `[semantic]` 安裝)是語意向量引擎:一個記憶體內的量化索引,以語意而非關鍵字召回記憶。它刻意是**可拋棄的**——只回傳候選 `memory_id` 與分數;每個候選都重新併回 SQLite、通過 ACL/到期硬性閘門後內容才可用,而索引可隨時丟棄重建,不動到真相庫。

語意召回開箱即用:

```python
client = MemoryClient(home="~/.agent-memory", semantic="auto")
```

`semantic="auto"` 會接上一個自我同步的 turbovec 索引,底層是內建的確定性雜湊 embedder(不需下載模型;對錯字與詞形變化容忍)。記憶表一變動索引就自我重建,後端未安裝時則靜默降級為詞彙 + resonance 召回。要更深的語意,把任意 embedding 模型透過 `TurbovecSemanticCandidateProvider.from_vectors(...)` 接上你自己的 `embed_query`。`agent-memory doctor` 會確認後端可匯入。

## 記憶生命週期與保留

```bash
agent-memory retention               # 歸檔已到期 + 閒置達 4 個半衰期的記憶
agent-memory retention --half-lives 0   # 只歸檔已到期
agent-memory check                   # SQLite + FTS + 連結圖完整性
```

被歸檔的記憶完全退出召回,但仍可還原(Web UI → Tools → Retention & archive,或 `POST /api/archive/{id}/restore`)。釘選與權威軌記憶絕不因衰減被歸檔。資料庫透過版本化、只前進的 migration 表自我遷移(`agent-memory check` 會回報 schema 版本)。

## 備份與還原

```bash
agent-memory backup ~/backups/memories-$(date +%F).db --keep 14   # 輪替,保留 14 份
agent-memory restore ~/backups/memories-2026-07-11.db --force
```

備份使用 SQLite 的線上備份 API,所以即使 agent 正在寫入也一致。`--keep N` 會輪替掉同名系列的舊備份(且**絕不會**刪到正在使用的資料庫)。可拋棄索引在還原後自動重建。

**升級與健康檢查。** `agent-memory update` 會檢查 PyPI、升級並重啟執行中的主控台;`--check` 只回報。把健康檢查指向 `GET /healthz`(200/503),Prometheus 抓取指向 `GET /metrics`。

## 多 agent 專案

一個專案可對單一儲存混用 **Claude Code、Codex、OpenClaw 與多個 Hermes 設定檔**。在主控台的 **Agents** 分頁或透過 API,把每個 agent 連同它的 teams 註冊——team 成員便自動看得到 `team:<project>` 記憶,不需額外接線:

```bash
curl -X POST localhost:8000/api/agents -H 'content-type: application/json' \
  -d '{"id": "cc-main", "kind": "claude-code", "teams": ["apollo"]}'
```

或把整支艦隊宣告為程式碼——`<home>/agents.toml` 在每次開啟儲存時重新套用(檔案列出的 agent 以檔案為權威;手動註冊的 agent 不受影響):

```toml
[agents.cc-main]
kind = "claude-code"
teams = ["apollo", "shared-infra"]   # 多個 team = 多個 project

[agents.hermes-neo]
kind = "hermes"
teams = ["apollo", "ops"]
```

每個 MCP server 用 `AGENT_MEMORY_AGENT_ID` 宣告身分,所以記憶預設以該 agent 為擁有者,每次召回都帶著它的 team ACL。用 `agent-memory sync export apollo.jsonl --team apollo` 把一個專案的共享記憶送到另一台主機。

## 聯邦(多主機同步)

```bash
# 每台主機一次性設定
agent-memory peers add http://other-host:8000 --peer-token <他們的 token>

# 與每個已註冊的 peer 收斂(pull + push,確定性合併)
agent-memory sync auto
```

Peer 依 home 各自儲存;`sync auto`(或主控台的「Sync mesh now」)與每個 peer 雙向收斂——記憶與設定檔 last-writer-wins、連結 strongest-wins——不可達的 peer 個別失敗、絕不致命。檔案 bundle(`sync export/import`)涵蓋氣隙移轉。搭配 `agent-memory service install` 與一個 cron/timer 條目即可持續 mesh 同步。

## Agent 整合

把 AgentMemoryOS 接進常見 agent 的逐步指南——點一下圖磚:

<p>
  <a href="docs/integrations/claude-code.md"><img src="assets/integrations/claude-code.svg" alt="Claude Code 整合指南" height="56"></a>
  <a href="docs/integrations/codex.md"><img src="assets/integrations/codex.svg" alt="Codex 整合指南" height="56"></a>
  <br>
  <a href="docs/integrations/openclaw.md"><img src="assets/integrations/openclaw.svg" alt="OpenClaw 整合指南" height="56"></a>
  <a href="docs/integrations/hermes-agent.md"><img src="assets/integrations/hermes-agent.svg" alt="Hermes Agent 整合指南" height="56"></a>
</p>

任何支援 MCP 的 agent 都能用同一套模式:把 `python -m agent_memory_os.mcp_server` 當成 stdio MCP server 執行,指向一個共享的 `AGENT_MEMORY_HOME`。

## MCP server

<a href="https://glama.ai/mcp/servers/yamantaka520/Agent-Memory-OS"><img width="380" height="200" src="https://glama.ai/mcp/servers/yamantaka520/Agent-Memory-OS/badges/card.svg" alt="Glama 上的 AgentMemoryOS MCP server"></a>

```bash
pip install 'agent-memory-os[mcp]'
python -m agent_memory_os.mcp_server
```

工具(11 個):`memory_add`、`memory_search`、`memory_context_pack`、`memory_orchestrate_context`、`memory_link`、`memory_update`、`memory_recall_feedback`、`memory_consolidate`、`memory_offload_context`、`memory_reload_context`、`memory_snapshot_diff`。設定 `AGENT_MEMORY_AGENT_ID`,讓每個 agent 以自己的身分行動。

## Web 主控台

```bash
pip install 'agent-memory-os[api]'
agent-memory-web --host 127.0.0.1 --port 8000 --home ~/.agent-memory-web
```

主控台支援 **English、繁體中文、简体中文、日本語、한국어**——依瀏覽器自動偵測,可在頁首切換。內建統計儀表板(scope/type/relation 分佈、14 天活動、最常召回的記憶)、搜尋與近期瀏覽(記憶卡片可就地編輯、回饋、連結與刪除)、互動式關聯圖檢視、附每筆決策的 context-pack 預覽,以及 add/link/consolidate 工具——全都由全域「acting as」身分驅動。右下角有版號徽章。

端點:health/stats/dashboard/integrity · 記憶 CRUD + 瀏覽 · search / context-pack / orchestrate · links + graph · 召回回饋 · share / revoke / audit · consolidate / retention / archive+restore · agents 註冊 · peers + mesh 同步 · bundle export/import · owner 清除。完整表格見[使用手冊](docs/USER_GUIDE.md)。

Search、browse、graph、召回回饋與 context-pack 都接受 `requester_agent_id`,並執行與 SDK 相同的 ACL 硬性閘門。沒有請求者的請求以不受限的 admin 檢視執行——請只綁定 localhost,或用 `--token <secret>`(或 `AGENT_MEMORY_WEB_TOKEN`)在每條 API 路由上要求 bearer token。

注意:把 `--home` 資料庫放在本機磁碟。網路檔案系統(NFS/SMB)可能讓 SQLite FTS5 建 schema 時出現 `database is locked`。

### 以登入服務執行(macOS / Linux / Windows)

```bash
agent-memory service install [--host 127.0.0.1] [--port 8000]
agent-memory service status | start | stop | restart | uninstall
```

`install` 會把主控台註冊到原生服務管理器,登入時自動啟動、失敗時重啟——macOS 用 launchd LaunchAgent、Linux 用 systemd user unit、Windows 用工作排程器登入工作。不需管理員權限;服務以它被安裝時的那個 Python 環境執行,日誌寫到 `<home>/logs/web.log`。Linux 上若要無登入也能開機啟動,執行 `loginctl enable-linger $USER`。加 `--dry-run` 預覽動作。CI 在 Ubuntu、macOS、Windows 上以 Python 3.11–3.13 跑完整測試套件。

## 授權

Apache-2.0。詳見 [LICENSE](LICENSE)。
