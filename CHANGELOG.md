# Changelog

格式參考 Keep a Changelog；版本號：費率更新 → minor，邏輯修正 → patch。

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
