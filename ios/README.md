# Sentinel — iOS HealthKit exporter

Pulls 90 days of daily physiological metrics out of HealthKit and hands them to
the Python detector in `../pipeline/`.

The Xcode project is already generated and **verified building** — an unsigned
device build produces a real `Sentinel.app` with no warnings:

```bash
cd ~/Documents/watch_sentinel/ios && xcodebuild -project Sentinel.xcodeproj \
  -target Sentinel -sdk iphoneos CODE_SIGNING_ALLOWED=NO build
```

What remains needs your Apple ID and your physical iPhone, so it can't be
scripted.

## Metrics pulled

| HealthKit type | Why it's here |
|---|---|
| `restingHeartRate` | rises during the illness prodrome |
| `heartRateVariabilitySDNN` | falls (parasympathetic withdrawal) |
| `respiratoryRate` | rises overnight |
| `appleSleepingWristTemperature` | rises; needs Series 8+ / Ultra |

## Steps

1. **Open the project**

   ```bash
   open ~/Documents/watch_sentinel/ios/Sentinel.xcodeproj
   ```

2. **Set your signing team.** Select the blue `Sentinel` project in the left
   sidebar → the `Sentinel` target → **Signing & Capabilities** tab.
   Tick *Automatically manage signing* and pick your name under **Team**.
   A free Apple ID works fine; add one via Xcode → Settings → Accounts if the
   Team dropdown is empty.

   The bundle identifier is `com.paing.Sentinel`. If Xcode complains it is
   already taken, change it to something unique on the same screen.

3. **Confirm the HealthKit capability is present.** It should already be listed
   on that same Signing & Capabilities tab, because `Sentinel.entitlements`
   declares it. If it isn't, click **+ Capability** and add *HealthKit*.

4. **Plug in your iPhone**, select it as the run destination in the toolbar,
   and press ⌘R.

5. **Trust the developer certificate** on the phone the first time:
   Settings → General → VPN & Device Management → your Apple ID → Trust.
   (This step only exists for free Apple IDs, and the app expires after 7 days —
   just re-run from Xcode to renew it.)

6. **In the app:** tap *Export last 90 days*, grant every health category when
   iOS asks, then tap *Share export* and AirDrop `sentinel_export.json` to this
   Mac.

7. **Point the pipeline at it:**

   ```bash
   cp ~/Downloads/sentinel_export.json ~/Documents/watch_sentinel/pipeline/data/
   ```

   then change the path in `pipeline/sentinel.py` (bottom of the file) from
   `data/synthetic_export.json` to `data/sentinel_export.json`, and re-run
   `tune.py` — the thresholds tuned on synthetic data will not be right for you.

## Gotchas

- **HealthKit returns nothing in the Simulator.** There is no watch and no
  health data there. This app is only meaningful on a real iPhone paired with
  your Watch.
- **Wrist temperature needs Series 8 or newer**, and only records during sleep
  tracking. On older watches that column will simply be absent and the detector
  will fall back to the three metrics it does have — but note that
  `MIN_AGREE = 3` out of 4 becomes much stricter when only 3 metrics exist, so
  drop it to 2 in that case.
- **You need real illness dates** to evaluate anything. Keep a note of any day
  you felt ill; without labels you can only look at the risk curve, not score it.
