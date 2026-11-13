"""抄表週期的狀態與計算（純 Python，不 import Home Assistant，方便單元測試）。

名詞：
  period_start   這期的抄表起算時間（排程算出來的抄表日 00:00，本地時間）。進度、夏月占比用它。
  measure_start  開始量測的時間＝外推的分母起點。正常等於 period_start；
                 安裝在週期中途、或 HA 停機錯過抄表日時會晚於 period_start（partial）。
  used           measure_start 以來累積的度數（只有在抄表日歸零）。
  last_value     上一次看到的電表總累積讀數；None ＝ 下一個讀數只當基準、不計入。
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import calc

ON_TIME_GRACE = timedelta(minutes=10)   # 計時器晚這麼多以內仍算「準時歸零」
METER_RESET_RATIO = 0.9                 # 讀數掉到上次的 90% 以下才當成電表歸零／換表


@dataclass(frozen=True)
class Schedule:
    months: int          # 1＝每月抄表，2＝兩個月抄表
    day: int             # 抄表日（1–31；該月沒有這天就用月底）
    parity: str = "odd"  # 兩個月抄表時，抄表月是奇數月（odd）或偶數月（even）

    @property
    def cycle_days(self) -> int:
        return 30 * self.months

    @property
    def signature(self) -> str:
        return f"{self.months}/{self.day}/{self.parity if self.months == 2 else '-'}"

    def is_reading_month(self, month: int) -> bool:
        if self.months == 1:
            return True
        return (month % 2 == 1) == (self.parity == "odd")

    def _at(self, year: int, month: int, tz) -> datetime:
        day = min(self.day, calendar.monthrange(year, month)[1])
        return datetime(year, month, day, tzinfo=tz)

    def last_reset(self, now: datetime) -> datetime:
        """now 當下（含）以前最近一次抄表時間。"""
        y, m = now.year, now.month
        for _ in range(14):
            if self.is_reading_month(m):
                t = self._at(y, m, now.tzinfo)
                if t <= now:
                    return t
            y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        raise AssertionError("unreachable")

    def next_reset(self, after: datetime) -> datetime:
        """after 之後（不含）下一次抄表時間。"""
        y, m = after.year, after.month
        for _ in range(14):
            if self.is_reading_month(m):
                t = self._at(y, m, after.tzinfo)
                if t > after:
                    return t
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        raise AssertionError("unreachable")


@dataclass
class CycleState:
    period_start: datetime
    measure_start: datetime
    used: float = 0.0
    last_value: float | None = None
    schedule_sig: str = ""
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "period_start": self.period_start.isoformat(),
            "measure_start": self.measure_start.isoformat(),
            "used": self.used,
            "last_value": self.last_value,
            "schedule_sig": self.schedule_sig,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CycleState:
        return cls(
            period_start=datetime.fromisoformat(d["period_start"]),
            measure_start=datetime.fromisoformat(d["measure_start"]),
            used=float(d.get("used", 0.0)),
            last_value=d.get("last_value"),
            schedule_sig=d.get("schedule_sig", ""),
            source=d.get("source", ""),
        )


def new_state(schedule: Schedule, now: datetime, source: str, initial_used: float | None = None) -> CycleState:
    """第一次安裝。有給「這期已用度數」→ 從這期抄表日起算；沒給 → 從現在開始量（partial）。"""
    start = schedule.last_reset(now)
    if initial_used is not None:
        return CycleState(start, start, float(initial_used), None, schedule.signature, source)
    return CycleState(start, now, 0.0, None, schedule.signature, source)


def reconcile(state: CycleState, schedule: Schedule, now: datetime, source: str) -> str:
    """啟動／重新載入時把存檔對齊現況。回傳做了什麼（給 log／測試）。

    - 換了電表 sensor：下一個讀數只當基準（不同電表的讀數不能相減）。
    - 換了抄表排程：period_start 對齊新排程，已用度數與分母保留（外推是速率，仍然有效）。
    - 排程沒換但已經過了抄表日（HA 停機錯過）：開新的一期；停機期間的度數分不出歸屬，
      所以從現在重新量（partial），不把上期的用量算進來。
    """
    actions = []
    if state.source != source:
        state.source = source
        state.last_value = None
        actions.append("source_changed")
    lr = schedule.last_reset(now)
    if state.schedule_sig != schedule.signature:
        state.schedule_sig = schedule.signature
        state.period_start = lr
        if state.measure_start < lr:
            # 新排程的這期起點比原本的量測起點晚：舊的用量不屬於這期，重來
            state.measure_start, state.used, state.last_value = now, 0.0, None
        actions.append("schedule_changed")
    elif state.period_start < lr:
        roll_over(state, schedule, now)
        actions.append("rolled_over_late" if state.measure_start > state.period_start else "rolled_over")
    return ",".join(actions) or "ok"


def roll_over(state: CycleState, schedule: Schedule, now: datetime) -> None:
    """到了抄表日：歸零開新的一期。計時器準時觸發時分母從抄表日起算；太晚（停機）就從現在算。"""
    lr = schedule.last_reset(now)
    state.period_start = lr
    state.used = 0.0
    if now - lr <= ON_TIME_GRACE:
        state.measure_start = lr          # last_value 保留：歸零當下的讀數就是新一期的基準
    else:
        state.measure_start = now
        state.last_value = None           # 停機期間跨期的度數不能算進新的一期


def apply_reading(state: CycleState, value: float) -> float:
    """吃一個電表總累積讀數，回傳這次加進 used 的度數。

    讀數下降：掉很多（< 上次 × 0.9）當成電表歸零／換表，新讀數整個算用量（同 utility_meter
    total_increasing）；小幅下降當成抖動，忽略且不更新基準。
    """
    if state.last_value is None:
        state.last_value = value
        return 0.0
    delta = value - state.last_value
    if delta < 0:
        if value < state.last_value * METER_RESET_RATIO:
            delta = value
        else:
            return 0.0
    state.used += delta
    state.last_value = value
    return delta


@dataclass
class Snapshot:
    energy: float
    days: float
    progress: float
    estimate: int | None
    confidence: str
    summer_ratio: float
    tier_price: float | None
    bill: int | None
    period_start: datetime
    measure_start: datetime
    next_reset: datetime
    partial: bool
    extra: dict = field(default_factory=dict)


def compute(state: CycleState, schedule: Schedule, now: datetime, rates: dict, profile: str,
            min_days: float = 3) -> Snapshot:
    cd = schedule.cycle_days
    days = max((now - state.measure_start).total_seconds() / 86400, 0.0)
    elapsed = max((now - state.period_start).total_seconds() / 86400, 0.0)
    ratio = calc.summer_ratio(state.period_start.date(), cd, tuple(rates["summer_months"]))
    estimate = price = amount = None
    if days >= min_days:
        estimate = int(round(state.used / days * cd))
        table = calc.bands(rates, profile, schedule.months)
        price = calc.tier_price(estimate, ratio, table)
        amount = calc.bill(estimate, ratio, table)
    return Snapshot(
        energy=round(state.used, 3),
        days=round(days, 2),
        progress=round(min(elapsed / cd * 100, 100), 1),
        estimate=estimate,
        confidence="low" if days < 7 else "medium" if days < 21 else "high",
        summer_ratio=ratio,
        tier_price=price,
        bill=amount,
        period_start=state.period_start,
        measure_start=state.measure_start,
        next_reset=schedule.next_reset(now),
        partial=state.measure_start > state.period_start,
    )
