# 開發日誌

依時間記錄進度與決策，最新的放最上面。每筆只寫「發生了什麼、決定了什麼、細節在哪」，
細節本身留在對應文件：架構決策 → `docs/decisions/`，實驗 → `docs/experiments.md`，
待決事項 → `docs/open-questions.md`，階段驗收 → `docs/gates/`，程式變更 → git log。

## 2026-11-11

- **交接指示 014**（Claude Code）：已記錄範本 repo 公開（https://github.com/colin-lai-dev/cc-project-template，template）、Langfuse 改走 OpenTelemetry 並端到端驗證（12/12、無內文）。
  demo 影片 release `demo-v1`：auto 模式下被分類器擋下；Colin 離開 auto 模式、逐次按同意後重試成功，
  https://github.com/colin-lai-dev/fabops-copilot/releases/tag/demo-v1（`fabops-copilot-demo.webm`，16.9 MB，可下載）。
- **交接指示 013**（Claude Code）：demo 橫幅捲動後收成 31px 單行；範本 repo https://github.com/colin-lai-dev/cc-project-template（public、template）；
  Langfuse 改走 OpenTelemetry（舊 ingestion API 已拒收、11-16 關閉），端到端驗證 12/12、違規 0（`experiments.md`）。demo-v1 release 被權限擋下，待 Colin 執行。
- **交接指示 012**（Claude Code）：demo 網站重新設計（夜班 MES 主控台、權限晶圓圖、6 步導覽、agent 逐步時間軸、真的操作核准、injection 對照組、互動結果圖），
  正式版與回放版共用元件；API 新增 `/api/docs` 與 `retrieved`；injection 對照組以 `rag-hybrid-bm25-noprefilter` 實跑（US$0.0005）。
  新依賴：@fontsource/barlow、noto-sans-tc、jetbrains-mono（自帶字型，不用 CDN）。重錄影片（2:55，1080p，存 `private/demo/`）與 GIF（27.5 s，2.8 MB）。
- **交接指示 011**（Claude Code）：回放 fixture（真實 API + Haiku，7 段，LLM 全命中快取，花費 US$0）、回放模式前端（橫幅、字幕、結果面板）、
  GitHub Pages 部署（https://colin-lai-dev.github.io/fabops-copilot/）、CI actions 升級；安裝 Playwright 1.49.1 + Chromium（約 88 MB）、gifenc、pngjs；
  自動錄製 3 分鐘影片（1080p WebM）與 30 秒 GIF（`docs/assets/demo.gif`）。上傳 release 被權限分類器擋下，待 Colin 執行。
- **交接指示 010 完成**（Claude Code）：Phase 3 結案、merge 回 main、tag `phase-3`；推上 GitHub（public，https://github.com/colin-lai-dev/fabops-copilot），
  第一次 CI 五個 job 全過；README 收尾（四路徑洩漏表、強制送達 injection、如何重現每個數字）；`docs/demo-script.md`（demo 問題都以 Haiku 實測過）。
- **Phase 3 gate 通過（Colin）**：規劃者決定兩個評分抽取限制不修（維持凍結規則、並列人工判讀，寫進 README 已知限制）；交接指示 010 推上 GitHub、準備 Phase 4。
- **交接指示 009 完成，Phase 3 到達 gate**（Claude Code）：Phase 2 merge 回 main、tag `phase-2`；模型比較（凍結 test）RAG 正確率 Haiku 0.752／Sonnet 0.743／qwen3 0.781、
  agent 13/15／15/15／4/15；CI workflow（本機驗證）；強制送達 injection（agent 送達 11/11、嚴格 9/11、人工 10/11＋1 部分）。Sonnet 第一次 400 已修。花費 Sonnet US$1.14。
  Langfuse 仍無 key。報告 `docs/gates/phase-3.md`。
- **Phase 2 gate 通過（Colin）**：agent test 三組對照 RAG 4/15、固定 workflow 15/15、agent 13/15（差距在雜訊內，agent 成本約 2 倍）；
  四路徑洩漏 0/180 vs 對照 113/180；injection 嚴格 9–10/11、人工判讀 11/11。規劃者決定：injection 判定規則維持凍結；
  強制送達 injection 變體放到 Phase 3。交接指示 009 開始 Phase 3。
