# Phase 1 Gate 報告（進行中）

- Branch：`phase-1-rag`
- 狀態：**草稿**。eval 框架與規則題完成；停在第一個 Colin 親手項目（手寫題目）。到達 gate 時補完整份報告。

## 1. 完成的任務

| 任務 | Commit |
| --- | --- |
| 權限 policy 純函式（ADR-0002），之後的 SQL 條件以它為準 | `fa4cdcb` |
| Eval 框架：題目格式、`evals/run.py`、dev/test 分割、`score.py` stub 與測試 | `56079bc` |
| 規則題 151 題（dev 60、test 91）與語料檢查 | `75e6a8d` |

規則題分布（n = 151）：fact 45、paraphrase 30、dirty 25、cross_doc 20、old_version 16、refuse 15。
沒有 open 題，開放題只能手寫。

## 2. Colin 要做的事

| 項目 | 放在哪裡 | 說明 |
| --- | --- | --- |
| 手寫題目 | `evals/handwritten.jsonl`，寫完執行 `uv run python -m evals.split evals/handwritten.jsonl` | 格式見 `evals/questions.example.jsonl` 與 `evals/README.md`；qid 用 `H-NNNN`。split 會檢查 doc id、提問者看不看得到文件。test 要達 100 題，至少需要 15 題手寫（60% ≈ 9 題進 test）；建議 30 題左右，並包含 `open` 題。 |
| `evals/score.py` | `evals/score.py` | 介面與 `QuestionScore` 欄位可自由改。`tests/test_score.py` 是 xfail，實作後必須通過。寫好後用 `uv run python -m evals.run --rescore <run_id>` 重新評分已存的輸出。 |
| 權限洩漏測試集 | 尚未建立格式 | 待做到「出口檢查」任務前建立格式。 |
| 人工標註 50 題 | 尚未建立格式 | 待做到 judge 選擇實驗前建立格式。 |

### `score.py` 需要你決定的評分細節

`tests/test_score.py` 只釘了 ADR-0005 明確規定的情況，以下留給你決定（決定後可把案例補進測試）：

1. **多份應引用文件時的 Recall@k**：命中任一份就算 1，還是算命中比例？（cross_doc 題有 2 份）
2. **數字邊界**：答案「145 mTorr」是否算包含「45 mTorr」？單純子字串比對會誤判。
3. **正規化**：「10分鐘」vs「10 分鐘」、全形／半形數字、`mTorr` 大小寫。
4. **拒答判定**：只看系統的 `refused` 旗標，還是也從回答文字判斷？兩者不一致時以誰為準？
5. **引用正確**：要求引用到全部 `expected_doc_ids`，還是至少一份且沒有引用不相關文件？

## 3. 最該 review 的地方

1. `evals/schema.py` 的 `Question._consistent`：題目一致性規則，手寫題也受它約束。
2. `evals/run.py` 的 `run_questions`：身分只以 `Scope` 傳給系統，不進題目文字（ADR-0001）。
3. `evals/run.py` 的 `check_split_allowed`：test split 沒有 `--allow-test` 就不跑。
4. `evals/split.py` 的 `write_split`：已存在的 test 檔不會被覆寫（`--force` 才行）。
5. `evals/gen_rule_questions.py` 的 `generate`：每組（文件, 欄位）只問一次，避免同一事實換個說法同時出現在 dev 與 test。
6. `evals/corpus.py`：答得出來的題目，提問者必須看得到所有應引用文件；看不到的屬於洩漏測試集。
7. `src/fabops/authz/policy.py`：`SYSTEM_SCOPE` 一律看不到使用者資料。

## 4. Dev eval

尚無：檢索還沒做，`score.py` 尚未實作。`refuse_all` 下限 baseline 已在 dev（n = 60）上跑通，0 錯誤。
