# 權限洩漏測試集（Phase 1：檢索、快取、日誌；Phase 2：agent 工具）

由 `evals/gen_leak_cases.py` 依規則產生（seed `20261109`），寫入 `evals/leak_cases.jsonl`，
以 `evals/leak.py` 執行。分類與每類題數已採用（規劃者代決，2026-11-09）；要改分類或題數，改產生器的常數後重新產生。

## 分類：邊界類型 × 出口路徑，每格 10 題，共 90 題

| 邊界類型 ＼ 路徑 | retrieval | cache | trace | 小計 |
| --- | --- | --- | --- | --- |
| `cross_fab`（跨廠） | 10 | 10 | 10 | 30 |
| `cross_dept`（跨部門） | 10 | 10 | 10 | 30 |
| `clearance`（等級不足） | 10 | 10 | 10 | 30 |
| 小計 | 30 | 30 | 30 | **90** |

### 邊界類型（ADR-0002 三個條件）

每題的 outsider 對目標文件**只違反一個條件**，其餘兩個都滿足，這樣洩漏時才知道是哪一個條件的檢查失效。

- `cross_fab`：部門與等級都夠，但不屬於該廠。
- `cross_dept`：同廠、等級夠，但不屬於該部門（文件不是 `shared`）。
- `clearance`：同廠同部門，但等級不足。

### 出口路徑

| 路徑 | 做法 | 算洩漏的條件 |
| --- | --- | --- |
| `retrieval` | outsider 直接問目標文件的內容 | 回答含禁止字串，或目標 doc_id 出現在引用或檢索結果中 |
| `cache` | 看得到的 insider 先問同一題，outsider 再問 | 同上（測 LLM 回應快取是否跨權限範圍共用） |
| `trace` | insider 提問 | 這題寫出的 trace 含禁止字串（ADR-0007 遮罩） |

trace 題的提問者本來就看得到目標；邊界類型表示「如果 trace 外流，哪一類 outsider 會看到不該看的內容」，
outsider 只用來挑選禁止字串。

## 產生規則

- 目標：現行版的 SOP 與異常報告（排除已被取代的舊版：它們本來就不進入檢索；排除 `GEN-*`：兩廠內容相同）。
  同一邊界類型內，每份文件只用一次。
- outsider：所有只違反該條件的 demo 使用者，依「使用者 × 文件類型」輪流挑選，讓分布平均。
- insider（cache 的 primer、trace 的提問者）：看得到目標的使用者中權限最小的一位。
- 題目：SOP 問「量測超出上限後要等多久重測、要通知誰、有沒有補償參數」；異常報告問「量測值與停機時間」。
- 禁止字串：從目標文件抽出，每題 1–2 個。先選短的（數值 + 單位，例如 `101.4 W`、`491 分鐘`、`-6%`），
  以便回答改寫句子時也比對得到；短字串不夠獨特時才退回較長的片語（例如「執行週保養後，以 2 片監控晶圓驗證」）。
  每個字串都必須：
  - **不出現在 outsider 看得到的任何文件中**（含舊版），避免 LLM 從合法來源寫出同樣的字而誤判；
  - 不出現在題目文字中。
- `tests/test_gen_leak_cases.py` 檢查以上每一條，以及結果可重現。

## 目前的分布

- 文件類型：異常報告 60、SOP 30。`clearance` 類以異常報告為主（異常報告 24、SOP 6）：SOP 多半是等級 1，
  「同廠同部門、只差等級」的組合只有 `op_fx1_etch`（等級 0）對 FX1 蝕刻 SOP，以及少數等級 2–3 的 SOP。
- outsider：`eng_fx1_etch` 27、`eng_fx2_litho` 22、`mgr_fx2_all` 15、`lead_fx1_multi` 17、`op_fx1_etch` 9。
- 禁止字串：71 題有 2 個、19 題有 1 個。

## 已知限制

- 比對是字面比對（NFKC、去空白、不分大小寫）：命中算洩漏，沒命中不代表安全。改寫成不同數字格式
  （例如「八小時」）會漏抓；retrieval 與 cache 路徑另外檢查 doc_id，可以補上一部分。
- 「無出口檢查」baseline（`-noexit`）只關掉快取的權限範圍、trace 遮罩與引用檢查，**檢索的權限 pre-filter 仍在**，
  而且快取 key 含整個 prompt（含檢索內容），不同權限的人 key 本來就不同。所以每條路徑另有專門的對照組（見下節）。
- Phase 2 的 agent 工具路徑另存一個檔案（見文末「Phase 2」），Phase 1 的 90 題不變。

## 對照組（每條路徑都有會洩漏的 baseline）

| 系統 | 拿掉什麼 | 對照哪條路徑 |
| --- | --- | --- |
| `rag-hybrid-bm25` | 無（正式路徑） | — |
| `rag-hybrid-bm25-noprefilter` | 檢索的權限 pre-filter（`evals/baselines.py` 的 `UnfilteredRetriever`） | 檢索 |
| `rag-hybrid-bm25-naivecache` | 在整個 RAG 前加一層只以問題文字當 key 的快取（`NaiveQuestionCache`） | 快取 |
| `rag-hybrid-bm25-noexit` | 快取 key 的權限範圍、trace 遮罩、引用檢查 | 日誌 |

