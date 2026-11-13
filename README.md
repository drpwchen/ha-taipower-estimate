# ha-taipower-estimate

台電**兩個月一期**（或每月一期）的電費估算，給 Home Assistant 用。兩種裝法：
**HACS 整合**（UI 設定，不碰 YAML；建議）或 **YAML package**。都會多出七個 sensor：
這期用了多少度、**過了幾天**（分母）、週期進度、預估整期度數、現在落在哪一級、預估電費。

跟其他台電電費整合不一樣的地方：

- **看得到分母。** 「週期已過天數」是獨立的 sensor；分母不到 3 天，預估、電價、電費全部 `unavailable`，不會在抄表日 00:01 因為「一分鐘的用電 × 60 天」跳到最高級。
- **只有一個地方會歸零**：抄表日 00:00（整合用設定裡的抄表日；package 用 `utility_meter` 的 cron）。沒有別的自動化在重設。
- **沒有外部 API、沒有帳密、沒有 cookie。** 只吃你本來就有的電表總累積度數 sensor，所以不會因為台電改網站而壞。
- **費率單一來源**：`tariff/rates.json`，每個數字附台電官方 PDF 連結。台電調價時改一個檔、跑一個指令、跑測試；
  整合版發新版後 HACS 會提示更新，不用自己重抄 YAML。

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

兩種裝法都需要一個**電表總累積度數**的 sensor（單位 kWh、只增不減，`state_class: total_increasing`）。
每天／每月自己歸零的 sensor 不能當來源。

### 方法一：Marketplace／HACS 整合（建議）