- **交接指示 008 完成，Phase 2 到達 gate**（Claude Code）：代決 4 項落實（MES 改 public、核准者規則寫成 ADR-0006 修訂、開發 DB 測試資料清除）；
  injection 集與隔離 DB runner、Langfuse 匯出（預設關閉）、FastAPI + React 前端、agent loop 練習。test（Haiku，只跑一次）：三組成功率 RAG 4/15、fixed 15/15、agent 13/15；
  洩漏四路徑 0/180 vs 113/180；injection 嚴格 9/9/10 of 11、人工判讀 11/11。花費約 US$0.09。報告 `docs/gates/phase-2.md`。
- **交接指示 007 完成**（Claude Code）：Phase 1 gate 報告改為已通過並補最終數字；`phase-1-rag` 合併回 main、tag `phase-1`；README 改寫（英文）。
- **Phase 2（branch `phase-2-agent`）**：FastMCP 唯讀工具 5 個＋JWT 身分（ADR-0001）；LangGraph agent／固定 workflow（ADR-0006），核准 interrupt、
  Postgres checkpoint、audit log、冪等；工具路徑洩漏 0/101 vs 對照 69/101；情境集 24 題（test 15 凍結）；dev 三組對照 Haiku agent 9/9、fixed 8/9、RAG 2/9（n=9），
  花費 US$0.055。新依賴：fastmcp、langgraph、langgraph-checkpoint-postgres、pyjwt。待決 11 項見 `open-questions.md`（2026-11-11），細節 `experiments.md`。
- **Phase 1 gate 通過（Colin）**：test（110 題，Haiku 5.5）回答正確率 75.2% vs 65.7%、Recall@5 78.8% vs 68.2%；洩漏 0/90 vs 各路徑對照 55/90；
  judge Gemini 3.6 Flash 與人工標註整題一致 50/50。Phase 1 API 花費約 US$0.29。GPT-5.4 mini 未比較（Colin 決定先不加 OpenAI 額度）。
- 交接指示 007：Phase 1 結案、README 更新（開始投履歷）、開始 Phase 2。

## 2026-11-10

- **交接指示 006 完成**：Gemini 3.6 Flash judge 校準與 Colin 標註嚴格一致 50/50（三分類 49/50、open 逐點 124/125），暫定採用；
  test open 題 judge 嚴格通過 4/5 vs dense 0/5。GPT-5.4 mini 待 OpenAI 額度。本 session 付費合計約 US$0.29。
- **test eval 完成（Colin 同意先跑系統輸出）**：Haiku 5.5，110 題，回答正確率 0.752 vs dense 0.657（n=105）、
  Recall@5 0.788 vs 0.682（n=99）、誤拒率 0.212 vs 0.313；open 5 題待 judge。ADR-0008 judge 候選改為 Gemini 3.6 Flash
  （3.5 Flash 已轉給 3.6），Gemini 免費方案每天 20 次已用完、待付費；GPT-5.4 mini 待 OpenAI 額度。花費 Haiku US$0.151。
- **交接指示 006（進行中，停在 judge）**：修正 Claude provider（新版 API 不接受 `temperature`）；Haiku 5.5 跑 dev：
  回答正確率 0.783（n=69，baseline dense 0.739）、open 要點命中率 0.933（n=15；校準 0.900，n=110）、升級條件 11/22，
  但誤拒率 0.200（n=65，qwen3 0.031），原因是檢索缺口。升級條件沒有低於一半，設定凍結。花費 US$0.063。
  **judge 卡住**：OpenAI 沒有額度、Gemini 2.5 Flash 呼叫回 404，等 Colin 決定（`private/handoff/006-*.md` 回報）。
- **交接指示 005**（Claude Code）：SOP 章節展開實驗不採用——升級條件 25/25 進入 context，但 qwen3 仍 0/22（問題在生成端），
  要點命中率 0.591 → 0.609（n=110 點）、token +7%；`expand_sop` 保留、預設關閉。judge 與 test eval 仍因沒有 API key 未執行。
  細節：`docs/experiments.md`、ADR-0010 補充段。
