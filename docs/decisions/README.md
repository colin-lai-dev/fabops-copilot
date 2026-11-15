# 設計決策索引

[English](README.en.md)

ADR（Architecture Decision Record）是一份決策一份檔案的紀錄：每份都有**背景**（要解決什麼）、**選項**（各自的優缺點）、**決定**、**理由**與**後果**（接受了什麼代價、什麼情況下要重新評估）。
下表一列一份 ADR，30 秒看完所有取捨；細節點進各 ADR。所有數字來自合成資料（虛構的 Fab-X），都附樣本數 n 與來源；沒有量測的決定寫的是設計理由。

## 已採用的決策

| ADR | 決策（一句話） | 選了什麼 vs 沒選什麼 | 關鍵依據 |
| --- | --- | --- | --- |
| [0001](0001-identity-injection.md) | 使用者身分怎麼傳到 agent 工具 | MCP 走 HTTP，FastAPI 簽發短效 JWT、MCP server 在邊界驗證 vs 同一行程用框架設定帶入、每位使用者一個 MCP 行程 | 設計理由：身分若是 LLM 可填的工具參數，prompt injection 就能升權。injection test（n=11）中越權讀取、冒用角色、外洩類，三組系統全部擋下（[Phase 2 gate](../gates/phase-2.md)） |
| [0002](0002-permission-model.md) | 權限模型 | 機密等級 + 廠區 + 部門屬性 vs 純角色（RBAC）、外部 policy engine（OPA、Casbin） | 設計理由：能測「等級足夠但跨廠／跨部門」；規則只有一個純函式來源，SQL 條件同源產生並以 DB 測試確保一致。agent 工具路徑洩漏 0/90 vs 拿掉權限條件的對照 58/90（[Phase 2 gate](../gates/phase-2.md)） |
| [0003](0003-filtered-vector-search.md) | 權限過濾與向量檢索怎麼搭配 | 先套權限條件、再精確搜尋 vs HNSW + iterative scan、依廠區／等級分割索引 | 399 個 chunk 時每題檢索約 250 ms（[ADR-0009](0009-chinese-lexical-retrieval.md)），不需要 ANN；檢索路徑洩漏 0/30 vs 無 pre-filter 19/30（[experiments 2026-11-09 權限洩漏測試](../experiments.md)） |
| [0004](0004-synthetic-data.md) | 合成文件怎麼產生 | 規則骨架 + 模板，髒資料以規則注入 vs 全部由 LLM 生成；LLM 潤飾實作了但不採用 | 潤飾（qwen3:8b）只有 100/192 份通過事實檢查，錯字標記保留 0/26、8/100 份混入簡體字（[experiments 2026-11-08 LLM 潤飾實驗](../experiments.md)） |
| [0005](0005-answer-grading.md) | 答案怎麼評分 | 事實題用程式比對、只有開放題用 LLM judge vs 全部雲端 judge、全部地端 judge | 標準事實來自骨架，程式比對免費且可重現；開放題 judge 與人工標註整題嚴格一致 50/50（n=50），judge 總花費 US$0.134（[experiments 2026-11-10 judge 校準](../experiments.md)） |
| [0006](0006-agent-graph.md) | Agent 的 LangGraph 結構 | 自訂 StateGraph vs 預建 ReAct agent、多 agent supervisor | 設計理由：核准、8 步上限、上下文壓縮都是看得見、測得到的節點；固定 workflow 共用同一組節點，對照只差「由誰決定下一步」。因此能做公平的三組對照：test RAG 4/15、固定 15/15、agent 13/15（n=15，[Phase 2 gate](../gates/phase-2.md)） |
| [0007](0007-trace-masking.md) | Trace 遮罩規則 | 嚴格遮罩（只送 ID、等級、雜湊、長度）+ 本機除錯模式 vs 依等級遮罩、靠 Langfuse 存取控管 | 日誌路徑洩漏 0/30 vs 未遮罩 13/30；Langfuse 端到端送出並讀回 12/12 筆，欄位全在允許清單內，違規 0（[experiments 2026-11-09、2026-11-11](../experiments.md)） |
| [0008](0008-model-selection.md) | 模型配置 | 主力 Claude Haiku 5.5 + 不同家族的 judge（Gemini 3.6 Flash）+ 地端 Qwen3 8B vs 全部 Claude、全部 OpenAI 或 Gemini | Phase 3 test：RAG 回答正確率三個模型 0.743–0.781（n=105），差距小；agent Sonnet 15/15、Haiku 13/15、qwen3 4/15（n=15），Sonnet 每題成本是 Haiku 的 12 倍（[experiments 2026-11-11 模型比較](../experiments.md)） |
| [0009](0009-chinese-lexical-retrieval.md) | 中文關鍵字檢索 | jieba + BM25 vs bge-m3 sparse | 與 dense 融合後 Recall@5 0.861 vs 0.778（dev n=54）；代碼（機台編號、單號）保留成完整 token |
| [0010](0010-sop-boost-for-disposal-questions.md) | 「該怎麼處理」類問題的檢索排序 | SOP chunk 分數 ×1.2 vs SOP／報告固定名額、整份 SOP 章節展開、留給 agent | 處置步驟進入 context 13/25 → 25/25（名額法最好 23/25）；開放題要點命中率 0.155 → 0.591（校準題庫 n=110 點，[experiments 2026-11-10](../experiments.md)） |

## 量測後不採用的做法

| 做法 | 結果 | 來源 |
| --- | --- | --- |
| rerank（bge-reranker-v2-m3，CPU） | 沒有提升召回：hybrid Recall@5 0.861 → 0.815（dev n=54），每題約 +25 s；確認不是 512 token 截斷造成，手寫題上再驗證結論不變 | [experiments](../experiments.md) 2026-11-08 檢索設定比較、2026-11-09 rerank 複查與再驗證 |
| bge-m3 sparse 當關鍵字那一路 | 與 dense 融合 Recall@5 0.778，低於 jieba + BM25 的 0.861（dev n=54） | [ADR-0009](0009-chinese-lexical-retrieval.md) |
| 整份文件一個 chunk | 回答正確率 0.883 vs 0.850（n=60），只多答對 2 題，在 dev 雜訊內；依章節切塊的引用較精確 | [experiments](../experiments.md) 2026-11-09 切塊實驗 |
| 處置題的 SOP 章節展開 | 升級條件已 25/25 進入 context，但要點命中率 0.591 → 0.609（n=110 點）、dev 0.600 → 0.467（n=15 點），input tokens +7%，無明確改善 | [ADR-0010 補充](0010-sop-boost-for-disposal-questions.md)、[experiments](../experiments.md) 2026-11-10 |
| 用 agent 取代固定 workflow | test 固定 15/15 vs agent 13/15（n=15），差距在雜訊內且方向與 dev 相反；agent 成本約 2.1 倍 | [Phase 2 gate](../gates/phase-2.md) |

網站設計怎麼從 v8 改到 v9、我怎麼指揮 AI 並驗收：[設計案例](../case-study-design-lab.md)。
