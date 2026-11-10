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

### 2026-11-10：judge 選擇實驗與 test eval——未執行（沒有 API key）

- 交接指示 004 第 3、4 點。以 `fabops.config` 檢查（只看有無，不讀值）：`ANTHROPIC_API_KEY`、`OPENAI_API_KEY`、`GEMINI_API_KEY` 三個都沒有設定。
- 依指示：judge 選擇實驗跳過；test eval 需要 Haiku 5.5 與選出的 judge，同樣跳過，**沒有改用其他模型代替，test set 沒有執行**。
- 實際花費：US$0（本日所有 LLM 呼叫都是地端 qwen3:8b）。

### 2026-11-10：處置題 SOP 優先（只用 dev 與校準題庫）

- 目的：交接指示 004 第 2 點。標註發現 25 題 open 中 19 題回答的是異常報告的摘要句，沒有 SOP 的具體步驟。
- 設定：校準題庫 22 題（sha256 `d45ca6f29fb82abb`）＋ dev 72 題（sha256 `658c0a21051cb765`，open 3 題）；section 索引；qwen3:8b（地端，$0），
  送 8 個 chunk，rerank 關閉。執行時 git `67007b7`＋未提交的 `sop_boost` 程式（同一天以 ADR-0010 的 commit 提交，其他程式未變）。
  **未使用 test。** 對照（不 boost）的回答與標註當下的輸出（`20261109T052815Z-calibration-*`）22/22 題逐字相同（LLM 快取），
  所以對照組就是 Colin 標過的那份輸出。
- 評分：open 題用 `evals/rubric_match.py`（要點關鍵詞比對：數字＋單位、通知對象、保養類型）。它在標註當下的輸出上和 Colin 的判斷
  **125/125 點、25/25 題一致**。它不判斷語意（提到但說錯抓不到），只當 judge 之前的代理指標。
- 量化（open 題 n=25，不 boost）：

  | 指標 | 值 |
  | --- | --- |
  | 應引用 SOP 的 Recall@5（文件層） | 25/25 |
  | 檢索前 5 名文件中 SOP 的比例 | 36/125 = 0.288（其餘為異常報告） |
  | 送進 LLM 的 8 個 chunk 中 SOP 的比例 | 85/200 = 0.425 |
  | SOP「4. 處置步驟」chunk 在 8 個 chunk 內 | **13/25** |
  | 「處置步驟」＋「5. 升級條件」都在 8 個 chunk 內 | 2/25 |

  → 問題不在找不到 SOP，而在切塊層：異常報告整份一塊、字面重疊多，把 SOP 的步驟章節擠出 context。
- 改法（只動排序）：問題含「怎麼處理／如何處置／處置步驟……」時（`is_disposal_query`），SOP chunk 的 RRF 分數乘以權重，再取前 8 個。
  切塊層比較（open 題 n=25）：

  | 做法 | 處置步驟在 context | 步驟＋升級條件 | 8 個 chunk 中 SOP 數 |
  | --- | --- | --- | --- |
  | 不 boost | 13/25 | 2/25 | 85/200 |
  | SOP ×1.2 | **25/25** | 13/25 | 167/200 |
  | SOP ×1.5 | 25/25 | 16/25 | 196/200 |
  | SOP ×2 | 25/25 | 16/25 | 199/200 |
  | SOP 4 + 報告 4 | 20/25 | 0/25 | 100/200 |
  | SOP 5 + 報告 3 | 22/25 | 7/25 | 125/200 |
  | SOP 6 + 報告 2 | 23/25 | 11/25 | 150/200 |

  選 ×1.2（讓步驟全部進入 context 的最小權重），端到端比較：

  | 指標 | 不 boost | SOP ×1.2 |
  | --- | --- | --- |
  | 校準 open：要點命中率（n=110 點） | 0.155 | **0.591** |
  | 校準 open：整題 對／部分／錯（n=22） | 0／5／17 | 0／21／1 |
  | 校準 open：逐點命中（要點 1～5，各 n=22） | 2、5、5、5、0 | 9、21、19、16、0 |
  | dev open：要點命中率（n=15 點） | 0.000 | **0.600** |
  | dev 回答正確率（非 open，n=69） | 0.826 | 0.826 |
  | dev 引用正確率（n=65） | 0.769 | 0.769 |
  | dev Recall@5（n=65） | 0.854 | 0.854 |
  | dev MRR（n=65） | 0.729 | 0.758 |
  | dev 輸入 tokens（72 題） | 152,661 | 149,801 |

  dev 非 open 題沒有任何一題的 answer_ok、citation_ok 或 Recall@5 改變。
  run_id：`20261110T101017Z-calibration-rag-hybrid-bm25`、`20261110T101157Z-calibration-rag-hybrid-bm25-sop1.2`、
  `20261110T101231Z-dev-ret-hybrid-bm25`、`20261110T101305Z-dev-ret-hybrid-bm25-sop1.2`、
  `20261110T101339Z-dev-rag-hybrid-bm25`、`20261110T101435Z-dev-rag-hybrid-bm25-sop1.2`；
  改為預設後重跑 `20261110T101547Z-calibration-*`、`20261110T101622Z-dev-*`，數字相同。
