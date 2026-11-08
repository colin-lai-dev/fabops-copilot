# Phase 1 Gate 報告（進行中）

- Branch：`phase-1-rag`
- 狀態：**草稿**。檢索、回答生成、出口檢查與 baseline 已完成；其餘任務都卡在 Colin 的手寫／設計項目（見第 2 節）。到達 gate 時補完整份報告。

## 1. 完成的任務

| 任務 | Commit |
| --- | --- |
| 權限 policy 純函式（ADR-0002），之後的 SQL 條件以它為準 | `fa4cdcb` |
| Eval 框架：題目格式、`evals/run.py`、dev/test 分割、`score.py` stub 與測試 | `56079bc` |
| 規則題 151 題（dev 60、test 91）與語料檢查 | `75e6a8d` |
| ADR-0005 預設評分規則釘成 xfail 測試 | `02d56c5` |
| 依賴：FlagEmbedding、jieba（Colin 2026-11-08 同意） | `4247432` |
| 切塊（SOP 依章節，chunk 帶文件標頭） | `d12ac14` |
| SQL 權限條件由同一個 policy 產生，DB 測試比對兩者一致 | `476df27` |
| bge-m3 索引（dense + sparse 一次產生，jieba token） | `7063982` |
| 檢索：權限 pre-filter → dense + BM25/sparse → RRF → 選用 rerank | `8b0d785` |
| LLM client：`reasoning_effort`、快取讀取時核對 scope | `daef8da` |
| trace 遮罩出口（本機 JSONL，ADR-0007） | `e037071` |
| 回答生成（引用、拒答、出口檢查）＋ seed 測試改用 `_test` DB | `39282cc`（兩件事混在同一個 commit，見 open-questions） |
| RAG 系統與 baseline（`rag-dense`、`-noexit`） | `53b806b` |

規則題分布（n = 151）：fact 45、paraphrase 30、dirty 25、cross_doc 20、old_version 16、refuse 15。
沒有 open 題，開放題只能手寫。

## 2. Colin 要做的事

| 項目 | 放在哪裡 | 說明 |
| --- | --- | --- |
| 手寫題目 | `evals/handwritten.jsonl`，寫完執行 `uv run python -m evals.split evals/handwritten.jsonl` | 格式見 `evals/questions.example.jsonl` 與 `evals/README.md`；qid 用 `H-NNNN`。split 會檢查 doc id、提問者看不看得到文件。test 要達 100 題，至少需要 15 題手寫（60% ≈ 9 題進 test）；建議 30 題左右，並包含 `open` 題。 |
| `evals/score.py` | `evals/score.py` | 介面與 `QuestionScore` 欄位可自由改。`tests/test_score.py` 是 xfail，實作後必須通過。寫好後用 `uv run python -m evals.run --rescore <run_id>` 重新評分已存的輸出。 |
| 權限洩漏測試集 | `evals/leak_cases.jsonl` | 格式 `LeakCase`（retrieval／cache／trace 三條路徑），範例 `evals/leak.example.jsonl`，說明見 `evals/README.md`；執行 `uv run python -m evals.leak --system …`。 |
| 人工標註 50 題 | `evals/judge_labels.jsonl` | 格式 `JudgeLabel`（run_id、qid、passed），範例 `evals/judge_labels.example.jsonl`；要先有 dev 全量 RAG 輸出可標。 |

`score.py` 的 5 條評分細節已由 ADR-0005 的預設規則定下（規劃者代決，Colin 可推翻），`tests/test_score.py` 已改成對應的 xfail 案例。

## 3. 最該 review 的地方

1. `evals/schema.py` 的 `Question._consistent`：題目一致性規則，手寫題也受它約束。
2. `evals/run.py` 的 `run_questions`：身分只以 `Scope` 傳給系統，不進題目文字（ADR-0001）。
3. `evals/run.py` 的 `check_split_allowed`：test split 沒有 `--allow-test` 就不跑。
4. `evals/split.py` 的 `write_split`：已存在的 test 檔不會被覆寫（`--force` 才行）。
5. `evals/gen_rule_questions.py` 的 `generate`：每組（文件, 欄位）只問一次，避免同一事實換個說法同時出現在 dev 與 test。
6. `evals/corpus.py`：答得出來的題目，提問者必須看得到所有應引用文件；看不到的屬於洩漏測試集。
7. `src/fabops/authz/policy.py`：`SYSTEM_SCOPE` 一律看不到使用者資料。

## 4. Dev eval

檢索（暫時評分器 `evals/_interim_metrics.py`，score.py 完成後刪除；dev 可回答題 n = 54）：

| 設定 | Recall@5 | Hit@5 | MRR |
| --- | --- | --- | --- |
| dense（baseline：只用向量、不 rerank） | 0.657 | 0.704 | 0.512 |
| dense + BM25（預設） | 0.861 | 0.889 | 0.750 |

cross_doc 只有 0.312（n = 8），需要兩段式檢索。完整比較、rerank 與切塊實驗見 `docs/experiments.md`。
回答品質要等 `score.py`；dev 全量 RAG 執行在 2026-11-08 因系統記憶體不足被中止，10 題 smoke run 正常（0 錯誤，平均 3.7 s/題）。
