# 待決問題

Claude Code 遇到 ADR 沒涵蓋的問題時記錄於此，並採用暫定做法繼續。Cody 在 gate 時決定。

| 日期 | 問題 | 暫定做法 | 替代方案 | 狀態 |
| --- | --- | --- | --- | --- |
| 2026-11-08 | **文件潤飾要不要在凍結 test set 前執行？** 潤飾會改變文件文字，題目必須以最終文件為準。 | 目前提交的是模板版本（未潤飾）。建議 Phase 1 出題前先跑 `make polish`，之後文件不再變動。 | 不潤飾，直接用模板版本（檢索分數可能偏高，要寫進已知限制）。 | **待決（Phase 1 開工前）** |
| 2026-11-08 | 機台資料表命名 | 用 `equipment`，避免和 agent 的「工具」混淆。 | 沿用 PLAN 的 `tools`。 | 暫定 |
| 2026-11-08 | Ollama 放在哪裡 | 跑在 Windows 主機上（直接用 GPU），不放進 Compose。 | 放進 Compose 並設定 GPU 直通，設定較複雜。 | 暫定 |
| 2026-11-08 | Claude 的接法（ADR-0008 留待確認） | 用 Anthropic 官方 SDK 的原生轉接層，其餘供應商走 OpenAI 相容介面。 | 走 Anthropic 的 OpenAI 相容端點，功能可能有差異。 | 暫定 |
| 2026-11-08 | 結構化輸出的做法 | 用 prompt 要求 JSON，再以 Pydantic 驗證，失敗時修正重試一次；各供應商通用。 | 改用各家原生的 JSON 模式或 tool calling，較穩定但要分別實作。 | 暫定 |
| 2026-11-08 | 機密等級分布 | restricted 等級目前只有 1 份 SOP 和 14 份異常報告。 | Phase 1 設計洩漏測試集時，若覺得不夠可調整 `generate.py` 的權重。 | 暫定 |
| 2026-11-08 | 程式不會自動載入 `.env` | 新增 `src/fabops/config.py`，以既有依賴 `pydantic-settings` 讀取 `.env`（環境變數優先）；seed、測試、LLM client 都改用它，Makefile 不再需要 `--env-file`。 | python-dotenv（要新增依賴）。 | 已解決 |