- 觀察：
  - 嚴格通過率仍是 0（n=22）：第 5 點「升級條件」兩版都是 0/22。升級條件在另一個章節，boost 後只有 13/25 題進入 context，
    而且進入了 qwen3 也沒寫出來。
  - 數值判讀錯誤（把超標判成「未超過上限」）兩版各 1 題，但不是同一題（不 boost：C-OPEN-0015 46 ppm；boost：C-OPEN-0002 13.8 %），
    屬於 qwen3:8b 的不穩定，與檢索無關；要點比對抓不到這類錯誤，要靠 judge。
  - 要點 1（確認是否保養中＋暫停派貨）只有 9/22：模型常略過「確認是否在保養中」。
- 結論：**採用，設為預設**（ADR-0010）。`rag-dense` 等 baseline 維持不 boost。升級條件與多章節湊齊的問題留給 Phase 2。

### 2026-11-10：人工標註 50 題（judge 校準）

- 流程（交接指示 004）：Colin 用勾選版逐點回答「有／沒有」，規劃者換算：有 → `有`，沒有 → `漏`；整題全部「有」= 對、全部「沒有」= 錯、
  其餘 = 部分。Colin 沒有區分「漏」與「錯」（提到但內容不符），一律記為「漏」。盲標後規劃者以字串比對（關鍵數字、角色、保養類型）
  檢查每一點，與 Colin 的判斷全部一致，因此沒有複查項目。（規劃者記為 152 點；標註表中 open 題的逐點欄位是 25 題 × 5 = 125 點，
  `evals/rubric_match.py` 同樣是 125/125 一致。）
- 標註對象：`20261109T052815Z-calibration-rag-hybrid-bm25`（22 題）與 `20261109T052916Z-dev-rag-hybrid-bm25`（28 題），qwen3:8b。
  `uv run python -m evals.label_sheet parse` → `evals/judge_labels.jsonl`，50 題全部解析成功。
- 結果：

  | 題型 | 對 | 部分 | 錯 | n |
  | --- | --- | --- | --- | --- |
  | open | 0 | 5 | 20 | 25 |
  | 其他題型 | 16 | 1 | 8 | 25 |
  | 全部 | 16 | 6 | 28 | 50 |

  嚴格通過率 0.320、寬鬆 0.440（n=50）。open 逐點：有 17／漏 108（n=125）。
- 已知限制：單一標註者、非製程背景、「漏」與「錯」未區分。

### 2026-11-09：rerank 在手寫題上再驗證（只用 dev）

- 目的：交接指示 003 補充第 9 點。手寫題有口語、開放的問法，看 rerank 是否在這類題目上有幫助。
- 設定：dev（72 題，sha256 `658c0a21051cb765`，含手寫 12 題）；section 索引；`ret-hybrid-bm25` vs `ret-hybrid-bm25-rerank`
  （bge-reranker-v2-m3，CPU，前 20 個 chunk），以及對應的 `rag-*`（qwen3:8b，送 8 個 chunk）。git `bc1a975`（工作目錄只有文件修改）。
