# 待決問題

Claude Code 遇到 ADR 沒涵蓋的問題時記錄於此，並採用暫定做法繼續。Colin 在 gate 時決定。

| 日期 | 問題 | 暫定做法 | 替代方案 | 狀態 |
| --- | --- | --- | --- | --- |
| 2026-11-08 | **文件潤飾要不要在凍結 test set 前執行？** 潤飾會改變文件文字，題目必須以最終文件為準。 | **暫不潤飾**，沿用模板版本。2026-11-08 實驗結果不採用（見 `experiments.md`）：簡體字混入、髒資料標記被洗掉。 | 若 Phase 1 baseline 顯示模板文字讓分數失真，再以修正版流程重做：先潤飾再加髒資料、`verify()` 加繁體檢查、關閉 qwen3 思考模式、prompt 指定台灣繁體中文。 | **已決（Colin，2026-11-08）** |
| 2026-11-08 | 機台資料表命名 | 用 `equipment`，避免和 agent 的「工具」混淆。 | 沿用 PLAN 的 `tools`。 | 暫定 |
| 2026-11-08 | Ollama 放在哪裡 | 跑在 Windows 主機上（直接用 GPU），不放進 Compose。 | 放進 Compose 並設定 GPU 直通，設定較複雜。 | 暫定 |
| 2026-11-08 | Claude 的接法（ADR-0008 留待確認） | 用 Anthropic 官方 SDK 的原生轉接層，其餘供應商走 OpenAI 相容介面。 | 走 Anthropic 的 OpenAI 相容端點，功能可能有差異。 | 暫定 |
| 2026-11-08 | 結構化輸出的做法 | 用 prompt 要求 JSON，再以 Pydantic 驗證，失敗時修正重試一次；各供應商通用。 | 改用各家原生的 JSON 模式或 tool calling，較穩定但要分別實作。 | 暫定 |
| 2026-11-08 | 機密等級分布 | restricted 等級目前只有 1 份 SOP 和 14 份異常報告。 | Phase 1 設計洩漏測試集時，若覺得不夠可調整 `generate.py` 的權重。 | 暫定 |
| 2026-11-08 | 程式不會自動載入 `.env` | 新增 `src/fabops/config.py`，以既有依賴 `pydantic-settings` 讀取 `.env`（環境變數優先）；seed、測試、LLM client 都改用它，Makefile 不再需要 `--env-file`。 | python-dotenv（要新增依賴）。 | 已解決 |
| 2026-11-08 | ADR-0004 與「暫不潤飾」不一致 | ADR-0004 已新增「修訂（2026-11-08）」段落，記錄暫不潤飾與重新啟用條件。 | 新增一篇 ADR 取代。 | 已解決 |
| 2026-11-08 | 規則題的提問者 | 選「看得到所有應引用文件、權限最低」的 demo 使用者；`op_fx1_etch` 因此沒有出現在規則題中。 | 在看得到的使用者中隨機選，分布較平均。 | 確認（規劃者代決，Colin 可推翻） |
| 2026-11-08 | 規則題的應拒答題只出「資料庫沒有答案」的題目，提問者固定為 `admin_all` | 權限型拒答（看不到文件）留給 Colin 設計的洩漏測試集，避免兩邊重複、也不替 Colin 出洩漏題。 | QA 集也加入權限型拒答題。 | 確認（規劃者代決，Colin 可推翻） |
| 2026-11-08 | 通用 SOP（`GEN-*`，緊急分機、升級時數）不出規則題 | 兩廠內容相同，題目無法指向單一文件。 | 用手寫題涵蓋，或接受兩份都算正確。 | 確認（規劃者代決，Colin 可推翻） |
| 2026-11-08 | qwen3 的思考模式（交接指示 001 第 4 點） | 用請求參數 `reasoning_effort="none"`（`LLM_REASONING_EFFORT=none`）；`/no_think` 與 `think=false` 實測無效，見 `experiments.md`。 | — | 已解決 |
| 2026-11-08 | 本機 `.env` 缺 `LLM_REASONING_EFFORT=none` | `.env.example` 已加入；Claude Code 不讀寫 `.env`，執行 dev eval 時以環境變數帶入。**請 Colin 在 `.env` 加上這一行。** | — | 已解決（規劃者已加入 `.env`）（規劃者代決，Colin 可推翻） |
| 2026-11-08 | 舊版文件（`superseded_by` 不為空）是否進入檢索 | 預設排除（SQL 加 `superseded_by IS NULL`），所以「問舊版內容」的題目無法回答，只會回答現行版。`RetrievalConfig(include_superseded=True)` 可以打開。 | 預設納入，交給 LLM 依 prompt 規則 5 選新版；引用正確率會受影響（ADR-0005 規則 5）。 | 確認（規劃者代決，Colin 可推翻） |
| 2026-11-08 | 沒有引用、也沒有拒答的回答 | 保留原樣輸出，不強制改成拒答；由評分（ADR-0005 規則 5）記為引用錯誤。 | 出口檢查時把無引用的回答改成拒答，較保守但會增加誤拒。 | 確認（規劃者代決，Colin 可推翻） |
| 2026-11-08 | Phase 1 的 trace 去哪裡 | 寫到本機 `.cache/traces.jsonl`，欄位與遮罩規則照 ADR-0007（`authz/trace.py`）；Langfuse 到 Phase 2 才接（不新增依賴）。 | 現在就接 Langfuse 免費雲端。 | 確認（規劃者代決，Colin 可推翻） |
| 2026-11-08 | rerank 預設關閉 | dev 上 rerank 沒有提升 hybrid 的 Recall@5（0.861 → 0.815，n=54），CPU 上每題約 25 秒。保留 `-rerank` 選項。 | 改用 CUDA 版 torch 在 GPU 上跑 rerank（要改依賴與 `uv.lock`，需 Colin 同意），再重新比較。 | 決定：不裝 CUDA 版 torch，rerank 維持關閉（rerank 在 dev 沒有提升，GPU 也要留給 qwen3）；若之後引用展開或手寫題讓 rerank 有提升空間再評估（規劃者代決，Colin 可推翻）。**2026-11-09 複查**：沒有 512 token 截斷（最長 chunk 305 token），結論不變；rerank 變差的原因是它偏好整份異常報告勝過單一 SOP 章節（`experiments.md`）。 |
| 2026-11-08 | 跨文件題（異常報告 → SOP）需要兩段式檢索 | Phase 1 維持單次檢索，cross_doc 的 Recall@5 只有 0.31（n=8）；改善留給 Phase 2 agent 的多步查詢。 | 在檢索層加「引用展開」：命中的文件中提到的 SOP 編號，經權限檢查後一併取回。 | 決定：Phase 1 不加引用展開，cross_doc 保留為 Phase 2 三組對照的核心案例（RAG 單次檢索 vs 固定 workflow vs agent）（規劃者代決，Colin 可推翻） |
| 2026-11-08 | qwen3:8b 會列出沒用到的引用 | 不改 prompt（規則 4 已要求只列實際依據的文件），由引用 precision 反映；Haiku 5.5 上再觀察。 | 加 few-shot 範例或只保留回答中提到的 doc_id。 | 確認（規劃者代決，Colin 可推翻） |
| 2026-11-08 | commit `39282cc` 混進了回答生成的程式 | `fix(test)` 那個 commit 也包含 `rag/answer.py`、`tests/test_answer.py` 以及 `llm/client.py`、`rag/retrieve.py` 的修改（提交時 PowerShell 參數問題）。沒有改寫歷史。 | 經 Colin 同意後用 rebase 拆開。 | 決定：不改寫歷史；merge 到 main 時於 gate 報告註明（規劃者代決，Colin 可推翻） |
| 2026-11-09 | rerank 粒度不對等：SOP 依章節切、異常報告整份一塊，reranker 偏好字面重疊多的整份報告 | 不處理，rerank 維持關閉。 | rerank 只在同類型文件內排序；或依問題類型（問單號 vs 問處置程序）決定是否 rerank。 | 暫定 |
| 2026-11-09 | 標註表的「部分」怎麼算 | `JudgeLabel.passed` 只有對錯，「部分」暫時算**不通過**，原文保留在 `notes`。 | 「部分」算通過；或 `JudgeLabel` 改成 0／0.5／1 分。 | 已決（規劃者代決，2026-11-09）：主要指標嚴格（不通過），另報寬鬆比例；寫入 ADR-0005 規則 6，`JudgeLabel.partial` |
| 2026-11-09 | 標註表沒有 open 題 | dev 目前只有規則題（沒有 open），50 題從 6 種規則題型分層抽樣。手寫題定稿、split 後，若 dev 有 open 題，重跑 dev 再產生一次標註表（open 題全收）。 | 現在就用手寫題草稿出 open 題（違反「不修改草稿、定稿後才 split」）。 | 已決（規劃者代決，2026-11-09）：另建 judge 校準題庫 `evals/calibration/open.jsonl`（22 題，不進 dev/test），標註表改以 open 題為主 |
| 2026-11-09 | 洩漏測試集的分類與題數 | 3 種邊界類型（跨廠、跨部門、等級不足）× 3 條路徑（檢索、快取、日誌），每格 10 題，共 90 題；每題只違反一個條件。詳見 `evals/leak/README.md`。 | 加入「同時違反兩個條件」的題目；每格題數調整。 | 已決（規劃者代決，2026-11-09）：照現狀採用 |
| 2026-11-09 | 切塊大小實驗（400／1200 字）沒有意義 | SOP 章節最長只有 149 字，`max_chars` 400／800／1200 切出來完全一樣（399 個 chunk），改做「依章節 vs 整份文件」的對照。 | — | 已解決 |
| 2026-11-09 | 預設切塊要不要改成「整份文件、送 4 份給 LLM」 | **暫不改**，維持依 SOP 章節切塊、送 8 個 chunk（PLAN 寫的是依章節）。dev 上整份 ctx4 回答正確率 0.883 vs 0.850（多答對 2 題，n=60），token 少 8%，差距在雜訊範圍內（`experiments.md`）。 | 改成整份文件 ctx4；若改，在手寫題加入 dev 後、凍結 test 前再確認一次。 | 已決（規劃者代決，2026-11-09）：維持依章節（理由見 `experiments.md`） |
| 2026-11-09 | 快取路徑的洩漏 baseline 證明不了什麼 | 照實報告 0/30 vs 0/30：快取 key 含整個 prompt（含檢索內容），不同權限的檢索結果不同，key 本來就不會撞。 | `-noexit` 改用「只以問題當 key」的快取（模擬常見的語意快取），讓 baseline 能顯示權限檢查的效果；或在 gate 報告只報檢索與日誌兩條路徑的對照。 | 已決（規劃者代決，2026-11-09）：新增 `-naivecache`（只以問題當 key）與 `-noprefilter` 兩個 eval 專用 baseline（`evals/baselines.py`） |
| 2026-11-10 | 處置類問題怎麼判斷（ADR-0010 的 SOP boost 何時啟動） | 關鍵詞（怎麼處理、如何處置、處置步驟、該怎麼辦……），dev＋校準題庫的 open 題全部命中，非 open 只有 4 題命中且都與 SOP 有關。 | Phase 2 由 agent 路由判斷；或擴充關鍵詞後在 dev 重新確認。 | 暫定 |
| 2026-11-10 | open 題「升級條件」（第 5 點）0/22 | **2026-11-10 更新**：章節展開讓升級條件 25/25 進入 context，qwen3 仍 0/22，問題在生成端；展開不採用（`experiments.md`）。暫不改 prompt，等 Haiku 5.5 在 dev 上的結果再看。 | prompt 規則加「處置類問題要包含升級條件」並在 dev 比較；或 Phase 2 agent。 | 暫定 |
