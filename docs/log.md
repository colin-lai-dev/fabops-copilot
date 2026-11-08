# 開發日誌

依時間記錄進度與決策，最新的放最上面。每筆只寫「發生了什麼、決定了什麼、細節在哪」，
細節本身留在對應文件：架構決策 → `docs/decisions/`，實驗 → `docs/experiments.md`，
待決事項 → `docs/open-questions.md`，階段驗收 → `docs/gates/`，程式變更 → git log。

## 2026-11-08

- **Phase 1 檢索**：dev Recall@5 dense + BM25 0.861、dense baseline 0.657（n=54）；rerank 在 CPU 每題約 25 秒且無提升，預設關閉；
  異常報告依段落切塊不採用；cross_doc 只有 0.31（n=8）。dev 全量 RAG 執行因記憶體不足中止，待重跑。
- **規劃者代決**：ADR-0009（jieba + BM25）採用；不裝 CUDA torch；Phase 1 不加引用展開（cross_doc 留給 Phase 2 對照）；
  不改寫 `39282cc`；`.env` 加入 `LLM_REASONING_EFFORT=none`。
- **交接指示 002（進行中）**：完成 bge-m3 索引、hybrid 檢索（dense + jieba BM25，ADR-0009 提議中）、回答生成與出口檢查、
  洩漏測試／judge 標註格式；dev Recall@5 0.861 vs baseline 0.657（n=54）。rerank 預設關閉、異常報告不切段（`experiments.md`）。
  dev 全量 RAG 執行因記憶體不足被系統中止，待 Colin 指示重跑（`private/handoff/reports/2026-11-08-1908-phase1-rag-paused.md`）。
- **Phase 1 開始**：eval 框架、權限 policy 函式、151 題規則題（dev 60／test 91）完成；
  停在 Colin 的手寫題與 `score.py`（`docs/gates/phase-1.md`）。
- **規劃者代決**：ADR-0004 補「暫不潤飾」修訂；ADR-0005 補 5 條評分細節預設規則（Colin 可推翻）；
  open-questions 4 筆暫定做法確認。CC 的回報改為寫進 `private/handoff/`，Colin 不必轉貼。
- **Phase 1 開始**（交接指示 001）：`phase-0-foundation` 合併回 `main`，開 `phase-1-rag`。完成 eval 框架與 151 題規則題（dev 60、test 91），停在 Colin 的手寫題目；待辦與評分細節見 `docs/gates/phase-1.md`，待決事項見 `docs/open-questions.md`。
- **企劃定稿為 v3**：經兩輪外部審查，主軸從「功能廣度」改為「驗證深度」——eval 先凍結再調參、
  權限檢查擴大到每個資料出口（檢索、快取、工具、日誌、輸出）、加入 prompt injection 測試、
  agent 以 RAG／固定 workflow／agent 三組對照證明價值；Phase 1 gate 為硬目標。
- **開發模式**：架構決策事先定案；Claude Code 在階段內自動實作，每個 gate 停下由 Colin review。
  手寫範圍收斂為 eval 評分腳本與 agent loop 練習；測試集由 Colin 設計。
- **架構決策 ADR-0001～0008 定案**：身分由伺服器端注入、權限模型（等級＋廠區＋部門）、
  先過濾再精確搜尋、規則骨架產生合成資料、評分方式、自訂 StateGraph、trace 嚴格遮罩、模型配置。
- **Phase 0 實作完成**：專案骨架、Postgres＋pgvector、合成資料產生器、LLM client。
- **Windows 驗證**：5432 被其他專案占用，改為可設定埠（本機用 5433）；固定 Python 3.12；
  uv 以 winget 安裝；程式改由 pydantic-settings 自動讀取 `.env`。
- **LLM 潤飾實驗不採用**：成功率 52%，且洗掉髒資料、混入簡體字；沿用模板版本，
  Phase 1 baseline 若顯示模板文字讓分數失真再重做（`docs/experiments.md`）。
- **協作設定**：新增 Claude Code 權限規則（`.claude/settings.json`）與交接機制
  （使用者說「接手」即執行 `private/handoff/` 中的下一份指示）。
- 企劃 v3 定稿版存於本機 `private/planning/`（不進 git）。
- **Phase 0 gate 通過**（`docs/gates/phase-0.md`）。下一步：Phase 1，先做 eval 框架。

## 2026-11-07

- 決定以「晶圓廠異常處理 AI 助理」作為補足 RAG／agentic workflow 經驗的 side project，
  題材來自 MES 與派貨系統實務；企劃 v1 完成。
