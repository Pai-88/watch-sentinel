"""Sentinel: personalised illness early-warning from Apple Watch daily metrics.

Stage 1 (this file): robust per-metric baseline -> directional z-scores ->
combined daily risk score -> alert days, evaluated against ground truth.

Reads the same JSON schema the Sentinel iOS app exports, so swapping in
real data later is a one-line path change.
"""
import json
import numpy as np
import pandas as pd

# Direction each metric moves when you're getting ill: +1 rises, -1 falls.
DIRECTION = {
    "HKQuantityTypeIdentifierRestingHeartRate": +1,
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": -1,
    "HKQuantityTypeIdentifierRespiratoryRate": +1,
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": +1,
}

BASELINE_WINDOW = 28   # days of trailing history used as "your normal"
MIN_HISTORY = 14       # don't score until we have at least this much
ELEVATED_Z = 1.0        # a metric counts as "off" above this robust z
MIN_AGREE = 3           # how many metrics must agree before we score at all
ALERT_THRESHOLD = 1.75  # daily risk above this raises an alert
# MIN_AGREE/ALERT_THRESHOLD chosen by tune.py; re-run it on real data, since
# two synthetic events is far too few to trust these numbers on their own.


def load(path: str) -> pd.DataFrame:
    with open(path) as f:
        records = json.load(f)
    df = pd.DataFrame([{"date": r["date"], **r["metrics"]} for r in records])
    return df.set_index("date")


def robust_z(df: pd.DataFrame) -> pd.DataFrame:
    """Directional robust z-score of each day vs the TRAILING window only
    (no look-ahead: a real-time system can't see the future).
    Uses median/MAD instead of mean/std so illness days themselves
    don't inflate the baseline they're compared against."""
    z = pd.DataFrame(index=df.index, columns=df.columns, dtype=float)
    for col in df.columns:
        x = df[col]
        med = x.shift(1).rolling(BASELINE_WINDOW, min_periods=MIN_HISTORY).median()
        mad = (x.shift(1) - med).abs().rolling(BASELINE_WINDOW, min_periods=MIN_HISTORY).median()
        z[col] = DIRECTION[col] * (x - med) / (1.4826 * mad)
    return z


def risk_score(z: pd.DataFrame) -> pd.Series:
    """Combine per-metric directional z-scores into one daily risk score.

    Multi-signal agreement is what separates illness from a bad night's sleep,
    so a lone elevated metric scores zero: several metrics must be above
    ELEVATED_Z before the day is scored at all.

    The gate scales to how many metrics the export actually contains. Wrist
    temperature and respiratory rate are only recorded during sleep tracking,
    so a watch that is not worn to bed — or one older than Series 8 — yields
    two metrics, not four. Demanding a fixed 3-of-4 there is unsatisfiable and
    would silently return no alerts forever, which looks identical to "you were
    never ill".
    """
    n = z.shape[1]
    gate = max(2, min(MIN_AGREE, n - 1))      # 4 metrics->3, 3->2, 2->both
    pos = z.clip(lower=0)                     # only "getting ill" deviations count
    elevated = z > ELEVATED_Z                 # which metrics look off today
    agree = elevated.sum(axis=1) >= gate      # multi-signal agreement gate
    score = pos.where(elevated).mean(axis=1)  # mean of the elevated metrics only
    score = score.where(agree, 0.0)           # gate: lone outliers score zero
    return score.where(z.notna().any(axis=1)) # keep NaN before history exists


def evaluate(risk: pd.Series, onsets: list[int]) -> None:
    alerts = np.flatnonzero((risk > ALERT_THRESHOLD).fillna(False).to_numpy())
    print(f"alert days: {alerts.tolist()}")
    for onset in onsets:
        early = [a for a in alerts if onset - 3 <= a <= onset + 3]
        if early:
            lead = onset - min(early)
            print(f"illness at day {onset}: DETECTED, lead time {lead:+d} days")
        else:
            print(f"illness at day {onset}: MISSED")
    healthy = [a for a in alerts if all(abs(a - o) > 4 for o in onsets)]
    print(f"false alarms on healthy days: {len(healthy)} ({healthy})")


if __name__ == "__main__":
    df = load("data/synthetic_export.json")
    onsets = json.load(open("data/ground_truth.json"))["illness_onsets"]
    z = robust_z(df)
    risk = risk_score(z)
    evaluate(risk, onsets)
