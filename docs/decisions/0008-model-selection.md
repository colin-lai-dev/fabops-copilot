# ADR-0008: 模型配置

- 日期：2026-11-08
- 狀態：已採用

## 背景

需要決定開發、test、judge 與地端各用哪個模型，在成本、品質與評分公正性之間取捨。

參考價格（每百萬 tokens，美金；第三方整理，2026 年 10 月下旬資料，實作前以官方定價頁為準）：

| 模型 | 輸入 | 輸出 |
| --- | --- | --- |
| Claude Haiku 5.5（prompt ≤100K） | 0.10 | 0.50 |
| Claude Sonnet 5.5 | 2 | 10 |
| GPT-5.4 mini | 0.75 | 4.50 |
| Gemini 2.5 Flash | 0.30 | 2.50 |

開發機：Windows/Linux，NVIDIA GPU ≥8GB。

## 選項

| 選項 | 優點 | 缺點 |
| --- | --- | --- |
| A. Haiku 5.5 主力 + 不同家族的 judge + 地端 Qwen3 | 最便宜；judge 不偏袒同家族 | 要接兩家以上 API |
| B. 全部 Claude（Haiku 開發，Sonnet 主力與 judge） | 單一廠商 | judge 與受測模型同家族，評分可能偏差 |
| C. 全部 OpenAI 或 Gemini | client 最單純 | 主力單價較高 |

## 決定

選擇 A。

| 用途 | 模型 |
| --- | --- |
| 開發除錯、dev eval | 地端 Qwen3 8B；能力不足時改用 Haiku 5.5 |
| 主力（test、demo、agent 對照） | Claude Haiku 5.5 |
| 大模型對照（test 跑一次） | Claude Sonnet 5.5 |
| Judge（開放題） | GPT-5.4 mini 與 Gemini 3.6 Flash 二選一，以 50 題人工標註的一致率決定（2026-11-10 修訂，見下方） |
| 地端比較 | Qwen3 8B（Ollama） |

## 理由

Haiku 5.5 的價格讓主力模型不必降級成小模型；judge 選不同家族以降低自我偏好，
「依一致率挑選 judge」本身也是一個可報告的實驗。

## 後果

- 預估一輪完整 test：Haiku 約 US$0.5、Sonnet 約 US$8（粗估，Phase 1 後以實際花費更新）。
  整個專案預算預估 US$20 以內，API 後台仍設每月硬上限。
- LLM client 需支援：OpenAI 相容端點（OpenAI、Gemini、Ollama）與 Claude
  （原生 adapter 或 Anthropic 的 OpenAI 相容端點；實作前確認功能差異，例如 prompt caching）。
- 8GB GPU 上，Qwen3 8B（Q4）與 bge-m3、bge-reranker 會互搶顯示記憶體：
  embedding 與 rerank 可改在 CPU 執行，或與 LLM 錯開執行。若 8B 跑不動，改用 Qwen3 4B 並記錄。
- 模型名稱與版本寫在設定檔，experiments.md 每筆紀錄都要標註。

## 修訂（2026-11-10）：judge 候選換成 Gemini 3.6 Flash

Colin 決定（交接指示 006）。

- **Gemini 2.5 Flash 已無法呼叫**：官方已棄用（2026-12-01 起轉給 3.5 Flash-Lite），這把 key 呼叫一律 404。
  Colin 指示改用 Gemini 3.5 Flash；但官方的棄用頁說明 `gemini-3.5-flash` 的請求會自動轉給 `gemini-3.6-flash`，
  為了讓紀錄與實際執行的模型一致，**直接指定 `gemini-3.6-flash`**（與打 3.5 端點是同一個模型）。
  價格（官方定價頁，2026-11-10 查）：輸入 $0.75、輸出（含 thinking）$3.75／每百萬 tokens，2027-01-01 起加倍。
- **GPT-5.4 mini 待補**：OpenAI 帳號目前沒有額度（429）。Colin 加額度後，只對同一份 50 題標註跑校準，依一致率二選一。
- **選 judge 只看校準一致率，不看 test 分數**。若最後選 GPT-5.4 mini，對已存的 test 輸出重新評分即可，不重跑系統。
- 兩者都不是 Claude，仍符合「judge 與受測模型不同家族」的理由。
