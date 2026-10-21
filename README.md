# ha-taipower-estimate

台電**兩個月一期**的電費估算，Home Assistant package。丟一個 YAML 進 `packages/`，多出七個 sensor：
這期用了多少度、**過了幾天**（分母）、週期進度、預估整期度數、現在落在哪一級、預估電費。

跟其他台電電費整合不一樣的地方：

- **看得到分母。** 「週期已過天數」是獨立的 sensor；分母不到 3 天，預估、電價、電費全部 `unavailable`，不會在抄表日 00:01 因為「一分鐘的用電 × 60 天」跳到最高級。
- **只有一個地方會歸零**：`utility_meter` 的 cron。沒有別的自動化在重設。
- **沒有外部 API、沒有帳密、沒有 cookie。** 只吃你本來就有的電表總累積度數 sensor，所以不會因為台電改網站而壞。
- **費率單一來源**：`tariff/rates.json`，每個數字附台電官方 PDF 連結。台電調價時改一個檔、跑一個指令、跑測試。

> 授權：[MIT](LICENSE)。費率數字取自台電公開電價表，以台電官方公告為準。

## 現行費率版本

| 項目 | 內容 |
|---|---|
| 電價 | 表燈(住商)非時間電價（住宅用／住宅以外非營業用／營業用） |
| 實施日 | **2025-10-01**（中華民國 114 年 10 月 1 日起實施；奉經濟部 114 年 9 月 26 日經能字第 11458000380 號函核定） |
| 最後對照官方電價表 | 2026-10-14 |
| 2026-03-27 審議會 | 決議電價不調整，維持平均電價 3.7823 元/度（[經濟部能源署](https://www.moea.gov.tw/MNS/populace/news/News.aspx?kind=1&menu_id=40&news_id=122235)） |
| 2026-09-18 審議會 | 決議暫不調整，10 月起維持現行電價，留待 12 月審議會再議（2026-10-14 對照的官方電價表仍是 114-10-01 實施版） |

住宅用（每月度數分段；**兩個月抄表時各段度數加倍**，台電電價表註記）：

| 每月用電度數 | 夏月 6/1–9/30 | 非夏月 |
|---|---|---|
| 120 度以下 | 1.78 | 1.78 |
| 121–330 | 2.55 | 2.26 |
| 331–500 | 3.80 | 3.13 |
| 501–700 | 5.14 | 4.24 |
| 701–1000 | 6.44 | 5.27 |
| 1001 以上 | 8.86 | 7.03 |

來源（台電官方）：[簡要電價表 PDF](https://www.taipower.com.tw/media/dhuhrppu/%E7%B0%A1%E8%A6%81%E9%9B%BB%E5%83%B9%E8%A1%A8.pdf?mediaDL=true)、
[詳細電價表 PDF](https://www.taipower.com.tw/media/xtofy2yw/%E8%A9%B3%E7%B4%B0%E9%9B%BB%E5%83%B9%E8%A1%A8.pdf?mediaDL=true)、
[電價表頁](https://www.taipower.com.tw/2289/2290/46940/)。完整清單在 `tariff/rates.json`。

## 安裝

需要：Home Assistant（有 `utility_meter` 與 template sensor 的版本，近幾年都有），以及一個**電表總累積度數**的 sensor
（單位 kWh、`state_class: total_increasing`）。每天／每月自己歸零的 sensor 不能當來源。

1. 確認 `configuration.yaml` 有啟用 packages：
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
2. 把 [`packages/taipower_estimate.yaml`](packages/taipower_estimate.yaml) 複製到你的 `/config/packages/`。
3. 改兩個地方（或用產生器直接帶參數，見下）：
   - `source:` → 你的電表總累積度數 entity_id
   - `cron:` → 對齊你的抄表日。預設 `0 0 13 1,3,5,7,9,11 *`＝奇數月 13 日 00:00 歸零。看電費單的「計費期間」。
4. 開發者工具 → YAML → 檢查設定，沒錯誤再重啟 Home Assistant（新增 `utility_meter` 通常要重啟；只改 template 可只重新載入 template）。
5. 第一個完整週期之前，`utility_meter` 的 `last_reset` 是它第一次啟動的時間，不是真正的抄表日，預估會偏。**等到第一次 cron 歸零之後的週期才準。**

用產生器（不想手改 YAML 就用這個；需要 Python 3.9+，沒有其他依賴）：

```bash
python tools/gen_package.py --source sensor.my_meter_kwh --cron "0 0 5 2,4,6,8,10,12 *" --out my_package.yaml
python tools/gen_package.py --profile commercial --months 1 --out my_package.yaml   # 營業用、單月
```

要請 AI agent 幫你調成自家情況：把 [`docs/customize-with-agent.md`](docs/customize-with-agent.md) 丟給它。

## 會多出哪些 sensor

| entity | 意義 |
|---|---|
| `sensor.power_cycle_energy` | 這期已用度數（utility_meter，唯一會歸零的地方） |
| `sensor.power_cycle_days` | 這期已過天數（分母） |
| `sensor.power_cycle_progress` | 週期進度 %（已過天數 / 60，上限 100） |
| `sensor.power_cycle_estimate` | 預估整期度數＝已用 ÷ 已過天數 × 60；`confidence` 屬性 low(<7 天)／medium(<21)／high |
| `sensor.power_cycle_summer_ratio` | 這個週期有幾成日子落在夏月 |
| `sensor.power_tier_price` | 以預估度數落在的級距，每度電價（夏月／非夏月依天數加權） |
| `sensor.power_cycle_bill` | 預估電費（逐級累進加總，元） |

想在預估電費超過某個數字時通知：條件加 `confidence == 'high'`，通知只在分母夠大時才會說話。

## 限制（先讀完再信數字）

- **這是估算，不是帳單。** 預估＝目前平均用電外推到整期，用電不均勻（出國、冷氣突然開）就會偏。
- **只支援非時間電價。** 時間電價（二段式／三段式）、低壓電力、太陽能躉購／淨計量不支援。
- **週期跨夏月（6/1 或 10/1 落在週期中）是近似。** 做法是依天數把夏月／非夏月電價加權混合；台電帳單的逐字算法我在官方電價表裡沒有找到明文，所以跨期那一期可能和帳單有幾元到幾十元差距。完全落在夏月或非夏月的週期，邏輯與官方範例一致（見測試）。
- **不含**：底度（電表容量最低計費）與「當月電費未滿 100 元以 100 元計收」、各種補助或節電獎勵、營業稅處理。
- 來源電表 sensor 暫時 `unavailable` 時，已用度數會被當成 0，預估會偏低，不會變成 unavailable。
- 週期固定當 60 天（單月 30 天）外推；實際抄表間隔 59–62 天的誤差沒有修正。
- **還沒有在真實的 Home Assistant 上跑過。** 測試是把 YAML 裡的 Jinja 模板用模擬的 HA 函式渲染、對照參考實作（38 個測試，見下），不是在 HA 裡實測。第一次裝請對照 Developer Tools → Template 與你的電費單。

## 開發與測試

```bash
pip install pyyaml jinja2
python -m unittest discover -s tests -v
python tools/gen_package.py --check      # 已 commit 的 YAML 與 rates.json 是否一致
```

測試內容：台電官方算例（住宅 8 月 400 度＝1,015 元、非營業用 800 度＝3,067 元）、兩個月加倍級距的手算值、
夏月占比的曆法、分母護欄（不到 3 天全部 unavailable）、YAML 裡的模板渲染結果＝參考實作、
YAML 與 `rates.json` 沒有脫鉤（手改 YAML 會被抓到）。

費率表（上方）是手抄的文件副本，調價時要跟 `tariff/rates.json` 一起改。台電調價時：見 [`AGENTS.md`](AGENTS.md)「調價 SOP」。變更紀錄見 [`CHANGELOG.md`](CHANGELOG.md)。