[![在 Home Assistant 開啟](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=drpwchen&repository=ha-taipower-estimate&category=integration)

上面的按鈕會直接開到這個 repo（2026.11 以上開 Marketplace，更舊的版本開 HACS）。要手動加的話：

**Home Assistant 2026.11 以上（內建 Marketplace）**

1. 設定 → **Marketplace** → 右上角 **Add from link**。
2. GitHub link 貼 `drpwchen/ha-taipower-estimate`（或完整網址）→ **Add**。
   第一次用會要求連結 GitHub：畫面給一組代碼，到 GitHub 核准即可，不用在 HA 輸入 GitHub 密碼。
3. 開啟 **Taipower Bill Estimate** → **Install**。裝好通常直接進設定精靈；如果 HA 提示要重啟，照提示重啟。

**Home Assistant 2026.10 以前（HACS）**

1. HACS → 右上角 ⋮ → **Custom repositories** → Repository 填 `https://github.com/drpwchen/ha-taipower-estimate`，
   Type 選 **Integration** → Add。
2. 在 HACS 搜尋 **Taipower Bill Estimate** → Download → 重啟 Home Assistant。
3. 設定 → 裝置與服務 → 新增整合 → **Taipower Bill Estimate**。

設定精靈的欄位：

   | 欄位 | 填什麼 |
   |---|---|
   | 電表總累積度數 sensor | 你的總累積 kWh sensor |
   | 電價類別 | 住宅用／住宅以外非營業用／營業用 |
   | 抄表週期 | 兩個月一期／每月一期 |
   | 抄表日 | 看電費單的「計費期間」起日；該月沒有這天就用月底 |
   | 抄表月份 | 兩個月一期才用得到：奇數月（1、3、5…）或偶數月（2、4、6…） |
   | 這期已用度數（選填） | 知道從這期抄表日到現在用了多少度就填，第一期就準 |

   「這期已用度數」不填也可以：從裝好那一刻開始量，用實測的每日用電外推整期（`partial_cycle` 屬性為 `true`），
   不會像 package 版那樣第一期偏掉。之後要改設定：整合頁面 → **設定（選項）**。

台電調價時：發新版後會出現在 設定 → 更新（Marketplace 對手動加入的 repo 每 48 小時檢查一次），更新即可。

### 方法二：YAML package

需要：Home Assistant（有 `utility_meter` 與 template sensor 的版本，近幾年都有）。

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

| 整合版 entity | package 版 entity | 意義 |
|---|---|---|
| `sensor.taipower_cycle_energy` | `sensor.power_cycle_energy` | 這期已用度數（唯一會歸零的地方）。整合版屬性：`period_start`、`measure_start`、`next_reset`、`partial_cycle` |
| `sensor.taipower_cycle_days` | `sensor.power_cycle_days` | 已量測天數（分母） |
| `sensor.taipower_cycle_progress` | `sensor.power_cycle_progress` | 週期進度 %（這期已過天數 / 60，上限 100） |
| `sensor.taipower_cycle_estimate` | `sensor.power_cycle_estimate` | 預估整期度數＝已用 ÷ 分母 × 60；`confidence` 屬性 low(<7 天)／medium(<21)／high |
| `sensor.taipower_cycle_summer_ratio` | `sensor.power_cycle_summer_ratio` | 這個週期有幾成日子落在夏月 |
| `sensor.taipower_tier_price` | `sensor.power_tier_price` | 以預估度數落在的級距，每度電價（夏月／非夏月依天數加權） |
| `sensor.taipower_cycle_bill` | `sensor.power_cycle_bill` | 預估電費（逐級累進加總，元） |

（單月一期時，上表的 60 換成 30。整合版的顯示名稱跟著 HA 介面語言，entity_id 固定用上面的英文。）

想在預估電費超過某個數字時通知：條件加 `confidence == 'high'`，通知只在分母夠大時才會說話。

## 限制（先讀完再信數字）

- **這是估算，不是帳單。** 預估＝目前平均用電外推到整期，用電不均勻（出國、冷氣突然開）就會偏。
- **只支援非時間電價。** 時間電價（二段式／三段式）、低壓電力、太陽能躉購／淨計量不支援。
- **週期跨夏月（6/1 或 10/1 落在週期中）是近似。** 做法是依天數把夏月／非夏月電價加權混合；台電帳單的逐字算法我在官方電價表裡沒有找到明文，所以跨期那一期可能和帳單有幾元到幾十元差距。完全落在夏月或非夏月的週期，邏輯與官方範例一致（見測試）。
- **不含**：底度（電表容量最低計費）與「當月電費未滿 100 元以 100 元計收」、各種補助或節電獎勵、營業稅處理。
- package 版：來源電表 sensor 暫時 `unavailable` 時，已用度數會被當成 0，預估會偏低，不會變成 unavailable。
  整合版：`unavailable` 期間不更新，等下一個正常讀數時把中間的度數一次補回。
- 整合版：Home Assistant 關機時跨過抄表日，開機後會開新的一期，但停機期間的度數分不出屬於哪一期，
  所以從開機那刻重新量（`partial_cycle: true`）。電表讀數掉到上次的 90% 以下當成換表／電表歸零；小幅下降當成抖動忽略。
- 週期固定當 60 天（單月 30 天）外推；實際抄表間隔 59–62 天的誤差沒有修正。
- **整合版已在一台真實運作的 Home Assistant（2026.11.1）上跑過**：用 Marketplace 安裝、設定精靈（週期中途安裝並填入
  「這期已用度數」）、在選項裡換來源電表，七個 sensor 都正常，數字與參考實作一致。==還沒驗證到的==：實際跨過抄表日的
  歸零、和台電實際帳單的比對。整合版另有 HA core 2026.10.4 測試環境（`pytest-homeassistant-custom-component`）的自動測試
  （設定精靈、讀數累積、抄表日歸零、重新載入、改選項）。
- **package 版還沒有在真實運作中的 Home Assistant 上跑過**：測試是把 YAML 裡的 Jinja 模板用模擬的 HA 函式渲染、對照參考實作。
  第一次裝請對照你的電費單。
- `hacs.json` 標的最低版本 2024.12 是依程式用到的 API 推估，沒有在舊版 HA 實測。

## 開發與測試

```bash
pip install pyyaml jinja2
python -m unittest discover -s tests -v   # 計算、週期邏輯、YAML 模板（不需要 Home Assistant）
python tools/gen_package.py --check       # 已 commit 的 YAML、整合內附的 rates.json 與 tariff/rates.json 是否一致

# 整合在 HA core 裡的測試（Linux／WSL／macOS；HA 不支援 Windows，Python 3.14）
pip install pytest-homeassistant-custom-component
python -m pytest
```

測試內容：台電官方算例（住宅 8 月 400 度＝1,015 元、非營業用 800 度＝3,067 元）、兩個月加倍級距的手算值、
夏月占比的曆法、分母護欄（不到 3 天全部 unavailable）、YAML 裡的模板渲染結果＝參考實作、
YAML 與 `rates.json` 沒有脫鉤（手改 YAML 會被抓到）；整合版的抄表日排程（奇偶月、月底、跨年）、讀數抖動／換表、
停機錯過抄表日、換電表或改排程，以及在 HA core 裡的設定精靈與歸零。計算核心只有一份
（`custom_components/taipower_estimate/calc.py`），package 測試拿它當對照答案。

費率表（上方）是手抄的文件副本，調價時要跟 `tariff/rates.json` 一起改。台電調價時：見 [`AGENTS.md`](AGENTS.md)「調價 SOP」。變更紀錄見 [`CHANGELOG.md`](CHANGELOG.md)。
