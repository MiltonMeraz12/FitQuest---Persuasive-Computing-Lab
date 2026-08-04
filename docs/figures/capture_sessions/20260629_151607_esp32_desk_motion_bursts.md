# Capture Analysis - 20260629_151607_esp32_desk_motion_bursts

- Label: esp32_desk_motion_bursts
- Frames: 276
- Duration: 16.176 s
- Effective FPS: 17.062
- ESP32 sample ratio: 1.0
- Wearable HR ratio: 0.0
- Wearable motion cross-check ratio: 0.0
- Pose ready ratio: 0.576
- Arms visible ratio: 1.0

## ESP32 / IMU

- Motion states: {'active': 100, 'burst': 172, 'small_motion': 4}
- Motion intensity p50/p90/max: 0.893/1.0/1.0
- Angular delta p50/p90/max: 105.351/387.362/1011.686 dps
- Sample rate p50: 14.925 Hz

## Garmin / Wearable

- Statuses: {'not_configured': 276}
- Heart-rate p50/p90/max: None/None/None bpm
- Exertion p50/p90/max: None/None/None
- Intensity zones: {'unknown': 276}
- Wrist motion states: {}
- Wrist motion delta p50/p90/max: None/None/None mg
- Wrist acceleration magnitude p50/p90/max: None/None/None mg

## Vision

- Statuses: {'calibrating': 117, 'ready': 159}
- Pose confidence p50/p90/max: 0.9/0.931/0.964

## Recommendations

- Garmin heart-rate samples are missing or sparse; start the BLE bridge or simulator before capture and pass --wearable-json.
- This capture is dominated by bursts; record one slower tilt sweep too for calibration and threshold comparison.
