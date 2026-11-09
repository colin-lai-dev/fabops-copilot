# Phase 1 Gate 報告（進行中）

- Branch：`phase-1-rag`
- 狀態：**草稿**。test set 已凍結；Claude Code 能做的任務都已完成，剩下的都要等 Colin（第 6 節）。到達 gate 時補上 test set 數字。

## 1. 完成的任務

| 任務 | Commit |
| --- | --- |
| 權限 policy 純函式（ADR-0002），之後的 SQL 條件以它為準 | `fa4cdcb` |
| Eval 框架：題目格式、`evals/run.py`、dev/test 分割 | `56079bc` |
| 規則題 151 題（dev 60、test 91）與語料檢查 | `75e6a8d` |
| ADR-0005 預設評分規則釘成測試 | `02d56c5` |
| 依賴：FlagEmbedding、jieba（Colin 2026-11-08 同意） | `4247432` |
| 切塊（SOP 依章節，chunk 帶文件標頭） | `d12ac14` |
| SQL 權限條件由同一個 policy 產生，DB 測試比對兩者一致 | `476df27` |
| bge-m3 索引（dense + sparse 一次產生，jieba token） | `7063982` |
| 檢索：權限 pre-filter → dense + BM25/sparse → RRF → 選用 rerank | `8b0d785` |
| LLM client：`reasoning_effort`、快取讀取時核對 scope | `daef8da` |
| trace 遮罩出口（本機 JSONL，ADR-0007） | `e037071` |
| 回答生成（引用、拒答、出口檢查）＋ seed 測試改用 `_test` DB | `39282cc`（兩件事混在同一個 commit；依決定不改寫歷史） |
| RAG 系統與 baseline（`rag-dense`、`-noexit`） | `53b806b` |
| 洩漏測試與標註的格式、洩漏 runner | `caa9953` |
| rerank 預設關閉 | `d13c1a8` |
| **`evals/score.py`**（ADR-0005 與修訂 5 條規則；刪除暫時評分器） | `6f2a97d` |
| `-ctxN`：送進 LLM 的 chunk 數實驗 | `e4e40cd` |
| **權限洩漏測試集**（規則產生 90 題） | `ef570a8` |
| **人工標註表**（50 題，不含判斷） | `986446d` |
| 執行摘要的 git 狀態改在開始時記錄 | `42e0075` |
| 標註「部分」：嚴格為主、另報寬鬆比例（ADR-0005 規則 6） | `1b10aae` |
| **手寫題 31 題定稿並切分；test set 凍結（110 題）** | `6ebbb5d`、`4dc3306` |
| 洩漏對照組：無 pre-filter、問題層快取（eval 專用） | `1d4ebee` |
| judge 校準題庫（22 題 open，不進 dev/test） | `46a5bac` |
| 標註表重做（open 題逐點判斷、手機版） | `bc1a975` |

## 2. 架構摘要

```
問題 + user_id ─(runner 查出 Scope，ADR-0001)─▶ Retriever
  Retriever：sql_filter(scope) pre-filter ─▶ dense（pgvector 精確搜尋）＋ BM25（jieba）─▶ RRF ─▶（選用 rerank）
  Answerer：前 8 個 chunk 當資料放進 prompt ─▶ LLMClient（快取 key 含 scope 與整個 prompt）─▶ JSON
            ─▶ 出口檢查（引用必須是這次檢索到、且 scope 看得到的文件）─▶ Tracer（只存 id、hash、長度）
評分：evals/run.py ─▶ evals/score.py（每題 QuestionScore，彙總時每個指標都帶 n）
洩漏：evals/gen_leak_cases.py ─▶ evals/leak_cases.jsonl ─▶ evals/leak.py（三條路徑 a/N）
```

## 3. 最該 review 的地方

1. `evals/score.py` 的 `contains_fact`、`_boundary_ok`、`_variants`：規則 2、3（數字邊界、正規化、同義詞雙向替換）。
   句尾英文句點不算小數點，這是我加的判斷（測試 `test_contains_fact_trailing_decimal_point_is_not_a_number_boundary`）。
