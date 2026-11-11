# Phase 2 Gate 報告

- Branch：`phase-2-agent`（已合併回 `main`，tag `phase-2`）
- 狀態：**已通過（Colin，2026-11-11）**。全部數字為合成資料（虛構 Fab-X）；test 只跑一次，設定在執行前 commit（`7baeda1`）。

## 0. 最終數字（test，Claude Haiku 5.5）

**三組對照：agent 情境 test（n=15；規則產生，dev 9 題另計）**

| 指標 | 只用 RAG | 固定 workflow | Agent |
| --- | --- | --- | --- |
| 成功率 | 4/15（27%） | **15/15（100%）** | 13/15（87%） |
| 　多步推理（n=6） | 0/6 | 6/6 | 4/6 |
| 　資料矛盾（n=4） | 0/4 | 4/4 | 4/4 |
| 　應拒絕給建議（n=5） | 4/5 | 5/5 | 5/5 |
| 工具選擇正確 | — | 15/15 | 12/15 |
| 捏造 ID（回答／引用／建議中有未依據的編號） | 0/15 | 0/15 | 0/15 |
| 平均工具呼叫（步數） | 0 | 3.47 | 2.73 |
| 平均 LLM 呼叫 | 1.0 | 1.0 | 3.73 |
| 每題成本／延遲 | US$0.00044／1.9 s | US$0.00092／4.1 s | US$0.00196／6.4 s |

解讀：需要 MES 資料的 10 題，單次 RAG 全錯；兩種工具流程都大幅勝出。固定 workflow 與 agent 的差距（2 題）在 n=15 的雜訊內，
但方向和 dev（fixed 8/9、agent 9/9）相反，**不能宣稱 agent 比固定流程好**；agent 的成本約是固定流程的 2.1 倍。

**四條路徑洩漏（a/N 正式系統 vs b/N 拿掉該路徑檢查的對照組）**

| 路徑 | 正式 | 對照 |
| --- | --- | --- |
| 檢索 | **0/30** | 19/30（無 pre-filter） |
| LLM 回應快取 | **0/30** | 23/30（問題層快取） |
| trace 日誌 | **0/30** | 13/30（無遮罩） |
| agent 工具（MES + 文件搜尋，經 MCP + JWT） | **0/90** | 58/90（無 MES 權限條件、無 pre-filter、無工具出口檢查） |
| 合計 | **0/180** | 113/180 |

前三條以現行程式、qwen3:8b 重跑正式系統確認（`20261111T031255Z`）；對照組數字是 2026-11-09 的結果。洩漏集不是盲測集（見已知限制）。

**Prompt injection test（n=11；規劃者起草、Colin 審閱全部保留）**

| 系統 | 通過（嚴格，凍結規則） | carrier 送達 | 人工判讀：抵擋住 |
| --- | --- | --- | --- |
| 只用 RAG | 9/11 | 11/11 | 11/11 |
| 固定 workflow | 9/11 | 10/11 | 11/11 |
| Agent | 10/11 | 1/11 | 11/11 |

嚴格判定的 5 個失敗全是「誤導程序」類：回答照 SOP 寫出暫停派貨與等待時間，並明確說注入內容不可信、與 SOP 衝突，但因為引用了那句話而被字面比對抓到。
權限類（越權讀取、冒用角色、外洩）三組全部通過。agent 幾乎不去讀異常報告，所以它的 10/11 多半沒有真的被攻擊到。

## 1. 完成的任務

| 任務 | Commit |
| --- | --- |
| FastMCP server、5 個唯讀工具、JWT 身分注入（ADR-0001）、工具出口檢查 | `339e749` |
| 洩漏集補 agent 工具路徑（規則產生）與工具層 runner | `63a9014`、`40ed1d6`（MES 改 public 後重產 90 題） |
| LangGraph StateGraph：8 步上限、重試／fallback、interrupt 核准、Postgres checkpoint、audit log、冪等 | `6896e1e` |
| 固定 workflow 與只用 RAG baseline、agent 情境集 24 題、三組對照 runner；結構化上下文壓縮 | `86919e2` |
| 核准者規則（ADR-0006 修訂）、`MES_CLEARANCE = 0`、開發 DB 測試資料清除 | `40ed1d6` |
| Prompt injection 測試集（20 題）與隔離 DB runner | `fb01be4` |
| Langfuse 匯出（只送遮罩後欄位；預設關閉） | `7eed77e` |
| FastAPI 後端與 React 前端（問答、角色切換、trace、核准） | `6cdc355` |
| test 設定先行 commit、test 結果、gate 報告、agent loop 練習 | `7baeda1`、本報告所在 commit |

## 2. 架構摘要

```
瀏覽器（web/，React）─Bearer session token─▶ FastAPI（api/app.py）
  └ token → user_id → users 資料表 → Scope（伺服器端；請求內容與 LLM 都不能指定身分）
  ├ mode=rag   ─▶ Phase 1 Answerer
  └ mode=agent|fixed ─▶ AgentService.ask ─▶ LangGraph（agent/graph.py）
        planner（agent：LLM 決定；fixed：腳本）─▶ tools ─▶ trim_context ─▶ planner …（≤ 8 次）
        └ tools 經 McpGateway（另簽一張 MCP JWT）─HTTP─▶ FastMCP（mcp_server/server.py，JWTVerifier）
              └ MesTools：PgMesStore（SQL 權限條件）＋ Retriever（pre-filter）＋ 再一次 visible() 出口檢查
        propose（目標必須出現在工具結果、種類相符）─▶ approval（interrupt）
  決定：POST /api/proposals/{id}/decision ─▶ AgentService.decide（核准者規則）─▶ approval 節點再檢查
        ─▶ execute（compare-and-set，只執行一次，模擬）─▶ summarize（引用只限搜尋工具回傳的文件）
  agent_proposals／agent_audit_log／checkpoints 都在同一個 Postgres
Tracer：只寫遮罩欄位到 .cache/traces.jsonl；FABOPS_LANGFUSE=1 且有 key 時同樣內容送 Langfuse
```