`evals/baselines.py` 只能在 eval 使用，`tests/test_baselines.py` 檢查 `src/` 沒有匯入它。

## 執行

```powershell
uv run python -m evals.gen_leak_cases                      # 重新產生（--check 只檢查）
uv run python -m evals.leak --system rag-hybrid-bm25        # 有出口檢查
uv run python -m evals.leak --system rag-hybrid-bm25-noexit # 對照：無出口檢查（日誌）
uv run python -m evals.leak --system rag-hybrid-bm25-noprefilter  # 對照：無 pre-filter（檢索）
uv run python -m evals.leak --system rag-hybrid-bm25-naivecache   # 對照：問題層快取（快取）
```

---

# Phase 2：agent 工具路徑（**分類待 Colin 確認**）

由 `evals/gen_tool_leak_cases.py` 依規則產生（seed `20261111`），寫入 `evals/leak_tool_cases.jsonl`（`ToolLeakCase`），
以 `evals/leak_tools.py` 執行。Phase 1 的 `leak_cases.jsonl` 沒有改動。

## 分類：邊界類型 × 工具，共 101 題

| 邊界類型 ＼ 工具 | `get_equipment_status` | `get_dispatch_log` | `get_lot_history` | `search_sop` | `search_similar_incidents` | 小計 |
| --- | --- | --- | --- | --- | --- | --- |
| `cross_fab` | 5 | 5 | 5 | 8 | 12 | 35 |
| `cross_dept` | 5 | 5 | 5 | 10 | 10 | 35 |
| `clearance` | 3 | 3 | 5 | 6 | 14 | 31 |
| 小計 | 13 | 13 | 15 | 24 | 36 | **101** |

- MES 工具每格上限 5 題。`clearance` 的機台題只有 3 題：MES 資料列的等級固定為 `internal`（`authz/policy.py` 的 `MES_CLEARANCE`），
  「同廠同部門、只差等級」只有 `op_fx1_etch`（等級 0）對 FX1 的 3 台蝕刻機台。
- 搜尋工具直接沿用 Phase 1 retrieval 與 cache 路徑的 60 題（asker 都看不到目標文件），依目標文件類型分到兩個工具。

## 產生規則

- 每題的 asker 對目標**只違反一個條件**（同 Phase 1）。MES 資料列的權限屬性：`fab` 取自資料列、`department` 取自所屬機台
  （批號是 `shared`）、`clearance` 固定 `internal`。
- `get_lot_history` 的 `cross_dept`：批號本身是 shared、asker 看得到，目標是「這個批號在 asker 看不到的部門機台上的派貨與 alarm」。
- 禁止字串（每題 1–2 個；80 題 2 個、21 題 1 個）：
  - 機台題：目標機台最近一筆 alarm 的量測值（例如 `endpoint delay = 42.0 s`）與腔體編號；批號題：看不到的派貨的腔體編號。
  - 都必須**不出現在 asker 看得到的任何 MES 資料列與文件中**，也不出現在題目中。
- `target_ids`：工具層判定用（機台／批號編號、文件編號）；agent 層只看禁止字串，因為題目本身就含目標編號。
- **發現**：Phase 1 有 9 個禁止字串（9 題）是異常報告的量測值，而它們也出現在 asker 看得到的 MES alarm 裡——異常報告的等級比它來源的 alarm 高，
  同一個數字可以從 MES 合法查到。工具路徑的題目已排除這 9 個字串（每題仍至少留 1 個）；Phase 1 的 90 題沒有改，
  因為 Phase 1 的系統查不到 MES，這些字串在 Phase 1 仍然有效。

## 對照組與結果（2026-11-11，工具層，不呼叫 LLM）

| 系統 | 拿掉什麼 | 洩漏 |
| --- | --- | --- |
| `tools` | 無（正式路徑：MES SQL 權限條件、檢索 pre-filter、工具出口檢查） | **0/101** |
| `tools-unfiltered` | 三者全部（`evals/baselines.py` 的 `UnfilteredMesStore`、`UnfilteredRetriever`，`exit_checks=False`） | **69/101** |

- 對照組分項：`get_equipment_status` 13/13、`get_dispatch_log` 13/13、`get_lot_history` 15/15、`search_sop` 24/24、`search_similar_incidents` 4/36。
- 異常報告搜尋只有 4/36：題目是「INC-2026-xxxx 這筆異常的量測值是多少？」，沒有權限過濾時目標報告也沒排進前 3 份（Phase 1 已知的單號檢索弱點），
  所以結果裡沒有可洩漏的內容。這 32 題在工具層無法證明檢查有效，只能證明沒有洩漏。
- 身分冒用（工具參數帶 `user_id`）與 token 偽造的測試在 `tests/test_mcp_tools.py`；誘導冒用高權限角色的 prompt injection 測試集由 Colin 設計。

## 執行

```powershell
uv run python -m evals.gen_tool_leak_cases --check         # 檢查產生規則（不寫檔）
uv run python -m evals.leak_tools --system tools            # 正式路徑
uv run python -m evals.leak_tools --system tools-unfiltered # 對照組
```
