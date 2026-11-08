# ADR-0006: Agent 的 LangGraph 結構

- 日期：2026-11-08
- 狀態：已採用

## 背景

Agent 要能多步查詢唯讀工具、產生寫入建議並等待人工核准，還要和固定 workflow 公平對照。

## 選項

| 選項 | 優點 | 缺點 |
| --- | --- | --- |
| A. 預建 ReAct agent + 寫入前 interrupt | 最快 | 流程細節藏在框架裡，難以說明與對照 |
| B. 自訂 StateGraph | 每個環節是明確節點；固定 workflow 可共用節點 | 要自己設計 state 與邊 |
| C. 多 agent supervisor | 可擴展到複雜分工 | 對本題過重 |

## 決定

選擇 B。

## 理由

明確的節點讓核准、步數上限、上下文管理都看得見、測得到；
固定 workflow 用同一組節點與寫死的邊組成，兩組對照只差在「由誰決定下一步」。

## 後果

- 節點：`agent`（LLM 決定下一步）→ `tools`（執行唯讀工具）→ `trim_context`
  → 回到 `agent`；需要寫入時 → `propose` → `approval`（interrupt）→ `execute` → `summarize`。
- 步數上限 8，超過即進入 `summarize` 並標記未完成。
- 固定 workflow：查批號 → 查機台 → 搜 SOP → 搜類似異常 → `propose`／`summarize`，共用相同節點。
- Checkpoint 存放在既有的 Postgres。
- Proposal 存入資料表（狀態、核准者、時間），以 idempotency key 確保同一建議只執行一次；
  執行結果寫入 audit log。