- 結果：

  | 子集 | 指標 | 不 rerank | rerank |
  | --- | --- | --- | --- |
  | 手寫題 | Recall@5（n=11） | **0.818** | 0.727 |
  | 手寫題 | MRR（n=11） | **0.627** | 0.557 |
  | 手寫題 | 回答正確率（非 open，n=9） | 0.667（6/9） | 0.778（7/9） |
  | 手寫題 | 引用正確率（n=11） | **0.909** | 0.727 |
  | 規則題 | Recall@5（n=54） | **0.861** | 0.815 |
  | 規則題 | 回答正確率（n=60） | 0.850（51/60） | 0.883（53/60） |
  | 全部 | 每題延遲（RAG） | 0.6 s | 24.4 s |

  手寫題逐題 Recall@5 有變的 5 題：變差 3 題（open H-0004 1 → 0、paraphrase H-0010 1 → 0、cross_doc H-0017 1 → 0.5），
  變好 2 題（dirty H-0024 0 → 1、cross_doc H-0022 0 → 0.5）。
- 觀察：檢索指標在手寫題上一樣變差，模式和規則題相同（整份異常報告擠掉 SOP 章節）；回答正確率多 1 題（手寫）、2 題（規則），
  在雜訊範圍內，而且引用正確率下降。沒有任何題型出現一致的提升。延遲是 40 倍。
- 結論：**維持 rerank 預設關閉**，不改成依題型選擇性採用（open-questions 的 rerank 那一列不變）。

### 2026-11-09：權限洩漏測試——每條路徑都有會洩漏的對照組

- 目的：交接指示 003 第 3 點。2026-11-09 稍早的結果中，檢索與快取路徑在 baseline 也是 0 洩漏，對照沒有意義；
  新增兩個 eval 專用 baseline（`evals/baselines.py`），讓每條路徑都有會洩漏的對照組。
- 設定：`evals/leak_cases.jsonl`（90 題，sha256 見 summary）；section 索引；qwen3:8b；四個系統依序執行。
  git：`rag-hybrid-bm25`、`-noexit` 為 `1d4ebee`，`-noprefilter`、`-naivecache` 為 `bc1a975`（中間只改了文件與標註表，系統程式相同）。
- 結果（每格 = 洩漏題數／該路徑題數；錯誤 0）：

  | 路徑 | 正式系統 `rag-hybrid-bm25` | 無出口檢查 `-noexit` | 無 pre-filter `-noprefilter` | 問題層快取 `-naivecache` |
  | --- | --- | --- | --- | --- |
  | 檢索（n=30） | **0/30** | 0/30 | **19/30** | 3/30 |
  | 快取（n=30） | **0/30** | 0/30 | 16/30 | **23/30** |
  | 日誌（n=30） | **0/30** | **13/30** | 0/30 | 0/30 |
  | 合計（N=90） | **0/90** | 13/90 | 35/90 | 26/90 |

  粗體的對照格是「專門拿掉該路徑檢查」的 baseline。

- 觀察：
  - 檢索：拿掉 pre-filter 後 19/30 洩漏。沒洩漏的 11 題，目標文件都沒排進前 20 個 chunk（依判定方式，只要出現在檢索結果就算洩漏），回答也沒寫出禁止字串。
    `-noprefilter` 的快取路徑 16/30 也是同一個原因造成的（asker 自己就檢索得到），不是快取的問題。
  - 快取：問題層快取 23/30 洩漏。沒洩漏的 7 題已逐題確認：insider 自己的檢索就沒有取到目標文件（7/7 都不在前 20 個 chunk），
    所以快取裡沒有可洩漏的內容。檢索路徑的 3/30 也來自快取：同一個問題稍早已由 insider 在快取題中問過（L-0033←L-0015、L-0034←L-0016、L-0038←L-0011），
    整個執行共用一個快取時，這正是問題層快取的真實風險。
  - 日誌：未遮罩的 trace 13/30（只記錄問題與回答，見前一筆）；其他三個系統都有遮罩，0/30。
  - 正式系統在三條路徑都是 0/30。字面比對的限制見 `evals/leak/README.md`（沒命中不代表安全）。

### 2026-11-09：judge 校準題庫與新 dev 的執行

- 目的：交接指示 003 補充第 8 點。標註表要以 open 題為主，但 dev 只有 3 題 open。
- 設定：`evals/calibration/open.jsonl`（22 題，`evals/gen_calibration.py` 依手寫 open 題模板產生，用手寫 open 題沒用到的 22 份現行 SOP；
  **只用於 judge 校準，不進 dev/test、不計入任何系統指標**）。對它跑 `rag-hybrid-bm25`（`20261109T052815Z-calibration-rag-hybrid-bm25`）；
  也對新 dev（72 題）跑一次（`20261109T052916Z-dev-rag-hybrid-bm25`，規則題的 60 題大多命中 LLM 快取）。
