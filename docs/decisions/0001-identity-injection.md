# ADR-0001: 使用者身分如何傳到 agent 工具

- 日期：2026-11-08
- 狀態：已採用

## 背景

Agent 透過 MCP 呼叫唯讀 MES 工具，每個工具都必須依使用者權限過濾結果。
如果使用者身分是 LLM 可以填寫的工具參數（例如 `role="admin"`），藏在異常報告裡的
prompt injection 就能讓模型自行升權，所有出口檢查都會失效。

限制：身分不能出現在 LLM 可控的任何地方（工具參數、prompt 內容）；
要能在本機 Docker Compose 跑；設定不能太重，每週只有 8–10 小時。

## 選項

| 選項 | 做法 | 優點 | 缺點 |
| --- | --- | --- | --- |
| A. MCP HTTP + 簽章 token | FastAPI 依登入的 demo 使用者簽發短效 JWT；agent 的 MCP client 以 HTTP header 帶上；MCP server 驗證 token 後解析角色，工具從請求 context 取得身分 | 身分在 MCP 邊界被強制驗證，最接近正式環境；面試好講 | 要處理 token 簽發與驗證，多約 1–2 天 |
| B. 同一行程，由框架設定帶入 | Agent 與工具在同一個 Python 行程，身分放在 LangGraph 的 run config，工具從 config 讀取 | 最簡單 | MCP 只是包裝層，身分沒有在 MCP 邊界驗證，「用了 MCP」的說服力較弱 |
| C. 每位使用者一個 MCP 連線 | 以 stdio 啟動每位使用者專屬的 MCP server 行程，身分放在環境變數 | 隔離簡單直觀 | 一人一個行程，不符合實際部署 |

## 建議

選 A。共通規則（不論選哪個）：

- 工具函式簽章不含任何身分參數，LLM 無從指定角色。
- 工具在伺服器端依身分過濾結果；結果只回傳使用者有權看的內容。
- Injection 測試集加入「要求模型以 admin 身分呼叫工具」的案例，驗證無法升權。
- Token 只在記憶體與 HTTP header 中傳遞，不寫入 trace 日誌。

## 決定

選擇 A：MCP 走 HTTP，由 FastAPI 簽發短效 JWT，MCP server 驗證後解析身分。

## 理由

身分在 MCP 邊界被強制驗證，而不是信任呼叫端；這最接近正式環境的做法，
也讓「使用 MCP」不只是包裝層。多出的 1–2 天工作量可以接受。

## 後果

- Phase 2 需要：token 簽發（FastAPI）、MCP client 帶 header、MCP server 驗證與
  取得身分的機制。實作前確認所用 FastMCP 版本的驗證 API。
- Demo 不做完整登入，以預設的幾個 demo 使用者切換角色，切換時重新簽發 token。
- 簽章金鑰放 `.env`；token 不寫入 trace 與日誌。
- 若未來改成多服務部署，可改用正式的 OAuth 流程，工具端的身分取得方式不需改變。
