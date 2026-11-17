# Changelog

格式參考 Keep a Changelog；版本號：費率更新 → minor，邏輯修正 → patch。

## [0.2.5] - 2026-11-18

### 新增

- 整合品牌圖：`custom_components/taipower_estimate/brand/icon.png`（256×256）與 `icon@2x.png`（512×512），透明背景。
  Home Assistant 2026.3 起，custom integration 把圖放在自己的 `brand/` 資料夾就會顯示；之前沒有附，
  整合頁左上角是「icon not available」。圖是自己畫的（帳單＋閃電），沒有用台電或其他商標；
  原稿 `docs/brand/icon.svg`，重畫用 `python tools/gen_brand.py`。
- 設定精靈（含選項）選到功率（W／kW）sensor 或 Wh／MWh sensor 時直接擋下並說明怎麼辦，不再讓人裝完才發現度數不對。
  來源選單現在也列出功率 sensor，選了會得到明確的下一步，而不是在清單裡找不到自己的 sensor。

### 變更

- README：新增「只有功率 sensor 或用 Emporia Vue」（Integration helper 設定：積分方法、前綴 k、時間單位 h、最大子區間）、
  「常見卡關」；更正「每天／每月歸零的 sensor 不能用」——整合版把讀數掉到上次 90% 以下當成歸零，會歸零的 kWh sensor 可以用，
  只是歸零前後幾分鐘的度數會漏。
- 測試：`tests/test_brand.py`、`tests_ha/` 新增設定精靈／選項擋功率與 Wh sensor 的測試。

## [0.2.4] - 2026-11-14

程式邏輯沒有改。

### 變更

- README：加上部落格文章連結、需求與費用、支持連結；移除指向不在 repo 內的 `AGENTS.md` 的連結。
- 新增 gitleaks secret-scan workflow。

## [0.2.3] - 2026-11-14

計算邏輯沒有改。

### 變更

- 整合版新增 `icons.json`：已量測天數、週期進度、預估整期度數、夏月占比、級距電價五個 sensor 有各自的圖示
  （原本都是預設圖示）；已用度數與預估電費沿用 device class 圖示。
- README 重排：開頭一句說明用途、badges、一鍵安裝擺最前，加上設定精靈與七個 sensor 的實機截圖（`docs/images/`）。
- README 更正：sensor 顯示名稱跟著 HA 的**系統語言**（設定 → 系統 → 一般），不是個人帳號的介面語言。
- README 新增說明：`sensor.taipower_tier_price` 放進 Energy 面板當電價時，算的是「目前級距單價 × 度數」，
  不是逐級累進，總額會比 `sensor.taipower_cycle_bill` 高。

## [0.2.2] - 2026-11-14

### 修正

- 整合版 `sensor.taipower_cycle_bill`（預估電費）加上 `state_class: total`：之前沒有 state_class，HA 不留長期統計，
  statistics-graph 畫不出電費趨勢。圖卡請用 `stat_types: state`（monetary 只允許 total，沒有 mean）。
- package 版 `sensor.power_cycle_bill` 加上 `state_class: measurement`，同樣為了長期統計。

## [0.2.1] - 2026-11-14

程式邏輯沒有改，只更新文件與版本號。

### 變更

- 整合版已在一台真實運作的 Home Assistant 2026.11.1 上驗證：Marketplace 安裝、設定精靈（週期中途安裝並填入已用度數）、
  在選項裡換來源電表（已用度數保留，只重設基準）都正常，七個 sensor 數值與參考實作一致。
  README「限制」改成照實寫明已驗證的範圍，以及還沒驗證的兩項：實際跨過抄表日、和台電帳單的比對。package 版仍未在真實 HA 驗證。

## [0.2.0] - 2026-11-14

> 整合版尚未在真實運作中的 Home Assistant 驗證（測試在 HA core 測試環境），見 README「限制」。（0.2.1 已更新）
>
> 安裝：Home Assistant 2026.11 以上 → 設定 → Marketplace → Add from link → `drpwchen/ha-taipower-estimate`；舊版用 HACS Custom repositories。

### 新增

- **HACS custom integration** `custom_components/taipower_estimate/`：UI 設定精靈（電表 sensor、電價類別、每月／兩個月、
  抄表日、奇偶月、選填「這期已用度數」），之後可在選項修改。七個 sensor 語意對齊 package，entity_id 為 `sensor.taipower_*`。
  - 自己追蹤抄表週期（不用 `utility_meter`），狀態存在 `.storage`，重開機不歸零；停機錯過抄表日會開新的一期並從開機起重量。
  - 安裝在週期中途、沒填已用度數時，以實測每日用電外推（`partial_cycle`），第一期不再偏。
  - 來源 sensor `unavailable` 期間的度數在恢復後補回；讀數掉到 90% 以下當成換表，小幅下降當成抖動。
- `hacs.json`、GitHub Actions（hassfest、HACS validate、unittest、gen `--check`、pytest）。
- 測試：`tests/test_cycle.py`（週期邏輯 23 個，不需 HA）、`tests_ha/`（HA core 2026.10.4 測試環境 7 個）。

### 變更

- 計算核心搬到 `custom_components/taipower_estimate/calc.py`，`tools/taipower_calc.py` 改為載入它（package 與整合同一份邏輯；
  原有 38 個測試不變、全過）。
- `tools/gen_package.py` 同時把 `tariff/rates.json` 複製進整合；`--check` 兩者都比對。
- README：安裝改為 HACS 優先，package 保留為方法二。

## [0.1.0] - 2026-10-21

### 新增

- 初版 package：`packages/taipower_estimate.yaml`，七個 sensor（累積度數、已過天數、週期進度、預估度數、夏月占比、級距電價、預估電費）。
- 費率單一來源 `tariff/rates.json`：表燈(住商)非時間電價（住宅用／住宅以外非營業用／營業用），**2025-10-01 起實施**版本，
  2026-10-14 對照台電官方簡要電價表、詳細電價表、計算範例 PDF。
- 產生器 `tools/gen_package.py`（`--profile`、`--months`、`--source`、`--cron`、`--min-days`、`--check`）。
- 測試 38 個：官方算例（住宅 8 月 400 度 = 1,015 元；非營業用 800 度 = 3,067 元）、兩個月加倍級距、夏月占比、分母護欄、
  YAML 模板渲染結果對照參考實作、YAML 與 rates.json 不脫鉤。
- `docs/customize-with-agent.md`：給 AI agent 的個人化指引。`AGENTS.md`：調價 SOP（不綁特定瀏覽器工具）。
- README「現行費率版本」補 2026-09-18 審議會：暫不調整，12 月再議。

### 與先前草稿的差異

- 草稿（blog 稿）把費率標成「2026-04-01 版」並寫「2026 年 4 月調價，1.68→1.78」。**實施日是 2025-10-01**
  （官方電價表：中華民國 114 年 10 月 1 日起實施）；2026-03-27 審議會決議不調價。費率數字本身與草稿相同，只有日期與敘述錯。
- 夏月占比獨立成一個 sensor，電價與電費共用，不再各算一次。
- 新增週期進度 sensor；`Power cycle days` 在沒有 `last_reset` 時改為 `unavailable`（草稿是字串 `unknown`）。
- 夏月占比先把 `last_reset` 轉成本地時間再數月份（HA 的 `last_reset` 常是 UTC，台北 00:00 歸零的週期不轉會把起算日當成前一天）。

授權：MIT。
