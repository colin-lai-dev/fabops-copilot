# Eval

評分方式見 ADR-0005；規則見 CLAUDE.md「Eval 規則」。

## 檔案

| 路徑 | 內容 | 誰寫 |
| --- | --- | --- |
| `schema.py` | 題目、系統輸出、執行紀錄的格式 | Claude Code |
| `questions.example.jsonl` | 每種題型一筆格式範例（內容是佔位文字） | Claude Code |
| `gen_rule_questions.py` | 依骨架事實產生規則題 | Claude Code |
| `split.py` | 依題型分層切 dev/test（40/60），不覆寫已存在的 test 檔 | Claude Code |
| `run.py` | 對指定 split 跑系統，存原始輸出與摘要 | Claude Code |
| `systems.py` | 受測系統（`refuse_all` 是下限 baseline） | Claude Code |
| `synonyms.py` | 事實比對用的同義詞／縮寫表 | Claude Code |
| `score.py` | 評分邏輯 | **Colin** |
| `dev/`、`test/` | 切好的題目（JSONL，一行一題） | 由 `split.py` 產生 |
| `results/` | `<run_id>.jsonl`（原始輸出，不進 git）、`<run_id>.summary.json`（進 git） | `run.py` |

## 題目格式

每行一個 JSON 物件，欄位見 `schema.py` 的 `Question`：

- `qid`：規則題 `R-<題型>-NNNN`，手寫題 `H-NNNN`。
- `qtype`：`fact`、`paraphrase`、`cross_doc`、`dirty`、`old_version`、`refuse`、`open`。
- `user_id`：以誰的身分提問。runner 查出權限範圍後另外傳給系統，**不會放進題目文字**（ADR-0001）。
- `key_facts`：回答必須包含的事實；`expected_doc_ids`：應引用、也是檢索目標的文件。
- `should_refuse`、`forbidden_facts`：應拒答的題目；回答中不得出現的字串。
- `rubric`：只有 `open` 題需要，給 judge 的評分準則。

## 流程

```powershell
uv run python -m evals.gen_rule_questions        # 產生規則題並切分（已凍結的 test 不會被覆寫）
uv run python -m evals.split evals/handwritten.jsonl   # 手寫題各自切分
make eval-dev SYSTEM=refuse_all                  # 或 uv run python -m evals.run --split dev
uv run python -m evals.run --rescore <run_id>    # score.py 改好後，重新評分已存的輸出
make eval-test                                   # 只在 gate、經 Colin 同意時執行
```

- 調參與除錯只看 `dev/`。`run.py` 只印統計數字，不印題目。
- 每個報告的數字都要標 n 與 baseline；摘要裡有 `n`、`n_by_qtype`、git commit、題目檔 hash。