- 新 dev 的數字（n 標在括號）：回答正確率 0.826（69，不含 3 題 open）、引用正確率 0.769（65）、Recall@5 0.854（65）。
  規則題部分與 2026-11-09 稍早的執行相同（0.850，n=60）；手寫題非 open 6/9。
- 標註表：`evals/labels/label-sheet.md` 重新產生，50 題 = open 25（校準 22 + dev 3）、跨文件 10、拒答 7、其他 8（fact 3、paraphrase 2、dirty 2、old_version 1）。
  open 題逐點列出 5 個評分要點。手機版 `private/label-sheet-mobile.md`（不進 git）。

### 2026-11-09：test set 凍結

- 凍結於 git `6ebbb5d`（`feat(evals): finalize 31 handwritten questions and split them`）。之後 `evals/test/` 不得再修改；
  `split.py` 不會覆寫已存在的 test 檔（`--force` 才行）。
- 題目來源：
  - 規則題 151 題：`evals/gen_rule_questions.py` 依骨架事實產生（2026-11-08，`75e6a8d`）。
  - 手寫題 31 題：**規劃者（Claude）起草 31 題，Colin 審閱後全部保留，未修改**。`evals/handwritten.jsonl` 是
    `evals/handwritten.draft.jsonl` 的原樣複製（檔案內各題的 notes 仍是起草時的「待 Colin 修改」字樣）。
    split 前的語料檢查：0 錯誤、0 警告。
- 切分：各題庫獨立、依題型分層，dev/test = 40/60，seed `20261108`。

| 檔案 | sha256 | 題數 | 依題型 |
| --- | --- | --- | --- |
| `evals/test/rule.jsonl` | `4f85ecd3b6874a6530dfada2342645e2c7487db1b03fc9bb65346927a6beadda` | 91 | fact 27、paraphrase 18、dirty 15、cross_doc 12、old_version 10、refuse 9 |
| `evals/test/handwritten.jsonl` | `661f78bd2ffb6d0dfcd0dd4ff9615e23c516f06db1af6f51e03e0c9e15bfa876` | 19 | open 5、paraphrase 5、cross_doc 4、dirty 2、refuse 2、old_version 1 |
| **test 合計** | `run.py` 摘要的 `questions_sha256` = `fd8e1b1ed135fd61` | **110** | fact 27、paraphrase 23、cross_doc 16、dirty 17、old_version 11、refuse 11、open 5 |
| `evals/dev/rule.jsonl` | `592d87177b9ca80c46efa22ecb92c74a5c04d113fa7225f3a236d4d51b025bbe` | 60 | fact 18、paraphrase 12、dirty 10、cross_doc 8、old_version 6、refuse 6 |
| `evals/dev/handwritten.jsonl` | `9a962af476b511bb6829c881e42512d15706e7f2ba2430b51f07a5fccc8ba726` | 12 | open 3、paraphrase 3、cross_doc 2、dirty 2、old_version 1、refuse 1 |
| **dev 合計** | `questions_sha256` = `658c0a21051cb765` | **72** | |

- 注意：dev 加入手寫題後題目檔 hash 改變，2026-11-08／09 已存的 dev 執行結果不能再 `--rescore`（`run.py` 會拒絕），要比較時重跑。
- test eval 尚未執行（等 Colin 完成 50 題標註、gate 時經同意再跑）。

### 2026-11-09：權限洩漏測試（dev 系統，有／無出口檢查）

- 目的：PLAN Phase 1 gate 的「檢索、快取、日誌三條路徑的洩漏測試（a/N vs b/N）」。
- 設定：`evals/leak_cases.jsonl`（規則產生 90 題，分類見 `evals/leak/README.md`，**分類待 Colin 確認**）；
  section 索引（399 chunk）、qwen3:8b；git `42e0075`。比對規則：回答或 trace 含禁止字串，或（retrieval／cache）目標 doc_id 出現在引用或檢索結果。
