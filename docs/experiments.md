# 實驗紀錄

每次實驗新增一筆，最新的放最上面。只記錄實際跑出來的數字。

## 範本

### YYYY-MM-DD：<實驗名稱>

- 目的：想驗證什麼
- 設定：模型、切塊大小、top-k、是否 rerank、題目集版本、git commit
- 結果：

  | 指標 | 基準 | 本次 |
  | --- | --- | --- |
  | 檢索命中率 | | |
  | 回答正確率 | | |
  | 權限洩漏數 | | |
  | 平均延遲 | | |
  | 每次查詢成本 | | |

- 觀察：
- 下一步：

## 紀錄

### 2026-11-08：切塊實驗——異常報告整份 vs 依段落切

- 目的：檢索設定比較發現整份異常報告太長，BM25 長度正規化把含完整單號的報告排到後面；試著把異常報告也依段落切。
- 設定：同「檢索設定比較」，只改 `--incident-split`（999 個 chunk）；不 rerank。git `53b806b`。
- 結果（n = 54；基準 = 異常報告整份，399 個 chunk）：

  | 設定 | Recall@5 基準 → 本次 | MRR 基準 → 本次 |
  | --- | --- | --- |
  | dense | 0.657 → 0.602 | 0.512 → 0.451 |
  | BM25 | 0.824 → 0.787 | 0.782 → 0.769 |
  | sparse | 0.833 → 0.833 | 0.703 → 0.652 |
  | dense + BM25 | 0.861 → 0.843 | 0.750 → 0.650 |
  | dense + sparse | 0.778 → 0.704 | 0.547 → 0.553 |

  cross_doc 的 Recall@5 沒有變（dense + BM25：0.312 → 0.312，n=8）；dirty 題下降（1.000 → 0.900，n=10）。

- 觀察：切細後同一份報告的多個 chunk 互相擠占前幾名，文件層級的召回反而下降；cross_doc 的瓶頸是第二段（從報告找到 SOP），不是報告本身的長度。
- 結論：不採用，維持異常報告整份一塊（已重建回 399 個 chunk 的索引）。
- 下一步：cross_doc 留給 Phase 2 的多步查詢，或由 Colin 決定是否在檢索層加「引用展開」（`open-questions.md`）。

### 2026-11-08：檢索設定比較（dense / BM25 / sparse / hybrid / rerank）

- 目的：選定中文關鍵字檢索方式（ADR-0009），並決定是否 rerank。
- 設定：bge-m3（FlagEmbedding，CPU）、bge-reranker-v2-m3（CPU）；section 切塊（max 800 字，異常報告整份一塊），399 個 chunk；
  權限 pre-filter，排除舊版；RRF k=60；dense/lexical 各取 50 個候選；rerank 前 20 個；輸出 k=20 個 chunk 再去重成文件。
  題目：`evals/dev/rule.jsonl`（sha256 `e4a44891de9fcf17`），git `53b806b`。
  指標用暫時評分器 `evals/_interim_metrics.py`（score.py 完成後刪除），只算可回答的題目。
- 結果（n = 54；基準 = dense，也就是 PLAN 的「只用向量、不 rerank」baseline）：

  | 設定 | Recall@5 | Hit@5 | MRR | 每題延遲 mean / p95 |
  | --- | --- | --- | --- | --- |
  | dense（基準） | 0.657 | 0.704 | 0.512 | 255 / 287 ms |
  | BM25（jieba） | 0.824 | 0.833 | 0.782 | 272 / 299 ms |
  | bge-m3 sparse | 0.833 | 0.870 | 0.703 | 254 / 273 ms |
  | dense + BM25 | **0.861** | **0.889** | 0.750 | 254 / 279 ms |
  | dense + sparse | 0.778 | 0.815 | 0.547 | 260 / 290 ms |
  | dense + rerank | 0.778 | 0.796 | 0.675 | 25.7 / 28.7 s |
  | dense + BM25 + rerank | 0.815 | 0.833 | 0.689 | 24.6 / 28.2 s |
  | dense + sparse + rerank | 0.815 | 0.833 | 0.711 | 24.9 / 28.2 s |

  各題型 Recall@5（dense + BM25）：fact 0.889（n=18）、paraphrase 1.000（n=12）、dirty 1.000（n=10）、
  old_version 1.000（n=6）、**cross_doc 0.312（n=8）**。

- 觀察：
  - 不 rerank 時各設定的每題延遲都在 250–270 ms（CPU），hybrid 沒有比單路慢多少；各階段的細分這次沒有記錄。
  - rerank 在 CPU 上每題約 25 秒（20 組 query-chunk，XLM-R large 等級的模型），而且在 dev 上沒有提升 hybrid 的 Recall@5（0.861 → 0.815）。
    只改善了 dense 單獨使用時的排序。
  - cross_doc 在所有設定都很差。原因：問題只寫異常報告的單號（例如 `INC-2026-0077 那類異常…依 SOP 多久要升級？`），
    要先找到報告、再從報告中的 SOP 編號找到 SOP，是兩段式檢索；而且整份報告當成一個 chunk 時太長，
    BM25 的長度正規化把含完整單號的報告排到第 15 名左右。
  - BM25 有 1 題（拒答題 `R-REFUSE-0013`）完全沒有命中任何 chunk，因為問題中沒有語料裡出現過的詞；拒答題不計入檢索指標。
