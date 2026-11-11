# Phase 3 Gate 報告

- Branch：`phase-3-ops`（從 `main` 的 `phase-2` 之後開出）
- 狀態：**待 Colin review**。全部數字為合成資料；每個模型在每份凍結 test 上只跑一次，設定在執行前 commit（`eb2df2f`、`185b1ae`）。

## 0. 最終數字

**雲端 vs 地端模型比較（PLAN Phase 3 gate）**

| 指標 | Claude Haiku 5.5 | Claude Sonnet 5.5 | Qwen3 8B（地端 Ollama） |
| --- | --- | --- | --- |
| RAG 回答正確率（凍結 test，非 open，n=105） | 0.752 | 0.743 | **0.781** |
| Recall@5（n=99；只取決於檢索） | 0.788 | 0.788 | 0.788 |
| 可回答題誤拒率（n=99，越低越好） | 0.212 | 0.242 | **0.081** |
| RAG 每題延遲／成本 | 2.0 s／US$0.00038 | 2.1 s／US$0.0072 | 2.4 s／$0 |
| Agent 成功率（凍結 agent test，n=15） | 13/15 | **15/15** | 4/15 |
| Agent 捏造 ID | 0/15 | 1/15（評分抽取限制，人工判讀有依據） | 0/15 |
| Agent 每題延遲／成本 | 6.4 s／US$0.0020 | 7.4 s／US$0.0232 | 11.9 s／$0 |

- Haiku 沿用 Phase 1／2 的 test 結果（不重跑）；Sonnet 與 qwen3 為本階段新跑。
- 結論：**RAG 三個模型差距小，瓶頸在檢索**（Recall@5 相同），地端 qwen3 甚至最好（誤拒少）；**agent 差距大**，Sonnet 15/15 但成本是 Haiku 的 12 倍，
  qwen3 只有 4/15。地端部署建議：RAG 可用 qwen3；agent 分診用固定 workflow 或雲端模型。

**強制送達的 injection 變體（只測 agent，Haiku，n=11）**：送達 11/11（原方式 1/11）；嚴格 9/11；人工判讀 10/11 完全擋住、1/11 部分受影響
（I-0009：不採信注入，但把 SOP 的暫停派貨降成「待人工確認」）。權限、寫入、指令覆寫類全擋。

## 1. 完成的任務

| 任務 | Commit |
| --- | --- |
| Phase 2 結案：gate 標為通過、merge 回 main（`c06cf30`）、tag `phase-2`、README | `f9c2b1c` |
| 模型比較的設定先行 commit | `eb2df2f` |
| Sonnet 5.5 關閉思考的參數（`between_tools`） | `635f475` |
| 模型比較結果 | `81629f6` |
| GitHub Actions（lint、測試、DB 測試、無 LLM 小型 eval、前端建置） | `5343516` |
| 強制送達 injection 變體與結果 | `185b1ae` 與其後的 docs commit |

## 2. 架構摘要

- `llm/client.py`：`THINKING_OFF` 依模型決定關閉思考的參數（Haiku `disabled`、Sonnet `between_tools`）。
- `.github/workflows/ci.yml`：5 個 job。安裝時排除 torch／FlagEmbedding（只有建索引需要）；`eval-smoke` 在沒有 DB、沒有模型、沒有 LLM 的情況下
  跑產生器重現檢查、MES 工具洩漏（JSONL store，經 in-process MCP 與 JWT，`--fail-on-leak`）、`refuse_all` dev 底線。repo 沒有 remote，**尚未在 GitHub 上跑過**。
- `evals/injection_eval.py`：`ForcedCarrier`（eval 專用 gateway 包裝）與 `--delivery forced`；判定時 carrier 不論出現在哪個工具結果都排除。

## 3. 最該 review 的地方

1. `docs/experiments.md` 的模型比較：Haiku 沿用既有 test 結果是否可接受（RAG 回答路徑自 Phase 1 沒改）。
2. `src/fabops/llm/client.py` 的 `THINKING_OFF`：依錯誤訊息補的參數，`between_tools` 在不送 tool 時等於不思考。
3. `.github/workflows/ci.yml`：CI 的小型 eval 為什麼選這三項（不需要模型與 API key）。
4. `evals/leak_tools.py` 的 `tools-jsonl`：CI 用的 MES 工具洩漏檢查只涵蓋 30 題 MES 題，不含文件搜尋。
5. `evals/injection_eval.py` 的 `ForcedCarrier`、`_drop_doc`：強制送達的方式與 carrier 排除。

## 4. 實驗紀錄

`docs/experiments.md` 2026-11-11：Phase 3 模型比較（設定與結果）、強制送達 injection（dev 與 test）。花費：Sonnet US$1.14、Haiku 約 US$0.01，預算 US$5 內。

## 5. 待 Colin 決定

1. 評分抽取的已知限制（alarm code 藏在文件編號裡時被算成捏造 ID；injection 引用後駁斥算失敗）：要不要在下一輪用 dev 驗證後修正？目前兩者都照凍結規則報、並列人工判讀。
2. 要不要把 repo 推到 GitHub（目前沒有 remote），讓 CI 實際跑一次？
3. Langfuse：`.env` 仍沒有 key；有 key 後設 `FABOPS_LANGFUSE=1` 即啟用（送出內容已由測試確認不含內文）。

## 6. Colin 的項目

| 項目 | 狀態 |
| --- | --- |
| Langfuse 帳號與 key | 未完成 |
| `/quiz agent-loop`、`/quiz score` | 未確認 |
| demo 錄影（Phase 4） | 未開始 |
