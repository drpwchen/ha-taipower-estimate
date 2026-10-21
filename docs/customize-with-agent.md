# 給 AI agent：幫使用者個人化這個 package

你（Claude Code、Codex 等）被請來把 `ha-taipower-estimate` 調成「這個使用者家裡」的版本。
先讀完這份，再動手。原則：**只動產生器的參數；費率不憑記憶，一律以台電官方電價表為準；
沒有跑過驗證不准說完成。**

## 0. 你要知道的結構

| 檔案 | 角色 | 你能不能改 |
|---|---|---|
| `tariff/rates.json` | 費率與級距的**唯一來源**（含實施日、官方來源連結） | 只在台電調價、或要新增電價類別時改 |
| `tools/gen_package.py` | 由 rates.json + 模板產生 YAML；參數＝使用者的個人化選項 | 改參數用；改邏輯要補測試 |
| `tools/package.yaml.tmpl` | YAML 模板 | 只在要改 sensor 行為時改 |
| `packages/taipower_estimate.yaml` | **產生物**（會被測試比對） | ==不要手改== |
| `tools/taipower_calc.py` | 參考計算（測試的對照答案） | 邏輯變動時一起改 |
| `tests/` | 測試 | 動邏輯就補測試 |

使用者只想要「自己家能用的 YAML」：產一份到別的路徑（`--out`），不要弄髒 repo 裡的預設檔。

## 1. 先問使用者的問題（一次問完，缺一不可）

每題後面寫的是「答案會改什麼」。答不出會改什麼的題，不要問。

1. **電價類別？** 住宅用 → `--profile residential`；機關學校等非營業 → `non_commercial`；商店／營業用 → `commercial`。
   看電費單的「電價種類」欄。**若是時間電價（二段式／三段式）、低壓電力、有太陽能躉購或淨計量：這個 package 不支援，如實告訴使用者，不要硬套。**
2. **單月還是兩個月抄表？** → `--months 1|2`（決定級距是否加倍、週期天數 30／60）。電費單通常一張涵蓋兩個月。
3. **哪一天抄表？** 電費單的「計費期間」。→ `--cron`。
   例：奇數月 13 日 00:00 → `"0 0 13 1,3,5,7,9,11 *"`；偶數月 5 日 → `"0 0 5 2,4,6,8,10,12 *"`；每月 1 日 → `"0 0 1 * *"`。
   五個欄位依序是：分 時 日 月 星期。抄表日可能每期差一兩天，取最常見的那天。
4. **電表總累積度數的 entity_id 是什麼？** → `--source`。
   - 條件：單位 kWh、`state_class: total_increasing`。到 HA 的 Developer Tools → States 查它的 attributes 確認。
   - 如果使用者只有功率（W）：先建 Riemann 積分 sensor（helper）再當 source；不要把 W 當 kWh 餵進去。
   - 如果有多個電表／迴路要加總：先建一個加總 sensor，再當 source。
   - 每日／每月會自己歸零的 sensor 不能當 source。
5. **要通知嗎？** 要的話：條件一定加 `confidence == 'high'`（分母夠大才說話），並問閾值（預估電費超過多少元）。這個要另外寫 automation，產生器不產。

不要問使用者「級距是多少」「現在電價多少」——那是你的工作，從 `tariff/rates.json` 與官方電價表查。

## 2. 動手

```bash
# 在 repo 根目錄；Python 3.9+，產生器沒有外部依賴
python tools/gen_package.py \
  --profile residential --months 2 \
  --source sensor.<使用者的 entity> \
  --cron "<使用者的抄表 cron>" \
  --out <使用者 HA config 裡的 packages/taipower_estimate.yaml 或暫存路徑>
```

產出檔開頭註解會記錄你用的參數（重產指令）。把這行留著，使用者以後調價時能重產。

## 3. 驗證（要做完才算完成）

1. `pip install pyyaml jinja2 && python -m unittest discover -s tests -v` 全綠（證明模板邏輯＝參考實作）。
2. 用你選的參數再跑一次「對照」：`python tools/gen_package.py <同樣參數> --out <暫存>`，確認 YAML 能被 PyYAML 讀進來（`python -c "import yaml,sys;yaml.safe_load(open(sys.argv[1],encoding='utf-8'))" <檔>`）。
3. 如果你碰得到使用者的 HA：
   - Developer Tools → YAML → 「檢查設定」無錯誤；
   - 載入後 `sensor.power_cycle_days` 有值，`sensor.power_cycle_estimate` 在週期第 3 天前是 unavailable（這是設計，不是壞掉）；
   - 用 Developer Tools → Template 貼 `{{ states('sensor.power_cycle_bill') }}`，對照使用者**上一期電費單**：把上一期總度數與夏月天數代進 `tools/taipower_calc.py` 的 `bill()`，應與帳單在合理範圍內（跨夏月那期可能差幾十元，見 README 限制）。
   - 碰不到使用者的 HA：明說「我沒在你的 HA 上驗證過」，並把上面三點交給使用者做。
4. 回報時列出：用了哪些參數、測試輸出最後一行、哪些項目你**沒**驗證。

## 4. 常見需求怎麼處理

| 使用者說 | 做法 |
|---|---|
| 「我家是營業用」 | `--profile commercial`（級距 330／700／1500／3000，已收錄）。 |
| 「我想改 sensor 名稱」 | 改 `tools/package.yaml.tmpl`（`sensor.power_*` 彼此在模板裡互相引用，要全部同步改，一個都不能漏），重產並跑測試；測試裡寫死了預設 entity_id，要一起改。不要在產出檔上 sed。 |
| 「台電調價了」 | 照 `AGENTS.md` 的調價 SOP；數字只信官方 PDF，不信新聞或部落格。 |
| 「要加通知／LINE」 | 另寫 automation（不在 package 內）；觸發條件加 `confidence == 'high'`。 |
| 「要時間電價」 | 不支援。誠實說；若使用者堅持，是新功能（需新的資料結構與測試），不是調參數。 |
| 「數字跟帳單差很多」 | 先檢查：cron 是否對齊抄表日、source 是否真的是總累積度數、首期（`last_reset` 是啟動時間）、跨夏月期。不要先去改費率。 |

## 5. 紅線

- 不要憑記憶改費率；改了就要附官方連結與抓取日期，更新 `effective_date`／`verified_on`。
- 不要手改 `packages/taipower_estimate.yaml`（測試會抓到）。
- 不要把使用者的 entity_id、cron 之類個人資料 commit 回這個 repo 的預設檔（個人化產物放別處）。
- 驗證沒跑就不要說「可以用了」。
