# 開發計畫

依企劃 v3：每週 8–10 小時，約 11 週。gate 沒過就不進下一階段。
Phase 1 的 gate 是硬目標；之後的階段都是加分。

標記：**[Colin]** 由 Colin 親手寫或設計，其餘由 Claude Code 實作。

## Phase 0：基礎建置（第 1 週）

- [x] 初始化 repo：uv、pyproject、ruff、pytest、`.env.example`、Makefile
- [x] Docker Compose：PostgreSQL + pgvector、Ollama
- [x] DB schema：tools、chambers、lots、dispatch_log、alarms、maintenance、documents、chunks
  - documents 的 metadata：fab、department、clearance、version、effective_date
- [x] 合成 MES 資料產生器 `scripts/seed.py`：模擬 2–4 週，固定 random seed 可重現
  - 埋入業務規則，例如「保養中的機台不可派貨」
- [x] 合成文件：約 40 份 SOP、約 150 筆異常報告，含以下髒資料
  - 同一份 SOP 的新舊兩版（系統應回答最新版）
  - Markdown/HTML 表格（不做 PDF 解析）
  - 中英混雜的縮寫與同義詞（PM、EQP、OOC 等）
  - 錯字與口語化的異常報告
- [x] `src/fabops/llm/client.py`：OpenAI 相容介面、快取（key 含角色與權限範圍）、
      token／延遲／成本紀錄
- [x] **[Colin]** 履歷 bullet 定稿（Phase 1 投遞版與完整版，數字留空；存於本機 `private/`，不進 git）

**Gate：** 從零執行 `docker compose up` 與 `make seed` 可完整跑起來；README 有快速開始。

## Phase 1：權限感知 RAG + Eval（第 2–5 週，硬目標）

Eval 基礎先做，凍結後才開始調參。

- [x] Eval 框架：題目格式、`evals/run.py`、dev/test 分割，`score.py` 介面 stub
- [x] RAG 問答集：test 目標 100 題以上（test 110 題）（規則產生 + 手寫），題型含換句話說、跨文件、
      錯字與縮寫、問到舊版 SOP、應拒答
  - [x] 規則題 151 題（dev 60、test 91）
  - [x] 手寫題目 31 題（Claude 起草，**[Colin]** 審閱後全部保留；dev 12、test 19）
- [x] 權限洩漏測試集：直接越權 + 快取、日誌間接路徑（規則產生 90 題，分類已採用；每條路徑都有會洩漏的對照組）
- [x] `evals/score.py`（Claude Code 實作，Colin review）
- [x] **[Colin]** 人工標註 50 題（2026-11-10，`evals/judge_labels.jsonl`）
- [x] Judge 選擇實驗：以人工標註的一致率決定（ADR-0008）。採用 Gemini 3.6 Flash（嚴格一致 50/50）；GPT-5.4 mini 未比較，Colin 決定先不加 OpenAI 額度
- [x] 凍結 test set（`6ebbb5d`，見 experiments.md）
- [x] 切塊（依 SOP 章節）與 bge-m3 索引
- [x] 中文 BM25 斷詞比較（jieba vs bge-m3 sparse），結果寫 ADR（ADR-0009，已採用）
- [x] 檢索：角色 pre-filter → hybrid search → rerank（rerank 預設關閉，見 experiments.md）
- [x] 回答生成：附來源引用、優先最新版、無可用資料時拒答
- [x] 出口檢查：LLM 回應快取、trace 日誌遮罩
- [x] Baseline 實驗：只用向量、不 rerank；無出口檢查版本
  - [x] 檢索 baseline（`ret-dense`）與系統實作（`rag-dense`、`-noexit`）
  - [x] dev 全量 RAG 執行（2026-11-09 完成）
- [x] 調參實驗（只看 dev）：切塊大小、top-k、rerank
  - [x] rerank（含 2026-11-09 截斷複查）、異常報告切法（見 experiments.md）
  - [x] 切塊大小（400／1200 字無差異，改比章節 vs 整份文件）、送進 LLM 的 chunk 數（見 experiments.md；是否改預設待 Colin 決定）
- [x] 第一輪 test eval，依實際花費重估預算（2026-11-10，Haiku 5.5，110 題；Phase 1 API 花費約 US$0.29）

**Gate：** 凍結 test set 上的 RAG 數字（附 n 與 baseline）；檢索、快取、日誌三條路徑的
洩漏測試（a/N vs b/N）；履歷 Phase 1 版數字填上，開始投遞。**已通過（Colin，2026-11-11），見 `docs/gates/phase-1.md`。**

## Phase 2：Agent workflow（第 6–8 週）

- [x] Agent loop 練習（`playground/agent_loop.py`，2026-11-11 改由 Claude Code 撰寫；Colin 以 `/quiz agent-loop` 理解）
- [x] FastMCP server：查批號履歷、查機台狀態、查派貨紀錄、搜 SOP、搜類似異常（全部唯讀）（`339e749`）
- [x] 身分注入與工具出口檢查（依 ADR-0001：JWT 在 MCP HTTP 邊界驗證，工具簽章無身分參數）
- [x] LangGraph agent：最多 8 步、上下文管理（結構化壓縮）、錯誤重試與 fallback（`6896e1e`、`86919e2`）
- [x] 人工核准：LangGraph interrupt 與 checkpoint（Postgres）、audit log、冪等性、核准者規則（ADR-0006 修訂；執行為模擬）
- [x] 固定 workflow baseline 與只用 RAG baseline
- [x] Agent 情境集 24 個（規則產生；dev 9、test 15）
- [x] Prompt injection 測試集 20 題（規劃者起草、Colin 審閱全部保留；dev 9、test 11）
- [x] 洩漏測試集補上 agent 工具路徑（規則產生 90 題，正式 0/90 vs 對照 58/90；分類已採用）
- [x] Langfuse trace（內文遮罩）：程式完成、預設關閉；啟用等 Colin 的帳號 key（Phase 3 C-4）
- [x] React 前端：問答、角色切換、agent trace、核准按鈕（`6cdc355`）
- [x] 三組對照實驗：成功率、工具選擇正確率、捏造 ID 率、步數、成本（test n=15，見 `docs/gates/phase-2.md`）

**Gate：** 三組對照結果；四條路徑洩漏測試；injection 測試結果。**已通過（Colin，2026-11-11），見 `docs/gates/phase-2.md`。**

## Phase 3：上線化（第 9–10 週）

- [ ] Ollama 地端模式完整可用
- [x] 模型比較：同一個 test set，Haiku 5.5、Sonnet 5.5、Qwen3 8B 各一欄，一張表（RAG 110 題＋agent 15 題，見 experiments.md）
- [ ] GitHub Actions：lint、測試、小型 eval（mock 或地端模型）
- [ ] （可選）交班摘要；若保留，納入權限測試

**Gate：** 雲端 vs 地端比較表完成。

## Phase 4：包裝與求職（第 11 週）

- [ ] README：一句話、demo GIF、架構圖、eval 結果表、快速開始、已知限制
      （含合成資料侷限、Langfuse 雲端方案前提）
- [ ] 3 分鐘 demo 影片
- [ ] **[Colin]** 履歷完整版、面試題自測（`/quiz`）

**Gate：** 他人照 README，10 分鐘內跑起來。
