# Phase 0 Gate 報告

- 日期：2026-11-08
- Branch：`phase-0-foundation`
- 狀態：程式與測試完成；**等 Cody 在自己電腦跑 `docker compose up` 與 `make seed` 驗證**

## 1. 完成的任務

| 任務 | Commit |
| --- | --- |
| uv、ruff、pytest、Makefile、`.env.example` | `chore: initialize Python project…` |
| Postgres + pgvector（Compose）、DB schema | `feat(db): add Postgres+pgvector…` |
| 合成 MES 資料與文件產生器、seed 載入 | `feat(data): add deterministic synthetic…` |
| LLM client（供應商切換、權限範圍快取、用量紀錄）、結構化輸出範例 | `feat(llm): add provider-switching…` |
| 文件潤飾與事實檢查（選用） | `feat(data): add optional LLM polish…` |

未完成：**[Cody]** 履歷 bullet 定稿。

## 2. 架構摘要

```
world.py（虛構工廠的固定設定）
   └─ generate.py ──> data/generated/*.jsonl ──> seed.py ──> Postgres（schema.sql）
                      └─ facts.json（eval 的標準答案，不給模型看）
polish.py（選用）──> LLMClient ──> Ollama / Claude / OpenAI / Gemini
                         ├─ 快取 key 含權限範圍（authz/scope.py）
                         └─ 用量紀錄只有 token、延遲、成本，沒有內文
```

產生的資料（seed 20261108，可完全重現）：

| 項目 | 數量 |
| --- | --- |
| 機台／腔體 | 30／91 |
| 批號 | 150 |
| 派貨紀錄 | 9,135（保養中被拒的有對應規則） |
| 警報 | 400 |
| 保養紀錄 | 136 |
| SOP | 42（含 8 份舊版） |
| 異常報告 | 150（縮寫 93、錯字 55、口語 72 份有標記） |

## 3. 最該 review 的地方

1. `src/fabops/llm/client.py` 的 `cache_key()`：權限範圍如何進入快取 key。這是第一個資料出口。
2. `src/fabops/authz/scope.py`：權限範圍的表示方式，Phase 1 的 policy 會建在上面。
3. `src/fabops/data/schema.sql`：權限欄位為何同時放在 `documents` 與 `chunks`（ADR-0003）。
4. `src/fabops/data/generate.py` 的 `gen_mes()` 派貨迴圈：「保養中不得派貨」規則怎麼埋進資料。
5. `src/fabops/data/generate.py` 的 `_render_sop()`：機密等級 ≥2 的 SOP 才有「製程補償參數」段落，這是之後洩漏測試的目標。
6. `src/fabops/data/polish.py` 的 `verify()`：怎麼判定潤飾沒有改壞事實。
7. `tests/test_llm_client.py` 的 `test_cache_never_shared_across_scopes`。

## 4. 測試結果

- `make test`：20 passed
- `make test-db`（本機 Postgres 16 + pgvector）：1 passed；從零 seed 成功，DB 內無「保養中仍派貨成功」的紀錄
- 尚未呼叫任何付費模型；Ollama 相關功能只用 mock 測過

## 5. 待你決定

見 `docs/open-questions.md`。最重要的一項：**Phase 1 出題前要不要先跑 `make polish`**。

## 6. 你的任務

- [ ] 在自己電腦跑「驗證步驟」
- [ ] 履歷 bullet 定稿（Phase 1 版與完整版）

## 驗證步驟（Windows）

```powershell
cd $HOME\Desktop\fabops-copilot
copy .env.example .env
docker compose up -d
uv sync
uv run python -m fabops.data.seed
uv run pytest
uv run pytest -m db
# 選用：測試 Ollama（需先 ollama pull qwen3:8b）
uv run python -m fabops.llm.examples
```

（Windows 若沒有 `make`，可直接執行上面的指令。）