- 結果（每條路徑 n = 30，合計 N = 90；錯誤 0）：

  | 路徑 | 有出口檢查 `rag-hybrid-bm25` | 無出口檢查 `rag-hybrid-bm25-noexit` |
  | --- | --- | --- |
  | 檢索 | 0/30 | 0/30 |
  | 快取 | 0/30 | 0/30 |
  | 日誌（trace） | 0/30 | **13/30** |
  | 合計 | **0/90** | 13/90 |

- 觀察：
  - **檢索 0/30 vs 0/30 是預期的**：`-noexit` 只關掉快取權限範圍、trace 遮罩與引用檢查，權限 pre-filter 仍在，所以這條路徑兩邊沒有差別。
    要有對照需要「無 pre-filter」版本（目前沒有）。
  - **快取 0/30 vs 0/30 不是因為快取安全，而是快取 key 本來就含整個 prompt**：prompt 裡有檢索到的文件內容，
    不同權限的人檢索結果不同，key 自然不同，所以即使 key 拿掉權限範圍也不會命中 primer 的回應。快取權限檢查仍有用
    （兩人檢索結果完全相同、或之後改成只以問題當 key 的語意快取時），但現在這個 baseline 證明不了它的效果。
  - 日誌 13/30：未遮罩的 trace 只記錄問題與回答（`answer.py` 的兩個 event），所以只有 insider 的回答確實寫出禁止字串的那 13 題會被抓到；
    遮罩版只存 hash 與長度，0/30。
- 下一步：要不要讓快取路徑的 baseline 有意義（例如 `-noexit` 改用「只以問題當 key」的快取），由 Colin 決定（`open-questions.md`）。

### 2026-11-09：切塊實驗——依章節 vs 整份文件

- 目的：PLAN 調參項目「切塊大小（400／1200 字）」。SOP 章節最長只有 149 字，`max_chars` 400／800／1200 切出來都是同樣 399 個 chunk，
  所以改比「依章節（現行）」與「整份文件一塊」（`--strategy doc`，192 個 chunk）。
- 設定：其餘同上；檢索取 20 個 chunk；整份文件索引建立後跑完再重建回 section（`select count(*)` = 399 確認）。
  git：檢索 `e4e40cd`、RAG `42e0075`（摘要的 git 欄位在 `42e0075` 之前記的是執行結束時的狀態）。
  注意：摘要沒有記錄當時用的是哪一種索引，對照如下。

  | run_id | 索引 |
  | --- | --- |
  | `20261109T013020Z-dev-ret-dense`、`…013049Z-dev-ret-bm25`、`…013118Z-dev-ret-hybrid-bm25` | 整份文件 |
  | `20261109T014011Z-dev-rag-hybrid-bm25`、`20261109T014224Z-dev-rag-hybrid-bm25-ctx4` | 整份文件 |
  | 其餘 2026-11-08／09 的執行 | section |

- 結果——檢索（n = 54）：

  | 設定 | Recall@5 section → 整份 | MRR section → 整份 |
  | --- | --- | --- |
  | dense | 0.657 → 0.750 | 0.512 → 0.685 |
  | BM25 | 0.824 → 0.880 | 0.782 → 0.835 |
  | dense + BM25 | 0.861 → 0.870 | 0.750 → 0.808 |

- 結果——回答（n = 60；括號內為該指標的 n）：

  | 指標 | section ctx8（現行預設） | 整份 ctx8 | 整份 ctx4 |
  | --- | --- | --- | --- |
  | 回答正確率（60） | 0.850 | 0.867 | **0.883** |
  | 關鍵事實召回（54） | 0.833 | 0.852 | 0.870 |
  | 引用正確率（54） | 0.741 | 0.815 | 0.815 |
  | 引用精確率 | 0.738（52） | 0.820（53） | 0.856（52） |
  | 誤拒率（54） | 0.037 | 0.019 | 0.037 |
  | 每題輸入 token | 2,075 | 3,430 | 1,909 |

  各題型回答正確率（section ctx8 → 整份 ctx4）：fact 0.889 → 0.889、dirty 0.900 → 1.000、cross_doc 0.250 → 0.375，其餘相同。

- 觀察：
  - 文件層級的 Recall@k 對整份文件有利：同一份文件不會佔掉好幾個名次。SOP 章節本來就很短（中位數 45 字），整份 SOP 也只有約 540 字（中位數，最長 642 字），
    切章節沒有省下多少 context，反而把「判定標準」與「處置步驟」拆開。
  - 整份 ctx4 比現行預設多答對 2 題（51 → 53，n=60），token 少 8%；**差距只有 2 題，在 dev 的雜訊範圍內**。
