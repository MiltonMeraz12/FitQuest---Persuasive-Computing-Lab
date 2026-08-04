# ESP32/IMU Hardware

The ESP32-S3 + BNO08x IMU is the project's direct hand-motion sensor. It streams a fixed JSON shape that `ironquest/sensors.py` parses through a strict `ESP32Telemetry` model, so the dashboard consumes the stream with no special-case hardware code.

This document covers wiring, bring-up, the firmware, and the wireless transport.

## Validated Hardware

- ESP32-S3 DevKitC-1, connected through the `UART` USB port;
- BNO08x IMU breakout at I2C address `0x4B`;
- CP2102N Windows driver;
- Arduino board `ESP32S3 Dev Module`, `USB CDC On Boot: Disabled`;
- `SDA = GPIO8`, `SCL = GPIO9`.

## Wiring

Power the ESP32 from USB, but wire the IMU while USB is **disconnected**.

| IMU breakout pin | ESP32-S3 DevKitC-1 pin | Purpose |
| --- | --- | --- |
| `VCC`, `VIN`, or `3V3` | `3V3` | Sensor power. Prefer 3.3 V unless the IMU board explicitly accepts 5 V logic. |
| `GND` | `G` / `GND` | Shared ground. |
| `SDA` | GPIO `8` | I2C data. |
| `SCL` | GPIO `9` | I2C clock. |
| `INT` | Leave disconnected | Optional interrupt pin. Add only if the firmware needs it. |
| `AD0` / `SA0` | Leave default, or tie to `GND` | Optional address select on MPU-style boards. |
| `CS` | Leave disconnected | Not needed for the BNO08x I2C setup. |

ESP32-S3 I2C pins are configurable in software; GPIO 8/9 are chosen because the DevKitC-1 breaks them out on the header.

Direct jumper wiring is fine for a desk smoke test but fragile for movement capture:

- use short female-to-female Dupont wires if both boards have male headers;
- keep the IMU flat and still during the first test;
- add tape or a small nonconductive clamp for strain relief after the first successful read;
- do not let the underside of either board touch metal;
- do not power the IMU from `5V` unless the breakout explicitly supports 5 V input with 3.3 V I2C logic.

If either board has loose unsoldered holes, stop and get soldered headers or Qwiic/STEMMA QT cables before powering anything.

## Bring-Up

Use the I2C scanner when rewiring or troubleshooting:

```text
firmware/esp32_s3_i2c_scanner/esp32_s3_i2c_scanner.ino
```

Expected output:

```text
Scanning I2C bus...
Found I2C device at 0x4B
Done. Devices found: 1
```

## Firmware

There is one telemetry sketch:

```text
firmware/esp32_s3_bno08x_udp/esp32_s3_bno08x_udp.ino
```

It publishes each sample over **both** USB serial and Wi-Fi UDP, so it covers the cabled and portable setups with one build. Install `Adafruit BNO08x` from the Arduino Library Manager and accept its dependencies.

Before flashing:

1. Copy `firmware/esp32_s3_bno08x_udp/wifi_config.example.h` to `firmware/esp32_s3_bno08x_udp/wifi_config.h`.
2. Set `WIFI_SSID` and `WIFI_PASSWORD`.
3. Keep `TELEMETRY_USE_BROADCAST = 1` as a fallback; the runtime also supports automatic UDP discovery.
4. Keep `TELEMETRY_DESTINATION_PORT = 4210` unless you change the Python side too.

`wifi_config.h` is gitignored because it holds local credentials.

The sketch calls `WiFi.disconnect(true)` before each reconnect attempt, which avoids a known ESP32 Wi-Fi library flakiness pattern after a dropped connection.

Expected telemetry lines:

```json
{"device_id":"esp32_0","timestamp_ms":12345,"mount":"right_gym_glove","orientation_euler_deg":{"pitch":1.2,"roll":-0.5,"yaw":30.1},"accel_mps2":{"x":0.1,"y":0.2,"z":9.7},"gyro_dps":{"x":0.0,"y":0.0,"z":0.3}}
```

