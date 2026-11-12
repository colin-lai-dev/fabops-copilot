# Phase 4 Gate：包裝與求職

Gate 條件：他人照 README，10 分鐘內跑起來。

## 1. 完成的任務

| 任務 | 狀態 | 出處 |
| --- | --- | --- |
| README（一句話、GIF、架構圖、eval 表、快速開始、已知限制、重現方式、CI badge） | 完成 | 交接指示 010–013 |
| 3 分鐘 demo 影片、靜態回放網站 | 完成 | release `demo-v1`、GitHub Pages |
| README 快速開始的乾淨 clone 驗證 | 完成（本報告） | 本次 commit |
| **[Colin]** 履歷完整版、`/quiz` 自測 | 未完成（只能由 Colin 做） | — |
| （可選）Phase 3 交班摘要 | 未做；需規劃者決定要保留還是刪除 | PLAN Phase 3 |

## 2. 乾淨 clone 驗證（2026-11-12，Claude Code 執行）

從 GitHub 重新 clone（`d4567ef`）到暫存目錄，Compose 專案名不同（不碰開發 DB），完全照 README 的 Windows 指令執行。
主機 5432 被別的專案佔用，照 README 說明改成 `FABOPS_DB_PORT=5434` 並同步改 `DATABASE_URL`，一次就成功。

| 步驟 | 累計時間 | 結果 |
| --- | --- | --- |
| clone、`.env`、`docker compose up`、`uv sync` | 0:33 | 成功（uv 套件已有本機快取） |
| seed | 0:43 | 9135 dispatch、400 alarms、136 maintenance、192 documents |
| index（bge-m3，CPU） | 4:23 | 399 chunks，embedding 188 s |
| `pytest`／`pytest -m db` | 5:33 | 233 passed／24 passed |
| `eval-dev rag-hybrid-bm25`（qwen3:8b，空快取） | **8:55** | n=72，0 錯誤，US$0 |

dev 數字與 `experiments.md` 的 qwen3 欄位（`20261110T143530Z`）**完全一致**：回答正確率 0.826（n=69）、
引用正確率 0.769（n=65）、Recall@5 0.854（n=65）、誤拒率 0.031（n=65）、拒答率 1.000（n=7）。
本次 run_id `20261112T033617Z-dev-rag-hybrid-bm25`（只存在暫存 clone，未進 repo）。

**限制（照實說）：**
- 這台機器已有 uv 套件快取（約 1.3 GB）、bge-m3／reranker 權重（約 4 GB）、qwen3:8b（5.2 GB）。
  真正的新使用者要多下載約 10 GB，在一般網路下**很可能超過 10 分鐘**。已在 README 快速開始補上時間與下載量說明。
- 不是「他人」執行：同一台機器、由 Claude Code 照 README 操作。Gate 要求的「他人」仍需要 Colin 找人試。
- 沒有測 macOS／Linux、也沒測 `make`（這台 Windows 沒有 make）。

## 3. 建議 Colin review 的檔案

1. `README.md` 快速開始段落：新增的時間與下載量說明是否要保留。
2. 本報告第 2 節的限制：決定 gate 是否接受「快取已在」的 9 分鐘，或要等他人實測。

## 4. Eval

見第 2 節（dev，n=72；baseline 為 experiments.md 同系統同模型的既有紀錄）。未使用 test。

## 5. 待決項目

- Gate 是否以本次驗證通過，或需找他人在乾淨機器上實測。
- Phase 3 的「（可選）交班摘要」要做還是從 PLAN 刪除。
- 暫存 clone 的 Docker volume `fresh_pgdata` 留在本機（刪除 volume 被權限擋下）；不需要時可執行 `docker volume rm fresh_pgdata`。

## 6. Colin 的任務

履歷完整版與 `/quiz` 自測：未完成。