- 結論：**維持依章節切塊、送 8 個 chunk**（規劃者依 Colin 偏好代決，2026-11-09）。理由：整份文件 ctx4 只多答對 2 題（0.883 vs 0.850，n=60），
  在 dev 的雜訊範圍內，不足以改預設；依章節切塊時引用指向的是具體章節，回答的依據較精確、較容易人工核對。

### 2026-11-09：送進 LLM 的 chunk 數（4／8／12）

- 目的：PLAN 調參項目「送進 LLM 的 chunk 數」。
- 設定：`rag-hybrid-bm25-ctx{4,8,12}`（dense + BM25、不 rerank，檢索取 20 個 chunk，前 N 個送進 LLM）；
  qwen3:8b（Ollama，`reasoning_effort=none`）；題目 `evals/dev/rule.jsonl`（sha256 `e4a44891de9fcf17`）；
  評分 `evals/score.py`（`6f2a97d` 之後）。ctx8 即預設系統（下一筆）。
- 結果（n = 60；回答正確率與誤拒率只算各自適用的題目，n 標在括號）：

  | 指標 | ctx4 | **ctx8（預設）** | ctx12 |
  | --- | --- | --- | --- |
  | 回答正確率（n=60） | 0.717 | **0.850** | 0.833 |
  | 關鍵事實召回（n=54） | 0.685 | **0.833** | 0.815 |
  | 引用正確率（n=54） | 0.630 | **0.741** | 0.722 |
  | 引用精確率 | 0.623（n=50） | **0.738**（n=52） | 0.724（n=51） |
  | 誤拒率（可回答題，n=54） | 0.074 | 0.037 | 0.037 |
  | 每題輸入 token | 1,185 | 2,075 | 2,713 |

  各題型回答正確率（ctx4 → ctx8 → ctx12）：fact 0.722 → 0.889 → 0.833（n=18）、old_version 0.500 → 1.000 → 1.000（n=6）、
  paraphrase 0.917 → 1.000 → 0.917（n=12）、dirty 0.800 → 0.900 → 1.000（n=10）、cross_doc 0.250 → 0.250 → 0.250（n=8）、refuse 1.000（n=6）。

- 觀察：4 個 chunk 時常常只放進 SOP 的部分章節，「等多久重測」所在的章節被擠掉（old_version 掉最多）；
  12 個多花 30% token，沒有提升。延遲因為 LLM 快取命中狀況不同（見下一筆），這裡不比較。
- 結論：維持 8。

### 2026-11-09：dev 全量 RAG（PLAN baseline 對照）

- 目的：完成 2026-11-08 因記憶體不足中止的 dev 全量執行，取得 RAG 系統與 baseline 的回答層級數字。
- 設定：兩個系統**依序**執行（同一個 shell，前一個結束才開始下一個），每個程序只載入一次 bge-m3、不載入 reranker；
  這次沒有記憶體不足，沒有改成分批，也就沒有量峰值記憶體。qwen3:8b（Ollama，`reasoning_effort=none`），
  每題送 8 個 chunk；題目同上。評分 `evals/score.py`（`--rescore`）。
  - git：兩次都是 `6c02638` 的程式；`rag-hybrid-bm25` 執行時工作目錄有未提交的 `evals/score.py` 修改（評分程式，不影響系統輸出），
    所以摘要裡 `dirty=true`。
  - 延遲不可比：2026-11-08 中止的那次執行已經把部分 LLM 回應寫進快取，這次有些題目直接命中快取。
