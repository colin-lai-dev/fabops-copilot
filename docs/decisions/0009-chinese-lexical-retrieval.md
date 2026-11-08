# ADR-0009: 中文關鍵字檢索用 jieba + BM25，不用 bge-m3 sparse

- 日期：2026-11-08
- 狀態：提議中（Claude Code 依交接指示 002 起草，待 Colin 在 Phase 1 gate 確認）

## 背景

ADR-0003 規定 hybrid search（向量 + 關鍵字），但沒有規定中文的關鍵字那一路要怎麼做。
中文沒有空白分詞，而問題裡常有機台編號、alarm code、單號這類代碼，要能精確命中。
候選做法有兩個，都在本機執行、不用付費：

- **jieba 斷詞 + 自己實作的 BM25**：搭配廠內詞典（alarm 名稱、PM 類型、部門、縮寫）。
- **bge-m3 sparse（lexical weights）**：跟 dense 向量由同一個 `BGEM3FlagModel` 一次產生
  （Colin 2026-11-08 指定 dense 與 sparse 都走 FlagEmbedding，不經 Ollama）。

兩者都只對已經通過權限過濾的 chunk 計分（ADR-0003：先過濾、再排序），
所以 IDF 等語料統計只來自使用者看得到的文件。

## 選項

| 選項 | 優點 | 缺點 |
| --- | --- | --- |
| A：jieba + BM25 | 代碼保留成完整 token（正規表示式先抽出 `FX1-ETCHER-02`、`INC-2026-0001`），精確命中；詞典可由廠內維護；行為可解釋 | 要維護詞典；長文件會被長度正規化壓低（見後果） |
| B：bge-m3 sparse | 不需詞典；與 dense 同一次推論，不多花時間 | 代碼會被 subword 拆開；權重不透明；與 dense 融合時沒有互補效果（見下表） |
| C：兩者都用（三路融合） | 可能再多一點召回 | 多一路要調權重；dev 只有 54 題，看不出差異 |

## 決定

選擇 A：關鍵字那一路用 jieba（`lcut_for_search`）+ 廠內詞典 + BM25（k1=1.5、b=0.75），
與 dense 以 RRF（k=60）融合。bge-m3 sparse 保留在程式中（`lexical="sparse"`），只作為對照實驗。

## 理由

dev 規則題（可回答的題目，n = 54；399 個 chunk；git `53b806b`），不 rerank，檢索 k=20 chunk：

| 設定 | Recall@5 | Hit@5 | MRR |
| --- | --- | --- | --- |
| dense（baseline） | 0.657 | 0.704 | 0.512 |
| BM25（jieba） | 0.824 | 0.833 | 0.782 |
| bge-m3 sparse | 0.833 | 0.870 | 0.703 |
| dense + BM25（RRF） | **0.861** | **0.889** | 0.750 |
| dense + sparse（RRF） | 0.778 | 0.815 | 0.547 |

- 單獨使用時兩者的 Recall@5 差不多（0.824 對 0.833），但 BM25 的 MRR 較高（0.782 對 0.703），代表正確文件排得較前面。
- 與 dense 融合後差距拉開：dense + BM25 是所有設定中最好的，dense + sparse 反而比 sparse 單獨使用還差。
  可能的原因是 sparse 與 dense 來自同一個模型，錯誤高度相關，融合沒有互補效果。
- 樣本數小，0.861 與 0.833 只差約 1–2 題，不能視為顯著差異；選 A 的主因是融合後的結果，加上可解釋性與代碼精確命中。

完整紀錄見 `docs/experiments.md` 的「2026-11-08：檢索設定比較」。

## 後果

- 詞典在 `fabops/rag/lexical.py` 的 `_load_domain_dictionary()`，來源是 `fabops/data/world.py`；
  新增 alarm 類型或縮寫時詞典會自動跟著更新，但重建索引後才會生效（chunk 的 `tokens` 欄位是建索引時算的）。
- BM25 要掃描使用者看得到的所有 chunk（ADR-0003 的精確檢索）。目前 399 個 chunk 時每題約 250 ms（含 bge-m3 編碼問題）；
  語料成長到數萬個 chunk 時要改用 Postgres 全文檢索或倒排索引，那時再重新評估。
- 整份異常報告當作一個 chunk 時，BM25 的長度正規化會把含有完整單號的報告排到後面；
  切塊實驗會另外處理（見 `experiments.md`）。
- 套件相容性：FlagEmbedding 1.4.2 搭配 transformers 5.22.2、torch 2.15.0（CPU 版）可正常執行，
  沒有另外固定 transformers 版本；所有版本都記錄在 `uv.lock`。
- 需要重新評估的條件：題目數增加後差異反轉、改用不同的 embedding 模型，或手寫題顯示 sparse 在口語問法上明顯較好。