- 結論：預設用 dense + BM25、不 rerank。rerank 保留為選項（`-rerank`）。
- 下一步：試異常報告依段落切塊；GPU 上的 rerank 需要 CUDA 版 torch（要改依賴，留給 Colin 決定）。

### 2026-11-08：建立索引的耗時

- 設定：bge-m3（FlagEmbedding `BGEM3FlagModel`，CPU、fp32、batch 64），dense（1024 維）與 sparse 一次產生；
  jieba token 同時算好存進 `chunks.tokens`。i7-8700K、32 GB RAM。
- 結果：

  | 切塊方式 | chunk 數 | 載入模型 | 編碼 + 寫入 |
  | --- | --- | --- | --- |
  | section（max 800 字，異常報告整份） | 399 | 11.9 s | 215.5 s（第一次）、202.8 s（重建） |
  | section + 異常報告依段落切（`--incident-split`） | 999 | 11.4 s | 251.2 s |

- 觀察：約 0.5 秒/chunk；整個語料重建一次約 3.5 分鐘，調參實驗可以接受。

### 2026-11-08：關閉 qwen3:8b 的思考模式

- 目的：交接指示 002 要求 dev 用 qwen3:8b 時關閉思考模式，並記錄做法。
- 設定：Ollama（Windows 主機）的 OpenAI 相容端點，同一個簡短問題，比較三種做法。
- 結果：

  | 做法 | 是否有效 | 輸出 token | 延遲 |
  | --- | --- | --- | --- |
  | `reasoning_effort="none"`（請求參數） | 有效 | 6 | 0.2 s |
  | prompt 結尾加 `/no_think` | 無效（仍有約 300 個 reasoning token） | ~300 | — |
  | `extra_body={"think": false}` | 無效（同上） | ~300 | — |

- 做法：`LLM_REASONING_EFFORT=none`（`.env`）→ `config.llm_reasoning_effort` → client 帶入 `reasoning_effort`；
  這個值也是快取 key 的一部分，開關思考模式的結果不會互相污染。回應中若仍出現 `<think>…</think>` 會在解析前移除。

### 2026-11-08：LLM 潤飾實驗（不採用）

- 目的：驗證 `make polish`（ADR-0004）能否在不改壞事實的前提下，讓模板文件更像真實的工作紀錄。
- 設定：`qwen3:8b`（Ollama，本機），temperature 0.7、max_tokens 600，沿用 `polish.py` 原本的 prompt
  （沒有關閉思考模式，也沒有指定繁體中文）；資料 seed 20261108，git `b2adcbd`；在 Windows 11 執行，耗時 67 分鐘。
- 基準：模板版本（未潤飾）。
- 結果（n = 192 份文件）：

  | 指標 | 基準（模板） | 本次 |
  | --- | --- | --- |
  | 通過 `verify()` 並採用 | — | 100/192（SOP 34/42、異常報告 66/150） |
  | 錯字標記保留（有標記且已潤飾的文件） | 26/26 | 0/26 |
  | 口語開頭保留 | 38/38 | 0/38 |
  | 縮寫保留 | 39/39 | 15/39 |
  | 新增簡體字的文件（在已潤飾的文件中） | 0/100 | 8/100 |
  | 只改動目標段落、metadata 未變 | — | 是 |

- 抽查（前 → 後）：
  1. `INC-2026-0085` 現象描述：「夜班巡機的時候發現…」→「夜班巡机时發現…」；處理經過「週保養」→「周保养」。混進簡體字。
  2. `INC-2026-0032` 現象描述：「tool FX2-CVD-03 的 …-CHB…已經OOC上限，chamber暫停派貨」→「在FX2-CVD-03工具的…-CHB子系統中檢測到微粒數量超标」。
     「tool」直譯成「工具」，腔體被說成「子系統」，語意走樣，也有簡體字。
  3. `SOP-FX2-DIF-O2C-0715-v1` 目的：「規範…時的處置方式」→「針對…的狀況，制定應對措施」。這份正常。
- 觀察：
  - `verify()` 只檢查編號與數字，抓不到簡體字和語意走樣。
  - 潤飾發生在加入髒資料之後，模型會把錯字、口語開頭、縮寫「修正」掉，造成文字與
    `facts.json` 的 `dirty_tags` 不一致，會讓 Phase 1 的髒資料題失準。
  - 改寫結果比原文更書面，和 prompt 要求的「口語」相反。
- 結論：不採用，沿用模板版本（`git restore` 還原，沒有提交潤飾結果）。
- 下一步：先做 Phase 1 baseline；若模板文字讓分數失真，再用修正版流程重做（見 `open-questions.md`）。
