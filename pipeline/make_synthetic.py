"""Generate synthetic watch data so the pipeline can be developed and tested
before the real Sentinel iOS export exists.

Simulates 120 days of a healthy baseline with circadian-ish weekly noise,
plus two 'illness' episodes where (as in the wearables literature):
  RHR rises, HRV falls, respiratory rate rises, wrist temp rises,
starting ~2 days before 'symptom onset'.
"""
import json
import numpy as np

rng = np.random.default_rng(7)
N = 120
days = np.arange(N)

# Personal baselines (typical young adult)
rhr = 52 + 1.5 * np.sin(2 * np.pi * days / 7) + rng.normal(0, 1.2, N)
hrv = 65 + 4.0 * np.sin(2 * np.pi * days / 7 + 1) + rng.normal(0, 5.0, N)
resp = 14.5 + rng.normal(0, 0.4, N)
temp = 0.0 + rng.normal(0, 0.15, N)   # deviation from personal baseline, degC

ILLNESS_ONSETS = [45, 95]  # ground-truth symptom-onset days
for onset in ILLNESS_ONSETS:
    for d in range(onset - 2, onset + 5):        # prodrome 2 days before onset
        if 0 <= d < N:
            severity = np.exp(-0.5 * ((d - onset - 1) / 2.0) ** 2)  # peak day after onset
            rhr[d] += 8 * severity
            hrv[d] -= 18 * severity
            resp[d] += 2.0 * severity
            temp[d] += 0.6 * severity

records = []
for i in range(N):
    records.append({
        "date": f"day_{i:03d}",
        "metrics": {
            "HKQuantityTypeIdentifierRestingHeartRate": round(rhr[i], 1),
            "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": round(hrv[i], 1),
            "HKQuantityTypeIdentifierRespiratoryRate": round(resp[i], 2),
            "HKQuantityTypeIdentifierAppleSleepingWristTemperature": round(temp[i], 2),
        },
    })

with open("data/synthetic_export.json", "w") as f:
    json.dump(records, f, indent=1)
with open("data/ground_truth.json", "w") as f:
    json.dump({"illness_onsets": ILLNESS_ONSETS}, f)
print(f"wrote {N} days, illnesses at {ILLNESS_ONSETS}")