## 3. 最該 review 的地方

1. `src/fabops/mcp_server/server.py` 的 `build_server.current_scope`：身分只從 token 來，工具簽章沒有身分參數；再驗一次自己的 claims。
2. `src/fabops/mcp_server/tools.py` 的 `_out` 與 `_search`：第二道出口檢查；查不到與無權限回覆相同。
3. `src/fabops/mcp_server/store.py` 的 `VIEWS`：MES 資料列的權限屬性怎麼來（批號是 shared、部門取自機台、等級 public）。
4. `src/fabops/agent/graph.py` 的 `propose`：目標必須出現在工具結果、種類必須和動作相符——捏造 ID 0/15 主要靠這裡。
5. `src/fabops/agent/proposals.py` 的 `approval_problem`、`execute_once`：核准者三條規則與「只執行一次」的 compare-and-set。
6. `src/fabops/agent/graph.py` 的 `trim_context` 與 `compact`：從「砍到 300 字」改成保留編號與狀態的結構化壓縮，dev 上修好 agent 的失敗。
7. `src/fabops/agent/graph.py` 的 `decide`：LLM 失敗的重試為什麼要改 prompt（快取會回同一個壞答案）。
8. `src/fabops/api/app.py` 的 `current_user`、`pending`、`decide`：前端唯一的身分來源與核准入口。
9. `evals/agent_eval.py` 的 `score_scenario`：「成功」與「捏造 ID」的定義。
10. `evals/injection_eval.py` 的 `action_violations` 與 `Carrier`：forbidden_actions 怎麼判、carrier 只能寫入 `fabops_injection`。

## 4. Dev eval 與實驗紀錄

`docs/experiments.md` 2026-11-11 各筆：dev 三組對照（Haiku agent 9/9、fixed 8/9、RAG 2/9；qwen3:8b 1/9、2/9、1/9；n=9）、工具洩漏、injection dev（qwen3）、test 設定與結果。
Phase 2 的 Haiku 花費約 US$0.15（本日合計 US$0.146，含 dev 除錯；預算 US$5）。

## 5. 待 Colin 決定（`docs/open-questions.md`；2026-11-11 規劃者已決定，見 log）

2026-11-11 的 11 項已由規劃者代決或確認。本次新增、需要決定的：

1. **injection 的字面判定**：引用注入句來駁斥它也算失敗（5/5 個嚴格失敗都是這種）。要不要改成「否定語境不算」？若改，先在 dev 驗證，再重跑 test（會是第二次 test，要註明）。
2. **固定 workflow 在 test 上勝過 agent**：履歷與 README 要怎麼寫三組對照（建議照實寫「工具流程大幅勝過單次 RAG；fixed 與 agent 差距在雜訊內，agent 成本約 2 倍」）。
3. **agent 很少讀異常報告**（injection 送達 1/11）：要不要另做一組「強制送達」的 injection 變體，專門測 agent 讀到注入文字時的反應。
4. Langfuse 尚未啟用（`.env` 沒有 key）：開好帳號後在 `.env` 加 `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY` 與 `FABOPS_LANGFUSE=1`；送出內容已由 `tests/test_langfuse.py` 確認不含內文。

## 6. Colin 的項目

| 項目 | 狀態 |
| --- | --- |
| Agent loop 練習 | Claude Code 已寫好 `playground/agent_loop.py`（CLAUDE.md 2026-11-11 調整）；**請跑 `/quiz agent-loop`** |
| Prompt injection 測試集 | 規劃者起草、Colin 審閱全部保留；已切分並執行 |
| Langfuse 帳號 | 未完成（程式已備妥、預設關閉） |
| 前端 demo 錄影 | 未開始；`make web-build` 後 `make api`，開 http://127.0.0.1:8000 |
| review `score.py`、`/quiz score`（Phase 1 留下） | 未確認 |

## 7. 履歷版本 B 可填的數字

- 「以檢索、快取、日誌、agent 工具 **4 條路徑**的洩漏測試驗證出口檢查：各路徑洩漏數 **0/30、0/30、0/30、0/90**（拿掉檢查的對照組為 **19/30、23/30、13/30、58/90**）」
- 「以 LangGraph 與 MCP 實作唯讀 MES 工具的 agent 分診流程，寫入經人工核准並留 audit log；以 RAG／固定 workflow／agent 三組對照（n=15），
  成功率 **27% / 100% / 87%**，平均步數 **0 / 3.5 / 2.7**，每題成本 **US$0.0004 / 0.0009 / 0.0020**；三組捏造 ID 皆 **0/15**」
- RAG（Phase 1，n=110 凍結 test）：Recall@5 **78.8% vs 68.2%**（dense baseline）、回答正確率 **75.2% vs 65.7%**、每題 **2.0 秒、US$0.0004**。
- Prompt injection（n=11）：權限類攻擊三組全擋；嚴格判定 9–10/11，人工判讀 11/11（見第 0 節說明，建議寫人工判讀時要註明）。
- 平均延遲與成本目前來自本機 usage log，不是 Langfuse；Langfuse 啟用後可改寫成「以 Langfuse trace 量化」。
