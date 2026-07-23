# Run and Demo Guide

Use this guide for normal supervisor demos.

## One Command

```powershell
.\run_ironquest.bat
```

This starts the live project stack:

- camera feed;
- YOLO body-pose model;
- dumbbell/weight detector;
- OpenCV monitoring UI;
- ESP32+IMU USB/Wi-Fi auto listener;
- Garmin Venu 3 BLE heart-rate bridge plus wearable JSON polling.

Before starting the demo, enable this on the watch:

```text
Settings > Watch Sensors > Wrist Heart Rate > Broadcast Heart Rate
```

Close the UI with `q`. Press `d` only if you want to toggle the telemetry panel.

## What To Expect

- If the ESP32+IMU is connected by USB or sending Wi-Fi telemetry, the ESP32 indicator should become online and the debug panel should show IMU values.
- In the IMU debug panel, `USB`, `WIFI`, `USB+WIFI`, or `WAIT` shows which ESP32 transport is actually receiving data.
- If the ESP32 is not available, the UI should still run with camera tracking.
- If the Garmin broadcast is visible to the laptop, the wearable indicator should become online and the payload should include heart rate, exertion level, and intensity zone.
- If the Garmin is not visible yet, the UI still runs and the bridge keeps retrying in the background.

## Demo Explanation

Use this short explanation for the monitoring UI:

> The live monitor combines camera pose tracking, dumbbell/object detection, and external sensor telemetry. It provides the reliable sensor-fusion signals that the small web-based game will consume for a concrete sensor-to-action demonstration.

The web game should be demonstrated separately as a lightweight browser client. It only needs a few reliable mappings from `game_control` to visible actions or feedback; it does not need a complex game world.

## Advanced Reference

Only use [Command Reference](07_COMMAND_REFERENCE.md) for debugging, data capture, or maintenance.