2. `evals/score.py` 的 `score_question`：`answer_ok` 的定義（事實題＝未拒答且含全部關鍵事實；拒答題＝有拒答且未洩漏；open 題留給 judge），
   以及沒有引用時精確率記為 None 而不是 0。
3. `evals/score.py` 的 `_REFUSAL_PHRASES`：只影響 `refusal_mismatch`，用語表是依 qwen3 實際輸出補的。
4. `evals/gen_leak_cases.py` 的 `eligible_pairs` 與 `distinctive`：「只違反一個條件」與「禁止字串不出現在 outsider 看得到的任何文件」。
5. `evals/leak/README.md`：分類與題數，**請確認**。
6. `evals/label_sheet.py` 的 `select`：50 題怎麼抽（最大餘數法，每個題型至少 1 題）。
7. `src/fabops/llm/client.py` 的 `cache_key`：洩漏測試顯示 key 含整個 prompt 本身就隔開了不同權限（見第 4 節）。
8. `evals/run.py` 的 `run_questions`：身分只以 `Scope` 傳給系統，不進題目文字（ADR-0001）。

## 4. Dev eval（只看 dev；test 已凍結、尚未執行）

**test set 已凍結**於 `6ebbb5d`：110 題（規則 91 + 手寫 19），各檔 sha256 見 `experiments.md`。

dev（2026-11-09 稍早，規則題 n = 60：可回答 54、應拒答 6），qwen3:8b（地端，$0）。基準 = `rag-dense`（PLAN 的「只用向量、不 rerank」）。

| 指標 | 基準 `rag-dense` | 預設 `rag-hybrid-bm25` |
| --- | --- | --- |
| 回答正確率（n=60） | 0.700 | **0.850** |
| 引用正確率（n=54） | 0.648 | **0.741** |
| Recall@5（n=54） | 0.657 | **0.861** |
| MRR（n=54） | 0.512 | 0.750 |
| 應拒答題的拒答率（n=6） | 1.000 | 1.000 |
| 可回答題的誤拒率（n=54） | 0.056 | 0.037 |

加入手寫題後的 dev（72 題）預設系統：回答正確率 0.826（n=69，不含 open）、Recall@5 0.854（n=65）；手寫題非 open 6/9。

- cross_doc 回答正確率只有 0.250（n=8），需要兩段式檢索，依決定留給 Phase 2 的三組對照。
- **洩漏測試（N=90，每條路徑 30）**：

  | 路徑 | 正式系統 | 無出口檢查 | 無 pre-filter | 問題層快取 |
  | --- | --- | --- | --- | --- |
  | 檢索 | **0/30** | 0/30 | **19/30** | 3/30 |
  | 快取 | **0/30** | 0/30 | 16/30 | **23/30** |
  | 日誌 | **0/30** | **13/30** | 0/30 | 0/30 |

  粗體對照格 = 專門拿掉該路徑檢查的 baseline。沒洩漏的對照題都已確認原因（目標文件不在檢索結果中），見 `experiments.md`。
- 調參：rerank 在規則題與手寫題上都沒有一致提升，維持關閉；送 8 個 chunk；維持依章節切塊。
- 細節與所有數字：`docs/experiments.md` 2026-11-08、2026-11-09 各筆。

## 5. 待 Colin 決定（`docs/open-questions.md`）

002 回報的 5 項已由規劃者代決（2026-11-09）。目前沒有新的待決事項。

## 6. Colin 的項目

| 項目 | 狀態 |
| --- | --- |
| 手寫題定稿 | **完成**（31 題全部保留；test 凍結） |
| review `score.py`，跑 `/quiz score` | 未完成 |
| 人工標註 50 題（`evals/labels/label-sheet.md`；手機版 `private/label-sheet-mobile.md`；填完 `uv run python -m evals.label_sheet parse`） | 未完成；卡住 judge 選擇實驗 |
| Judge 選擇實驗（GPT-5.4 mini vs Gemini 2.5 Flash） | 要標註完成，且要呼叫付費模型（需 Colin 同意） |
| 第一輪 test eval（`make eval-test`） | gate 時、經 Colin 同意 |