The firmware should only stream sensor readings. Do not encode exercise rules, game controls, or camera assumptions on the ESP32; fusion decisions stay in Python.

## Active Data Path

```text
BNO08x IMU -> ESP32-S3 -> JSON telemetry -> Python bridge -> game_control payload -> UI / JSONL / capture_analysis
```

The IMU fields the runtime uses:

- `orientation_euler_deg.pitch` / `.roll` / `.yaw`
- `accel_mps2`, `gyro_dps`
- `motion_delta_mps2`, `angular_delta_dps`, `orientation_delta_deg`
- `motion_intensity`, `rotation_intensity`, `motion_state`
- `stability_index`, `sample_rate_hz`

## Running It

Normal use is the launcher, which listens to USB serial and Wi-Fi UDP together:

```powershell
.\run_ironquest.bat
```

The Wi-Fi path includes automatic laptop discovery: Python broadcasts a discovery packet from port `4210` and the ESP32 listens on port `4211`, so the board can relearn the laptop address after a hotspot or network change. The packet must carry a shared token (`ironquest_discover:<token>`) matching `DISCOVERY_TOKEN` in `wifi_config.h`, so another device on the same hotspot cannot redirect the telemetry stream. Both sides fall back to the same placeholder token, so this works out of the box; set a private value in `wifi_config.h` and in the `IRONQUEST_ESP32_DISCOVERY_TOKEN` environment variable to actually lock it down.

For a valid Wi-Fi test the laptop and ESP32 must be on the same local network:

1. Connect the laptop to the phone hotspot.
2. Power the ESP32 from USB or a powerbank.
3. Make sure `wifi_config.h` uses that same hotspot SSID and password.
4. Open the UI and press `d` if the debug panel is hidden.
5. Read the IMU transport label:

| Label | Meaning |
| --- | --- |
| `USB` | Read through the laptop cable. Stable fallback. |
| `WIFI` | Read wirelessly. Validates the portable/powerbank path. |
| `USB+WIFI` | Both paths working. Ideal for transition testing. |
| `WAIT` | No ESP32 telemetry reaching the UI yet. |

Do not validate Wi-Fi with the laptop on `eduroam` and the ESP32 on the phone hotspot: those are different networks, so local UDP will not arrive. The firmware also does not target `eduroam` directly because that network uses enterprise authentication.

## Standalone Checks

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest check-esp32 --port auto --seconds 10 --list-ports
```

Close the Arduino Serial Monitor first; it holds the port. If auto-detection picks the wrong device, pass the port shown in Windows Device Manager, for example `--port COMx`.

For the Wi-Fi path:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest check-esp32 --transport udp --udp-host 0.0.0.0 --udp-port 4210 --seconds 30
```

For a saved research capture:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest capture-motion-data --mode full --label imu_udp_test_01 --source 0 --esp32-transport udp --esp32-udp-port 4210 --duration 30 --video --ui-detail debug
```

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest analyze-capture
```

## Debug Panel Signals

Debug mode exposes the processed IMU signals:

- IMU state: `steady`, `small_motion`, `active`, or `burst`.
- Motion intensity: normalized movement from acceleration, angular velocity, orientation deltas, and raw gyro magnitude.
- Rotation intensity: normalized angular movement.
- Stability: higher means physically steadier samples.
- Sample rate: around 15 Hz with the current firmware.

The OpenCV window is a monitor, not the final game interface.

## Physical Case

The printed case lives in [`hardware/esp32_case/`](../hardware/esp32_case/README.md). It is on its second revision.

The case exists to:

- prevent jumper wires from pulling out;
- avoid short circuits;
- keep the IMU orientation fixed relative to the hand;
- expose reset/boot access;
- separate battery/power hardware from sensor signal wires;
- allow the module to be removed for flashing or repair.

Mount rotation sets an absolute pitch offset on the forearm signal. The browser's per-rep validation therefore keys off the *excursion* of forearm elevation rather than its absolute band, so a constant mount offset cancels out.