- **交接指示 004**（Claude Code）：Colin 的 50 題標註入檔（open 對 0／部分 5／錯 20，其他 16／1／8）；
  處置題 SOP 優先採用（ADR-0010，`sop_boost` 1.2）：open 要點命中率 校準 0.155 → 0.591（n=110 點），dev 其他題型不變；
  新增 `evals/rubric_match.py`（與標註 125/125 點一致）。**judge 選擇與 test eval 因 `.env` 沒有 API key 跳過**，花費 $0。
  細節：`docs/experiments.md`、`docs/decisions/0010-*.md`、`docs/gates/phase-1.md`。

## 2026-11-10

- **人工標註完成**：Colin 以勾選版標完 50 題，字串比對交叉檢查 152 點全部一致；open 對 0／部分 5／錯 20。
  發現 25 題處置題中 19 題回答引用異常報告摘要而非 SOP 步驟。
- **ADR-0010**：處置類問題提高 SOP 權重，open 要點命中率 dev 0 → 0.600（n=15）、校準 0.155 → 0.591（n=110 點）。
  「升級條件」仍 0/22，交接指示 005 先試 SOP 章節展開。
- judge 實驗與 test eval 因 `.env` 沒有 API key 跳過；Colin 已同意兩者的花費（judge US$1、test US$2 以內）與 test 不必停下確認。

## 2026-11-09

- **交接指示 003 完成**（Claude Code）：手寫題 31 題原樣定稿並切分；**test set 凍結於 `6ebbb5d`（110 題）**；洩漏測試補上無 pre-filter 與問題層快取兩個對照組，
  正式系統三條路徑都 0/30、各對照組 19/30（檢索）、23/30（快取）、13/30（日誌）；judge 校準題庫 22 題，標註表改以 open 題為主重做；
  rerank 在手寫題上也沒有一致提升，維持關閉；ADR-0005 加規則 6（「部分」）。細節：`docs/experiments.md`、`docs/gates/phase-1.md`。
- **交接指示 002 完成**（Claude Code）：`score.py` 實作並刪除暫時評分器；dev 全量 RAG 完成，回答正確率 hybrid 0.850 vs dense baseline 0.700（n=60）；
  洩漏測試集規則產生 90 題，有出口檢查 0/90、無出口檢查 13/90（全在 trace）；人工標註表 50 題備妥。細節：`docs/experiments.md`、`docs/gates/phase-1.md`。
- **rerank 複查**：沒有 512 token 截斷，結論不變（rerank 偏好整份異常報告）；chunk 數 8 維持；整份文件 ctx4 略好但暫不改預設，待 Colin 決定。
- 待 Colin：洩漏分類確認、切塊預設、快取 baseline 做法、標註「部分」的算法（`docs/open-questions.md`）。

## 2026-11-09

- **Phase 1 Claude Code 部分完成**：`score.py`、洩漏集 90 題、標註表 50 題。dev 回答正確率 0.850（dense + BM25）vs 0.700（dense），n=60；
  洩漏：有出口檢查 0/90、無出口檢查 13/90（全在 trace）。rerank 複查：輸入沒有被截斷，結論不變（不採用）。
- **規劃者代決**：預設切塊維持依章節（整份文件只多 2 題，屬雜訊）；補「天真快取」與「無 pre-filter」兩個洩漏 baseline，
  讓每條路徑都有對照；標註「部分」算不通過並另報寬鬆比例。手寫題 31 題 Colin 確認全部保留，交接指示 003 定稿並凍結 test。
- **協作設定**：Claude Code 改為 auto 權限模式、預設繁體中文；Remote Control 開機腳本 `private/start-remote-control.bat`。

## 2026-11-08

- **分工調整（Colin 決定）**：`score.py` 與洩漏測試集改由 Claude Code 實作、Colin review；手寫題由規劃者起草 31 題
  （`evals/handwritten.draft.jsonl`）、Colin 修改；50 題人工標註仍由 Colin 親自完成。rerank 結論待複查（是否被輸入長度截斷）。
