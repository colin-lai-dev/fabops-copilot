# ADR-0002: 權限模型

- 日期：2026-11-08
- 狀態：已採用

## 背景

每個資料出口（檢索、快取、agent 工具、trace、輸出）都要依同一套規則判斷使用者能不能看到某份資料。
模型太簡單，洩漏測試只能測一個維度；模型太複雜，又會吃掉有限的開發時間。

## 選項

| 選項 | 優點 | 缺點 |
| --- | --- | --- |
| A. 純角色（RBAC），角色對應機密等級 | 最簡單 | 只能測「等級夠不夠」，不符合跨廠、跨部門隔離的實況 |
| B. 機密等級 + 廠區 + 部門屬性 | 接近晶圓廠實際做法；洩漏路徑較多（同等級但跨廠等） | 規則與測試較多 |
| C. 外部 policy engine（OPA、Casbin） | 規則與程式分離 | 多一個元件與一套語言，對本專案過重 |

## 決定

選擇 B。

- 使用者：`fabs`（可存取的廠區集合）、`departments`（部門集合）、`clearance`（等級）。
- 文件與資料列：`fab`、`department`、`clearance`。
- 可見條件：`doc.clearance <= user.clearance` 且 `doc.fab ∈ user.fabs` 且
  （`doc.department ∈ user.departments` 或 `doc.department = 'shared'`）。
- 機密等級：`public` < `internal` < `confidential` < `restricted`。

## 理由

最接近實際的資料隔離方式，也讓洩漏測試能涵蓋「等級足夠但跨廠或跨部門」的情況。
規則仍簡單到可以用一個純函式與一段 SQL 條件表達。

## 後果

- 規則只有一個來源：`src/fabops/authz/policy.py` 的純函式，以及由同一份定義產生的 SQL 條件。
  以測試確保兩者判斷一致（同一組使用者 × 文件組合，結果必須相同）。
- Demo 預設 4–6 個使用者，涵蓋各種組合（含跨廠、跨部門）。
- MES 資料表也帶 `fab` 欄位，agent 工具依同一套規則過濾。
