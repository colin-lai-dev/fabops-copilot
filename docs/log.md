# 開發日誌

依時間記錄進度與決策，最新的放最上面。每筆只寫「發生了什麼、決定了什麼、細節在哪」，
細節本身留在對應文件：架構決策 → `docs/decisions/`，實驗 → `docs/experiments.md`，
待決事項 → `docs/open-questions.md`，階段驗收 → `docs/gates/`，程式變更 → git log。

## 2026-11-10

- **交接指示 004**（Claude Code）：Colin 的 50 題標註入檔（open 對 0／部分 5／錯 20，其他 16／1／8）；
  處置題 SOP 優先採用（ADR-0010，`sop_boost` 1.2）：open 要點命中率 校準 0.155 → 0.591（n=110 點），dev 其他題型不變；
  新增 `evals/rubric_match.py`（與標註 125/125 點一致）。**judge 選擇與 test eval 因 `.env` 沒有 API key 跳過**，花費 $0。
  細節：`docs/experiments.md`、`docs/decisions/0010-*.md`、`docs/gates/phase-1.md`。

## 2026-11-10

- **人工標註完成**：Colin 以勾選版標完 50 題，字串比對交叉檢查 152 點全部一致；open 對 0／部分 5／錯 20。
  發現 25 題處置題中 19 題回答引用異常報告摘要而非 SOP 步驟。
- **ADR-0010**：處置類問題提高 SOP 權重，open 要點命中率 dev 0 → 0.600（n=15）、校準 0.155 → 0.591（n=110 點）。
  「升級條件」仍 0/22，交接指示 005 先試 SOP 章節展開。
- judge 實驗與 test eval 因 `.env` 沒有 API key 跳過；Colin 已同意兩者的花費（judge US$1、test US$2 以內）與 test 不必停下確認。

## 2026-11-09

- **交接指示 003 完成**（Claude Code）：手寫題 31 題原樣定稿並切分；**test set 凍結於 `6ebbb5d`（110 題）**；洩漏測試補上無 pre-filter 與問題層快取兩個對照組，
  正式系統三條路徑都 0/30、各對照組 19/30（檢索）、23/30（快取）、13/30（日誌）；judge 校準題庫 22 題，標註表改以 open 題為主重做；
  rerank 在手寫題上也沒有一致提升，維持關閉；ADR-0005 加規則 6（「部分」）。細節：`docs/experiments.md`、`docs/gates/phase-1.md`。
- **交接指示 002 完成**（Claude Code）：`score.py` 實作並刪除暫時評分器；dev 全量 RAG 完成，回答正確率 hybrid 0.850 vs dense baseline 0.700（n=60）；
  洩漏測試集規則產生 90 題，有出口檢查 0/90、無出口檢查 13/90（全在 trace）；人工標註表 50 題備妥。細節：`docs/experiments.md`、`docs/gates/phase-1.md`。
- **rerank 複查**：沒有 512 token 截斷，結論不變（rerank 偏好整份異常報告）；chunk 數 8 維持；整份文件 ctx4 略好但暫不改預設，待 Colin 決定。
- 待 Colin：洩漏分類確認、切塊預設、快取 baseline 做法、標註「部分」的算法（`docs/open-questions.md`）。

## 2026-11-09

- **Phase 1 Claude Code 部分完成**：`score.py`、洩漏集 90 題、標註表 50 題。dev 回答正確率 0.850（dense + BM25）vs 0.700（dense），n=60；
  洩漏：有出口檢查 0/90、無出口檢查 13/90（全在 trace）。rerank 複查：輸入沒有被截斷，結論不變（不採用）。
- **規劃者代決**：預設切塊維持依章節（整份文件只多 2 題，屬雜訊）；補「天真快取」與「無 pre-filter」兩個洩漏 baseline，
  讓每條路徑都有對照；標註「部分」算不通過並另報寬鬆比例。手寫題 31 題 Colin 確認全部保留，交接指示 003 定稿並凍結 test。
- **協作設定**：Claude Code 改為 auto 權限模式、預設繁體中文；Remote Control 開機腳本 `private/start-remote-control.bat`。

## 2026-11-08

- **分工調整（Colin 決定）**：`score.py` 與洩漏測試集改由 Claude Code 實作、Colin review；手寫題由規劃者起草 31 題
  （`evals/handwritten.draft.jsonl`）、Colin 修改；50 題人工標註仍由 Colin 親自完成。rerank 結論待複查（是否被輸入長度截斷）。
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
