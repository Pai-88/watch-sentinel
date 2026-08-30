"""Sweep the alert threshold and agreement gate to trade off lead time
against false alarms."""
import json
import numpy as np
from sentinel import load, robust_z, risk_score
import sentinel

df = load("data/synthetic_export.json")
onsets = json.load(open("data/ground_truth.json"))["illness_onsets"]
z = robust_z(df)

print(f"{'agree':>5} {'thresh':>7} {'detected':>9} {'lead':>6} {'false':>6}")
for min_agree in (2, 3):
    sentinel.MIN_AGREE = min_agree
    risk = risk_score(z)
    for thresh in np.arange(1.0, 3.01, 0.25):
        alerts = np.flatnonzero((risk > thresh).fillna(False).to_numpy())
        leads, detected = [], 0
        for onset in onsets:
            early = [a for a in alerts if onset - 3 <= a <= onset + 3]
            if early:
                detected += 1
                leads.append(onset - min(early))
        false = sum(1 for a in alerts if all(abs(a - o) > 4 for o in onsets))
        lead = f"{np.mean(leads):+.1f}" if leads else "  -"
        print(f"{min_agree:>5} {thresh:>7.2f} {detected:>6}/{len(onsets)} {lead:>6} {false:>6}")
