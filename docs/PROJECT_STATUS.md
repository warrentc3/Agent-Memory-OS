# 專案狀態 (Project Status) - Agent Memory OS

本文件為 Agent Memory OS 的單一事實來源 (Single Source of Truth, SSOT)，用於追蹤專案的演進路徑、目前進度以及治理狀態。

## 🚀 演進路徑 (Evolution Path)

專案分為多個階段，旨在逐步構建一個能夠管理代理狀態與記憶的作業系統。

| 階段 | 名稱 | 狀態 | 描述 |
| :--- | :--- | :--- | :--- |
| **Phase 1** | 身份與門戶契約 (Identity & Gate Contract) | ✅ SEALED | 確立代理身份定義與記憶存取權限的基礎契約。 |
| **Phase 2.1** | 感官擴展 (Sensation Expansion) | ✅ SEALED | 擴展代理對外部數據與多模態輸入的感知能力。 |
| **Phase 2.2** | 感知工程 (Perception Engineering) | ⚠️ BASELINE ESTABLISHED | 建立感知處理基準，目前等待最終驗收 (Awaiting Acceptance)。 |
| **Phase 2.3** | 動態上下文編排 (Dynamic Context Orchestration, DCO) | ✅ VERIFIED | 實現主動的上下文快照與狀態恢復機制。基準精度已建立。 |

---

## 🎯 當前衝刺：動態上下文編排 (DCO)

DCO 旨在管理代理狀態在「活動」工作記憶（LLM 上下文窗口）與「休眠」持久記憶（Agent Memory OS）之間的移動，防止上下文溢出並確保任務切換時的無縫銜接。

### 核心目標 (Goals)
- [x] **`ContextSnapshot` 實作**：定義並實現快照結構，封裝目標、假設、關鍵變數及推理鏈。
- [x] **API 開發**：
    - [x] `offload_context`: 將當前狀態序列化並存儲至記憶庫。
    - [x] `reload_context`: 恢復指定或最新的會話快照。
- [x] **精度驗證**：確保狀態恢復後的上下文精度，無關鍵資訊丟失。

### 技術設計參考
詳細實現方案請參閱：[DCO 技術設計文件](docs/plans/20260613_dco-technical-design.md)

---

## 🛠 治理與同步 (Governance & Sync)

- **更新頻率**：每次 Sprint 結束或重大里程碑達成時更新。
- **驗收標準**：所有 `SEALED` 狀態的階段必須通過完整的集成測試且文檔完備。
- **同步路徑**：`PROJECT_STATUS.md` $\rightarrow$ 技術設計 $\rightarrow$ 實作代碼 $\rightarrow$ 驗證測試。
