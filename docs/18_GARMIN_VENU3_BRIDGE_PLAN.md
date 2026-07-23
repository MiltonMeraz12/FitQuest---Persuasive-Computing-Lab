# Garmin Venu 3 Bridge Plan

The Garmin Venu 3 should be treated as a wearable-context source, not as the main motion sensor. The ESP32/IMU remains the direct hand/object-motion sensor. The Garmin path should first provide physiological context, especially heart rate, and only later explore deeper sensor access if the project has time.

## Practical Goal

The useful bridge is still a JSON file that the current middleware already understands:

```json
{
  "status": "connected",
  "device": "garmin_venu_3",
  "provider": "garmin",
  "sample_type": "connect_iq_live",
  "heart_rate_bpm": 96,
  "acceleration": {"x": 12.0, "y": -30.0, "z": 1008.0},
  "acceleration_unit": "mg",
  "gyroscope": {"x": 0.3, "y": -1.2, "z": 2.4},
  "gyroscope_unit": "dps",
  "activity_state": "connect_iq_live_stream",
  "timestamp": "2026-07-08T12:00:00Z"
}
```

This payload shape is already compatible with the normal launcher. The runtime path is:

```powershell
.\runs\validate\wearable_live.json
```

The `run` command points to this path by default, even if the file does not exist yet. Until a bridge writes the first sample, the UI will report the wearable path as missing/stale instead of breaking the camera loop.

## Implemented Connect IQ Bridge

The normal one-command workflow starts one Connect IQ HTTP receiver. The BLE bridge is an explicit fallback:

```powershell
.\run_ironquest.bat
```

The receiver listens on the laptop at:

```text
http://<laptop-wifi-ip>:8765/garmin
```

The current safe watch app endpoint is configured in:

```text
monkey_c/ironquest_safe_telemetry/source/IronQuestSafeView.mc
```

The watch app posts heart rate, optional RR intervals, accelerometer, gyroscope, and location fields when the device exposes them. The local bridge writes normalized data to `runs/validate/wearable_live.json`, which the UI and JSONL capture already read.

The built sideload app is:

```text
monkey_c/ironquest_telemetry/build/IronQuestTelemetry.prg
```

The watch app uses the active HTTPS tunnel endpoint configured in that source file. If the tunnel endpoint changes, rebuild and sideload the `.prg` again.

## Implemented BLE Bridge

The BLE bridge remains available as an explicit heart-rate fallback:

```powershell
.\run_ironquest.bat
```

Use `--garmin-bridge` only when the Connect IQ app is not being used. Running both sources against the same wearable JSON can cause a missing-device fallback to hide a valid Connect IQ sample.

On the Garmin Venu 3, enable wrist heart-rate broadcasting first:

```text
Settings > Watch Sensors > Wrist Heart Rate > Broadcast Heart Rate
```

The runtime starts `tools/garmin_ble_heart_rate_bridge.py`, keeps scanning if the watch is not visible yet, and writes bridge output to:

```text
runs/validate/garmin_ble_bridge.log
```

Use `.\run_ironquest.bat --no-garmin-bridge` only when a demo should skip Bluetooth entirely.

If Connect IQ samples are fresh, the BLE fallback does not overwrite them. This preserves accelerometer, gyroscope, and location values from the watch app while still allowing BLE heart rate when the Connect IQ app is not running.

## What The Watch Can Contribute

| Signal | Practical value now | Likely access path |
| --- | --- | --- |
| Heart rate | High. Useful for exertion and intensity context. | Connect IQ app, BLE heart-rate bridge, Garmin SDK/API, or manual/export bridge. |
| Activity/session summary | Medium. Useful after a test session. | Garmin Health API or export workflow. |
| Stress, respiration, Body Battery, Pulse Ox | Medium/low for this prototype. Useful as context, not real-time controls. | Garmin Health API/SDK if access is available. |
| GPS/location | Low for gym glove tests. Useful only if outdoor movement becomes relevant. | Connect IQ app or Garmin activity export/API. |
| Accelerometer/gyroscope | Useful as an occasional double-check, while ESP32/IMU remains the primary motion sensor. | Connect IQ app. |

## What We Can Do With The Data

For the paper and demos, the Garmin data should be used to add physiology context to the existing movement signals:

- `heart_rate_bpm`: show exertion trend during controlled dumbbell movement.
- `exertion_level`: normalize heart rate into a 0.0-1.0 signal using resting/max HR when available.
- `intensity_zone`: classify session context as low, moderate, high, or peak.
- `rr_intervals_ms`: optional beat-to-beat context if the BLE packet exposes it.
- `activity_state`: label the capture scenario, for example `controlled_dumbbell_movement`.

The offline capture report now summarizes wearable status, HR percentiles, exertion percentiles, and intensity-zone counts.

## Recommended Order

1. Keep `.\run_ironquest.bat` as the only normal startup command.
2. Use the Connect IQ app for richer live watch data.
3. Keep the ESP32/IMU as the primary hand-motion source over UDP.
4. Keep BLE heart rate as a simple fallback when the Connect IQ app is not running.
5. Use Garmin Health API/SDK later for post-session health summaries if project approval/access is available.
6. Document latency and availability honestly in the paper.

## Runtime Direction

The user-facing workflow should stay simple: launch `.\run_ironquest.bat`, power the ESP32/IMU, and wear the Garmin. The Garmin bridge should only be responsible for updating `runs/validate/wearable_live.json`; the main runtime should not care whether that file came from BLE, a Garmin API, Connect IQ, or a controlled manual export.

## Source Notes

- Garmin Health API: https://developer.garmin.com/gc-developer-program/health-api/
- Garmin Health SDK: https://developer.garmin.com/health-sdk/
- Garmin Connect IQ: https://developer.garmin.com/connect-iq/
- Connect IQ Sensor API: https://developer.garmin.com/connect-iq/api-docs/Toybox/Sensor.html
- Venu 3 heart-rate broadcast manual: https://www8.garmin.com/manuals/webhelp/GUID-9CC4A873-E034-4A06-B2E0-636DCFE760EE/EN-US/GUID-E224D0CC-A96C-4F5A-B0EB-83691D7BF923.html
- Garmin Venu 3 product information: https://www.garmin.com/en-CA/p/873008
