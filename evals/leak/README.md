# 權限洩漏測試集（Phase 1：檢索、快取、日誌三條路徑）

由 `evals/gen_leak_cases.py` 依規則產生（seed `20261109`），寫入 `evals/leak_cases.jsonl`，
以 `evals/leak.py` 執行。**分類與每類題數請 Colin 確認**；要改分類或題數，改產生器的常數後重新產生。

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
  所以 retrieval 路徑在兩個系統上預期都是 0 洩漏；這條路徑的對照要等「無 pre-filter」版本（目前沒有做）。
- Phase 2 補 agent 工具路徑時，用同樣的方式擴充（新增 `LeakPath`，同樣的三種邊界類型）。

## 執行

```powershell
uv run python -m evals.gen_leak_cases                      # 重新產生（--check 只檢查）
uv run python -m evals.leak --system rag-hybrid-bm25        # 有出口檢查
uv run python -m evals.leak --system rag-hybrid-bm25-noexit # 對照：無出口檢查
```
