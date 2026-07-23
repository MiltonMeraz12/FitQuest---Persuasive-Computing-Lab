# ESP32/IMU Wireless Next Step

The current USB serial prototype is successful: the ESP32-S3, BNO08X IMU, Python bridge, OpenCV UI, JSONL capture, and offline capture analysis all work together.

## Current Physical Constraint

The current hardware is still a desk prototype:

- ESP32-S3 is on a breadboard with a power supply module.
- The ESP32 is still connected to the laptop by USB.
- The IMU uses short female-to-male jumpers, so movement tests are physically constrained.
- No gym glove, wearable mount, battery, or protective case is available yet.

This means the next software step should not assume comfortable full-body movement. The right next step is to make the transport wireless while preserving the same JSON payload and analysis pipeline.

## Active Data Path

```text
BNO08X IMU -> ESP32-S3 -> JSON telemetry -> Python bridge -> sensor_fusion_engine -> UI / JSONL / capture_analysis
```

The useful IMU fields now are:

- `orientation_euler_deg.pitch`
- `orientation_euler_deg.roll`
- `orientation_euler_deg.yaw`
- `accel_mps2`
- `gyro_dps`
- `motion_delta_mps2`
- `angular_delta_dps`
- `orientation_delta_deg`
- `motion_intensity`
- `rotation_intensity`
- `motion_state`
- `stability_index`
- `sample_rate_hz`

## Wireless Prototype

For normal use, the ESP32/IMU path is started through the main launcher:

```powershell
.\run_ironquest.bat
```

That command opens the camera UI and listens to USB serial and Wi-Fi UDP together. If USB is available, it can read serial data. If the ESP32 is powered by a powerbank, it can read Wi-Fi telemetry on port `4210`.

The Wi-Fi path now includes automatic laptop discovery: Python broadcasts a small discovery packet from port `4210`, and the ESP32 listens on port `4211` so it can learn the laptop address after hotspot or network changes.

The project still supports serial and UDP checks for debugging, but those are not the daily workflow.

## Daily Wi-Fi Test

Use only the normal launcher:

```powershell
.\run_ironquest.bat
```

For a valid Wi-Fi test, the laptop and ESP32 must be on the same local network. The most reliable setup is:

1. Connect the laptop to the phone hotspot.
2. Power the ESP32 from USB or a powerbank.
3. Make sure `wifi_config.h` uses that same hotspot SSID and password.
4. Open the UI and press `d` if the debug panel is hidden.
5. Read the IMU transport label:

| Label | Meaning |
| --- | --- |
| `USB` | The IMU is being read through the laptop cable. This is the stable fallback. |
| `WIFI` | The IMU is being read wirelessly. This validates the portable/powerbank path. |
| `USB+WIFI` | Both paths are working. This is ideal for transition testing. |
| `WAIT` | No ESP32 telemetry is reaching the UI yet. |

Do not validate Wi-Fi with the laptop on `eduroam` and the ESP32 on the phone hotspot. Those are different networks, so local UDP telemetry is not expected to reach the laptop. The ESP32 firmware also does not target `eduroam` directly because that network uses enterprise authentication.

For research capture sessions, use the capture command only when a saved dataset is needed:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest capture-motion-data --mode full --label imu_udp_test_01 --source 0 --esp32-transport udp --esp32-udp-port 4210 --duration 30 --video --ui-detail debug
```

Analyze after capture:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest analyze-capture
```

## Firmware Path

The known-good serial firmware remains:

```text
firmware/esp32_s3_bno08x_imu/esp32_s3_bno08x_imu.ino
```

The new Wi-Fi UDP prototype is:

```text
firmware/esp32_s3_bno08x_udp/esp32_s3_bno08x_udp.ino
```

Before flashing the UDP sketch:

1. Copy `firmware/esp32_s3_bno08x_udp/wifi_config.example.h` to `firmware/esp32_s3_bno08x_udp/wifi_config.h`.
2. Set `WIFI_SSID`.
3. Set `WIFI_PASSWORD`.
4. Keep `TELEMETRY_USE_BROADCAST = 1` as a fallback; the runtime also supports automatic UDP discovery from the laptop.
5. Keep `TELEMETRY_DESTINATION_PORT = 4210` unless you change the Python command.

The UDP sketch still prints serial logs, but the Python runtime receives telemetry over Wi-Fi.

## UI Improvements

Debug mode now exposes processed IMU signals:

- IMU state: `steady`, `small_motion`, `active`, or `burst`.
- Motion intensity: normalized movement signal from acceleration, angular velocity, and orientation deltas.
- Rotation intensity: normalized angular movement signal.
- Stability: high values mean physically steadier samples.
- Sample rate: expected around 15 Hz with the current firmware.

The UI should be used as a monitor, not as the final game interface.

## Next Hardware Milestones

1. Keep desk testing with USB serial as the fallback baseline.
2. Flash and validate Wi-Fi UDP while still powered by USB.
3. Compare one serial capture and one UDP capture using `analyze-capture`.
4. Only after UDP is stable, design the portable case and power path.
5. For the glove/case version, prioritize strain relief, short protected IMU wiring, and removable access to the ESP32 USB port.

## Case Design Notes

The portable case should solve these problems:

- prevent jumper wires from pulling out;
- avoid short circuits on the breadboard/module;
- keep the IMU orientation fixed relative to the hand;
- expose reset/boot access if needed;
- separate battery/power hardware from sensor signal wires;
- allow the module to be removed for flashing or repair.

Do not permanently mount the current breadboard on a glove until the wireless path and power plan are tested.
