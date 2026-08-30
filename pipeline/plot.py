"""Plot the four metrics, their directional z-scores and the daily risk score,
with alert days and true illness onsets marked."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sentinel import (load, robust_z, risk_score, DIRECTION,
                      ALERT_THRESHOLD)

LABELS = {
    "HKQuantityTypeIdentifierRestingHeartRate": "Resting HR (bpm)",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "HRV SDNN (ms)",
    "HKQuantityTypeIdentifierRespiratoryRate": "Respiratory rate (br/min)",
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": "Wrist temp dev (°C)",
}

df = load("data/synthetic_export.json")
onsets = json.load(open("data/ground_truth.json"))["illness_onsets"]
z = robust_z(df)
risk = risk_score(z)
days = np.arange(len(df))
alerts = days[(risk > ALERT_THRESHOLD).fillna(False).to_numpy()]

fig, axes = plt.subplots(6, 1, figsize=(11, 13), sharex=True,
                         gridspec_kw={"height_ratios": [1, 1, 1, 1, 1.3, 1.3]})

for ax, col in zip(axes, DIRECTION):
    ax.plot(days, df[col].to_numpy(), lw=1.2, color="#2b6cb0")
    ax.set_ylabel(LABELS[col], fontsize=8)
    ax.grid(alpha=0.25)

ax = axes[4]
for col in DIRECTION:
    ax.plot(days, z[col].to_numpy(), lw=1.0, alpha=0.75, label=LABELS[col])
ax.axhline(0, color="k", lw=0.6)
ax.set_ylabel("directional z", fontsize=8)
ax.legend(fontsize=6, ncol=2, loc="upper left")
ax.grid(alpha=0.25)

ax = axes[5]
ax.plot(days, risk.to_numpy(), lw=1.6, color="#c53030")
ax.axhline(ALERT_THRESHOLD, ls="--", color="k", lw=0.8,
           label=f"alert threshold ({ALERT_THRESHOLD})")
ax.scatter(alerts, risk.to_numpy()[alerts], color="#c53030", zorder=5, s=28,
           label="alert")
ax.set_ylabel("risk score", fontsize=8)
ax.set_xlabel("day")
ax.legend(fontsize=7, loc="upper left")
ax.grid(alpha=0.25)

for ax in axes:
    for onset in onsets:
        ax.axvspan(onset - 2, onset + 4, color="#f6ad55", alpha=0.25, zorder=0)

axes[0].set_title("Sentinel — illness early-warning from Apple Watch metrics\n"
                  "(orange = true illness episode, synthetic data)", fontsize=11)
fig.tight_layout()
fig.subplots_adjust(left=0.11)
fig.savefig("sentinel_timeline.png", dpi=150)
print("wrote sentinel_timeline.png")