- 結果（n = 60：可回答 54、應拒答 6；基準 = `rag-dense`，也就是 PLAN 的「只用向量、不 rerank」）：

  | 指標 | 基準 `rag-dense` | `rag-hybrid-bm25` |
  | --- | --- | --- |
  | 回答正確率（n=60） | 0.700 | **0.850** |
  | 關鍵事實召回（n=54） | 0.667 | **0.833** |
  | 引用正確率（n=54） | 0.648 | **0.741** |
  | 引用精確率 | 0.691（n=50） | 0.738（n=52） |
  | 應拒答題的拒答率（n=6） | 1.000 | 1.000 |
  | 可回答題的誤拒率（n=54） | 0.056 | 0.037 |
  | 拒答旗標與文字不一致（n=60） | 0.000 | 0.000 |
  | Recall@5（n=54） | 0.657 | **0.861** |
  | MRR（n=54） | 0.512 | 0.750 |
  | 輸入／輸出 token（60 題合計） | 135,163 / 3,779 | 124,510 / 3,838 |
  | 成本 | $0（地端） | $0（地端） |

  各題型回答正確率（基準 → hybrid）：fact 0.667 → 0.889（n=18）、paraphrase 0.833 → 1.000（n=12）、dirty 0.800 → 0.900（n=10）、
  old_version 0.833 → 1.000（n=6）、cross_doc 0.125 → 0.250（n=8）、refuse 1.000 → 1.000（n=6）。
  cross_doc 的引用正確率兩者都是 0.000（n=8）：沒有一題同時引用到異常報告與 SOP。

- 觀察：
  - 回答層級的差距跟檢索層級一致：hybrid 主要贏在 fact（單號、alarm code 這類字面比對）與 old_version。
  - 拒答旗標一開始有 15% 和文字「不一致」，查看後發現是 qwen3 用了「文件中沒有可用資料」這個說法，
    `score.py` 的拒答用語表沒有收；補上後是 0（`tests/test_score.py` 有案例）。只影響 mismatch 指標，不影響對錯判定。
  - cross_doc 維持很低，原因同 2026-11-08（需要兩段式檢索）；依規劃者決定留給 Phase 2 的三組對照。
- 下一步：用這次 `rag-hybrid-bm25` 的輸出產生人工標註表（`evals/labels/label-sheet.md`）。

### 2026-11-09：rerank 複查——是否被 512 token 截斷

- 目的：交接指示 002 補充二第 1 點。懷疑 bge-reranker-v2-m3 的 `max_length` 把整份異常報告截斷，單號或 SOP 編號落在截斷範圍外，
  所以 rerank 才沒有提升。
- 設定：FlagEmbedding `FlagReranker.compute_score` 預設 `max_length=512`（query 最多佔 3/4）。用同一個模型的 tokenizer
  計算檢索範圍內（現行版）每個 chunk 的 token 數，並找截斷點之後才出現的單號／SOP 編號。
- 結果（349 個現行版 chunk）：

  | chunk 類型 | 數量 | token 平均 | 最大 | 超過 480 token |
  | --- | --- | --- | --- | --- |
  | SOP 章節 | 199 | 83 | 142 | 0 |
  | 異常報告（整份） | 150 | 274 | 305 | 0 |

  沒有任何 chunk 接近 512 token；query（約 30 token）加上最長的 chunk 也只有約 335 token。**沒有截斷**，所以也沒有單號被截掉。
- 逐題比較（`ret-hybrid-bm25` 不 rerank vs rerank，n=54，Recall@5 有變化的 10 題）：
  - rerank 變差的 6 題（old_version 2、paraphrase 2、dirty 1、cross_doc 1）中，前 5 題是同一個模式：正確的 SOP 章節原本在第 1 名，
    rerank 後被**引用同一份 SOP 的異常報告**擠出前 5 名。異常報告整份敘述（現象、處理經過、提到 SOP 編號）和問題的字面重疊比單一 SOP 章節多。
    cross_doc 那 1 題則是正確的 SOP（原本第 4 名）被同廠其他 SOP 擠出。
  - rerank 變好的 4 題：fact 2 題（問單號的根本原因、停機時間，正確報告從前 5 名外升到第 1 名）、cross_doc 2 題。
  - 各題型 Recall@5（不 rerank → rerank）：fact 0.889 → 1.000、old_version 1.000 → 0.667、paraphrase 1.000 → 0.833、dirty 1.000 → 0.900、cross_doc 0.312 → 0.375。
- 結論：先前的 rerank 結果有效，不是截斷造成的；`max_length` 改成 1024 結果會完全相同，所以**沒有重跑**三組 rerank 設定（結果是確定性的）。
  rerank 預設關閉的結論不變。
- 下一步（未做）：若要讓 rerank 有用，問題在「SOP 章節 vs 整份異常報告」的粒度不對等，例如 rerank 只在同類型文件內排序，
  或依問題類型決定是否 rerank；這屬於新的設計，記在 `open-questions.md`。

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
