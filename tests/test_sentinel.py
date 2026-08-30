"""Tests for the Sentinel illness detector.

The first test is the important one: it proves the detector cannot see the
future. Everything else here is guarding behaviour that is easy to break
silently during tuning.
"""
import numpy as np
import pandas as pd
import pytest

import sentinel
from sentinel import DIRECTION, robust_z, risk_score

METRICS = list(DIRECTION)
RHR, HRV, RESP, TEMP = METRICS


def make_df(n=80, seed=0):
    """A well, boring subject: flat baselines plus mild noise."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        RHR: 52 + rng.normal(0, 1.0, n),
        HRV: 65 + rng.normal(0, 4.0, n),
        RESP: 14.5 + rng.normal(0, 0.3, n),
        TEMP: rng.normal(0, 0.12, n),
    }, index=[f"day_{i:03d}" for i in range(n)])


# --------------------------------------------------------------------------
# Causality — the claim the whole method rests on
# --------------------------------------------------------------------------

def test_z_scores_do_not_depend_on_the_future():
    """Perturbing later days must not change any earlier day's z-score.

    A real-time detector only ever has the past. If this fails, the baseline
    is peeking ahead and every reported lead time is meaningless.
    """
    df = make_df()
    before = robust_z(df)

    tampered = df.copy()
    cut = 50
    tampered.iloc[cut:] += 1000.0  # absurd future values

    after = robust_z(tampered)

    pd.testing.assert_frame_equal(before.iloc[:cut], after.iloc[:cut])


def test_risk_score_does_not_depend_on_the_future():
    """Same guarantee, end to end through the scoring stage."""
    df = make_df()
    before = risk_score(robust_z(df))

    tampered = df.copy()
    cut = 50
    tampered.iloc[cut:] += 1000.0

    after = risk_score(robust_z(tampered))

    pd.testing.assert_series_equal(before.iloc[:cut], after.iloc[:cut])


def test_no_score_before_minimum_history():
    """With too little history there is no baseline, so there is no score."""
    z = robust_z(make_df())
    assert z.iloc[: sentinel.MIN_HISTORY].isna().all().all()


# --------------------------------------------------------------------------
# Direction — each metric must point the "getting ill" way
# --------------------------------------------------------------------------

@pytest.mark.parametrize("metric,shift", [
    (RHR, +12.0),    # resting HR rises when ill
    (HRV, -30.0),    # HRV falls when ill
    (RESP, +4.0),    # respiratory rate rises
    (TEMP, +1.0),    # wrist temperature rises
])
def test_illness_direction_gives_positive_z(metric, shift):
    df = make_df()
    df.iloc[-1, df.columns.get_loc(metric)] += shift
    assert robust_z(df)[metric].iloc[-1] > 2.0


def test_healthy_direction_gives_negative_z():
    """A metric moving the *healthy* way must not read as illness."""
    df = make_df()
    df.iloc[-1, df.columns.get_loc(HRV)] += 30.0   # HRV up = good
    assert robust_z(df)[HRV].iloc[-1] < 0


# --------------------------------------------------------------------------
# The agreement gate
# --------------------------------------------------------------------------

def z_row(values):
    return pd.DataFrame([dict(zip(METRICS, values))])


def test_lone_elevated_metric_scores_zero():
    """One wild metric is a hot shower, not an illness."""
    assert risk_score(z_row([5.0, 0.0, 0.0, 0.0])).iloc[0] == 0.0


def test_two_elevated_metrics_still_gated():
    assert risk_score(z_row([3.0, 3.0, 0.0, 0.0])).iloc[0] == 0.0


def test_three_agreeing_metrics_score_their_mean():
    score = risk_score(z_row([2.0, 2.0, 2.0, 0.0])).iloc[0]
    assert score == pytest.approx(2.0)


def test_gate_scales_to_a_three_metric_export():
    """A watch not worn to bed yields no wrist temperature. The gate must
    adapt, or 3-of-4 becomes unsatisfiable and the detector goes silent."""
    three = pd.DataFrame([{RHR: 2.0, HRV: 2.0, RESP: 0.0}])
    assert risk_score(three).iloc[0] == pytest.approx(2.0)


def test_two_metric_export_requires_both():
    two_agree = pd.DataFrame([{RHR: 2.0, HRV: 2.0}])
    one_only = pd.DataFrame([{RHR: 5.0, HRV: 0.0}])
    assert risk_score(two_agree).iloc[0] == pytest.approx(2.0)
    assert risk_score(one_only).iloc[0] == 0.0


def test_negative_z_never_raises_the_score():
    """Metrics moving the healthy way must not be averaged in as positives."""
    gated = risk_score(z_row([2.0, 2.0, 2.0, -50.0])).iloc[0]
    assert gated == pytest.approx(2.0)


# --------------------------------------------------------------------------
# Robustness
# --------------------------------------------------------------------------

def test_baseline_survives_a_previous_illness():
    """Median/MAD baseline must not absorb an earlier spike as 'normal'.

    With a mean/std baseline, a past illness inflates the baseline and blunts
    the next detection. That silent failure is what median/MAD prevents.
    """
    df = make_df(n=120)
    df.iloc[40:47, df.columns.get_loc(RHR)] += 10.0   # an earlier illness
    df.iloc[-1, df.columns.get_loc(RHR)] += 10.0      # today, same magnitude

    z = robust_z(df)
    assert z[RHR].iloc[-1] > 3.0


def test_end_to_end_detects_both_synthetic_illnesses():
    """The headline synthetic result, pinned so tuning cannot silently break it."""
    from pathlib import Path
    import json

    root = Path(__file__).resolve().parent.parent / "pipeline"
    df = sentinel.load(str(root / "data" / "synthetic_export.json"))
    onsets = json.loads((root / "data" / "ground_truth.json").read_text())["illness_onsets"]

    risk = risk_score(robust_z(df))
    alerts = np.flatnonzero((risk > sentinel.ALERT_THRESHOLD).fillna(False).to_numpy())

    for onset in onsets:
        assert any(onset - 3 <= a <= onset + 3 for a in alerts), f"missed {onset}"

    false_alarms = [a for a in alerts if all(abs(a - o) > 4 for o in onsets)]
    assert not false_alarms, f"false alarms on {false_alarms}"