- **Phase 1 檢索**：dev Recall@5 dense + BM25 0.861、dense baseline 0.657（n=54）；rerank 在 CPU 每題約 25 秒且無提升，預設關閉；
  異常報告依段落切塊不採用；cross_doc 只有 0.31（n=8）。dev 全量 RAG 執行因記憶體不足中止，待重跑。
- **規劃者代決**：ADR-0009（jieba + BM25）採用；不裝 CUDA torch；Phase 1 不加引用展開（cross_doc 留給 Phase 2 對照）；
  不改寫 `39282cc`；`.env` 加入 `LLM_REASONING_EFFORT=none`。
- **交接指示 002（進行中）**：完成 bge-m3 索引、hybrid 檢索（dense + jieba BM25，ADR-0009 提議中）、回答生成與出口檢查、
  洩漏測試／judge 標註格式；dev Recall@5 0.861 vs baseline 0.657（n=54）。rerank 預設關閉、異常報告不切段（`experiments.md`）。
  dev 全量 RAG 執行因記憶體不足被系統中止，待 Colin 指示重跑（`private/handoff/reports/2026-11-08-1908-phase1-rag-paused.md`）。
- **Phase 1 開始**：eval 框架、權限 policy 函式、151 題規則題（dev 60／test 91）完成；
  停在 Colin 的手寫題與 `score.py`（`docs/gates/phase-1.md`）。
- **規劃者代決**：ADR-0004 補「暫不潤飾」修訂；ADR-0005 補 5 條評分細節預設規則（Colin 可推翻）；
  open-questions 4 筆暫定做法確認。CC 的回報改為寫進 `private/handoff/`，Colin 不必轉貼。
- **Phase 1 開始**（交接指示 001）：`phase-0-foundation` 合併回 `main`，開 `phase-1-rag`。完成 eval 框架與 151 題規則題（dev 60、test 91），停在 Colin 的手寫題目；待辦與評分細節見 `docs/gates/phase-1.md`，待決事項見 `docs/open-questions.md`。
- **企劃定稿為 v3**：經兩輪外部審查，主軸從「功能廣度」改為「驗證深度」——eval 先凍結再調參、
  權限檢查擴大到每個資料出口（檢索、快取、工具、日誌、輸出）、加入 prompt injection 測試、
  agent 以 RAG／固定 workflow／agent 三組對照證明價值；Phase 1 gate 為硬目標。
- **開發模式**：架構決策事先定案；Claude Code 在階段內自動實作，每個 gate 停下由 Colin review。
  手寫範圍收斂為 eval 評分腳本與 agent loop 練習；測試集由 Colin 設計。
- **架構決策 ADR-0001～0008 定案**：身分由伺服器端注入、權限模型（等級＋廠區＋部門）、
  先過濾再精確搜尋、規則骨架產生合成資料、評分方式、自訂 StateGraph、trace 嚴格遮罩、模型配置。
- **Phase 0 實作完成**：專案骨架、Postgres＋pgvector、合成資料產生器、LLM client。
- **Windows 驗證**：5432 被其他專案占用，改為可設定埠（本機用 5433）；固定 Python 3.12；
  uv 以 winget 安裝；程式改由 pydantic-settings 自動讀取 `.env`。
- **LLM 潤飾實驗不採用**：成功率 52%，且洗掉髒資料、混入簡體字；沿用模板版本，
  Phase 1 baseline 若顯示模板文字讓分數失真再重做（`docs/experiments.md`）。
- **協作設定**：新增 Claude Code 權限規則（`.claude/settings.json`）與交接機制
  （使用者說「接手」即執行 `private/handoff/` 中的下一份指示）。
- 企劃 v3 定稿版存於本機 `private/planning/`（不進 git）。
- **Phase 0 gate 通過**（`docs/gates/phase-0.md`）。下一步：Phase 1，先做 eval 框架。

## 2026-11-07

- 決定以「晶圓廠異常處理 AI 助理」作為補足 RAG／agentic workflow 經驗的 side project，
  題材來自 MES 與派貨系統實務；企劃 v1 完成。
