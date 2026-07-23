# ESP32-S3 + IMU Planning Notes

This document separates wiring, I2C scanning, and the real BNO08x IMU firmware. The Python side has a strict `ESP32Telemetry` payload model in `ironquest/sensors.py`, so the dashboard can consume the ESP32 stream without special-case hardware code.

## Goal

Use an ESP32-S3 DevKitC-1 as the IMU bridge for one sensor that will eventually be mounted on a gym glove. USB serial is the validated baseline. Wi-Fi UDP is the next prototype transport so the module can later run without a laptop cable. The current Python architecture already expects fields like:

```json
{"device_id":"esp32_0","timestamp_ms":12345,"mount":"right_gym_glove","accel_mps2":{"x":0,"y":0,"z":9.81},"gyro_dps":{"x":0,"y":0,"z":0}}
```

## No-Breadboard Wiring Plan

Use jumper wires directly from the IMU breakout pins to the ESP32-S3 DevKitC-1 header pins. This works only if both boards have soldered header pins or sockets. If either board has loose unsoldered holes, pause and get soldered headers, a breadboard, or JST/Qwiic/STEMMA QT cables before powering anything.

Power the ESP32 from USB, but wire the IMU while USB is disconnected.

| IMU breakout pin | ESP32-S3 DevKitC-1 pin | Purpose |
| --- | --- | --- |
| `VCC`, `VIN`, or `3V3` | `3V3` | Sensor power. Prefer 3.3 V unless the IMU board explicitly says it accepts 5 V logic. |
| `GND` | `G` / `GND` | Shared ground. |
| `SDA` | GPIO `8` | I2C data. |
| `SCL` | GPIO `9` | I2C clock. |
| `INT` | Leave disconnected for now | Optional interrupt pin. Add later only when the firmware needs it. |
| `AD0` / `SA0` | Leave default, or connect to `GND` | Optional address select on many MPU-style boards. Usually default address is `0x68`; tying high often changes it to `0x69`. |
| `CS` | Leave disconnected for the current BNO08x setup | The validated I2C scanner result did not need this pin. |

Why GPIO 8 and 9: ESP32-S3 I2C pins are configurable in software, and GPIO 8/9 are broken out on the DevKitC-1 headers. Espressif's DevKitC-1 documentation shows the board exposes most available GPIOs on the pin headers and lists GPIO8/GPIO9 on the header map.

References:

- Espressif ESP32-S3-DevKitC-1 user guide: <https://documentation.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/index.html>
- Adafruit MPU6050 Arduino guide, useful if the IMU is MPU6050-compatible: <https://learn.adafruit.com/mpu6050-6-dof-accelerometer-and-gyro/arduino>

## Validated BNO08x Bring-Up

The current prototype uses:

- ESP32-S3 DevKitC-1 over the `UART` USB port;
- CP2102N Windows driver;
- Arduino board `ESP32S3 Dev Module`;
- `USB CDC On Boot: Disabled`;
- `SDA = GPIO8`, `SCL = GPIO9`;
- detected BNO08x I2C address `0x4B`.

Use the scanner when rewiring or troubleshooting:

```text
firmware/esp32_s3_i2c_scanner/esp32_s3_i2c_scanner.ino
```

Expected scanner output:

```text
Scanning I2C bus...
Found I2C device at 0x4B
Done. Devices found: 1
```

Then flash the real IMU firmware:

```text
firmware/esp32_s3_bno08x_imu/esp32_s3_bno08x_imu.ino
```

Install `Adafruit BNO08x` from Arduino Library Manager and accept its dependencies. Expected serial lines look like:

```json
{"device_id":"esp32_0","timestamp_ms":12345,"mount":"right_gym_glove","orientation_euler_deg":{"pitch":1.2,"roll":-0.5,"yaw":30.1},"accel_mps2":{"x":0.1,"y":0.2,"z":9.7},"gyro_dps":{"x":0.0,"y":0.0,"z":0.3}}
```

Validate the stream from Python after closing Arduino Serial Monitor:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest check-esp32 --port auto --seconds 10 --list-ports
```

If auto-detection ever picks the wrong device, use the ESP32 port shown by Windows Device Manager, for example `--port COMx`.

## Next Wi-Fi UDP Prototype

The wireless prototype keeps the same JSON shape and sends it over Wi-Fi UDP:

```text
firmware/esp32_s3_bno08x_udp/esp32_s3_bno08x_udp.ino
```

Before flashing it, copy:

```text
firmware/esp32_s3_bno08x_udp/wifi_config.example.h
```

to:

```text
firmware/esp32_s3_bno08x_udp/wifi_config.h
```

Then set:

- `WIFI_SSID`
- `WIFI_PASSWORD`
- `TELEMETRY_USE_BROADCAST` should stay enabled so the laptop IP can change between networks

`wifi_config.h` is intentionally ignored because it contains local credentials.

Start the normal UI before moving the board:

```powershell
.\run_ironquest.bat
```

The serial firmware remains the fallback while the case, battery, and glove mount are still unresolved.

## Physical Stability Without a Breadboard

Direct jumper wiring is fine for a desk smoke test, but it is fragile for movement capture.

- Use short female-to-female Dupont wires if both boards have male headers.
- Keep the IMU flat and still during the first test; do not mount it inside the glove yet.
- Add tape or a small nonconductive clamp for strain relief after the first successful serial read.
- Avoid letting the underside of either board touch metal.
- Do not power the IMU from `5V` unless the breakout explicitly supports 5 V input and 3.3 V I2C logic.

The firmware should only stream sensor readings. Do not encode exercise rules, game controls, or camera assumptions on the ESP32. Keep fusion decisions in Python until the signal quality is understood.
