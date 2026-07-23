# Sensors and Materials

This document records the active hardware decision after the June 23, 2026 pivot.

## Recommendation

Use **Garmin Venu 3** as the active wearable path for this sprint. Other research wearables are out of the active implementation scope unless the lab explicitly changes the hardware plan.

## Why Garmin Venu 3 Now?

Garmin Venu 3 is the better near-term fit because the project only needs wearable context, especially heart rate, while the core paper contribution is the sensor-fusion middleware. Garmin's public developer program documents health metrics such as heart rate, stress, respiration, Pulse Ox, Body Battery, and activity summaries through Health API workflows. Garmin also documents Venu 3 sensors including wrist heart rate, accelerometer, gyroscope, barometric altimeter, compass, and Bluetooth connectivity.

For this repo, the practical target is a bridge that writes heart-rate data as a neutral intensity/context signal:

```json
{
  "device": "garmin_venu_3",
  "provider": "garmin",
  "sample_type": "ble_heart_rate",
  "heart_rate_bpm": 92,
  "activity_state": "controlled_dumbbell_movement",
  "timestamp": "2026-06-23T12:00:00-03:00"
}
```

## Device Comparison

| Device | Useful data | Integration shape | Project decision |
| --- | --- | --- | --- |
| Garmin Venu 3 | Heart rate, activity/session summaries, stress-style metrics, motion sensors, Pulse Ox, Body Battery. | Garmin API/SDK or a simple bridge that emits JSON. | Chosen for current sprint. |

## ESP32 + IMU Prototype

The ESP32 path is active because it can provide direct object-motion data that the camera cannot infer reliably.

Recommended starting hardware:

| Item | Quantity | Purpose |
| --- | ---: | --- |
| ESP32-S3-DevKitC-1 | 1 | USB serial bridge and firmware target. |
| BNO085/BNO086 or GY-BNO08X IMU breakout | 1 | Acceleration, angular velocity, and orientation. |
| Breadboard or Qwiic/STEMMA QT cable | 1 | Safer and repeatable wiring. |
| Jumper wires | As needed | Basic prototyping. |
| Micro-USB data cable | 1 | Firmware upload and serial monitoring. |
| Temporary mounting material | As needed | Attach the prototype to the gym glove without conductive contact. |
| Portable case and battery hardware | Later | Needed only after Wi-Fi telemetry is stable. |

## ESP32 JSON Contract

Expected telemetry line over USB serial or Wi-Fi UDP:

```json
{
  "device_id": "esp32_0",
  "timestamp_ms": 123456,
  "mount": "right_gym_glove",
  "orientation_euler_deg": {
    "pitch": 4.1,
    "roll": -2.0,
    "yaw": 91.5
  },
  "accel_mps2": {
    "x": 0.0,
    "y": 0.0,
    "z": 9.81
  },
  "gyro_dps": {
    "x": 0.0,
    "y": 0.0,
    "z": 0.0
  }
}
```

The Python bridge now derives additional signal fields from consecutive samples:

- `sample_interval_ms`
- `sample_rate_hz`
- `motion_delta_mps2`
- `angular_delta_dps`
- `orientation_delta_deg`
- `motion_intensity`
- `rotation_intensity`
- `motion_state`
- `stability_index`

These fields compare IMU changes over time and can be fused with camera movement. They are useful for pilot logging now, but they should be validated after the IMU is mounted in the real gym glove.

## Wireless Transport Plan

The validated desk setup should remain available through USB serial. The Wi-Fi UDP path is now the active wireless prototype:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest check-esp32 --transport udp --udp-host 0.0.0.0 --udp-port 4210 --seconds 30
```

The matching firmware is:

```text
firmware/esp32_s3_bno08x_udp/esp32_s3_bno08x_udp.ino
```

Keep Wi-Fi credentials in:

```text
firmware/esp32_s3_bno08x_udp/wifi_config.h
```

Create that file from `wifi_config.example.h`; do not put local SSIDs or passwords directly in the sketch.

Do not design a permanent glove case until a serial capture and a UDP capture have been compared with `analyze-capture`.

## Heart-Rate Signal

The middleware maps Garmin heart rate to `exertion_level` and `intensity_zone`. These are input signals for analysis or future mapping, not hard-coded medical stop conditions.

## Source Notes

- Garmin Health API: https://developer.garmin.com/gc-developer-program/health-api/
- Garmin Venu 3 specs: https://www.garmin.com.my/products/wearables/venu-3-whitestone/
- Garmin Health SDK overview: https://developer.garmin.com/health-sdk/
