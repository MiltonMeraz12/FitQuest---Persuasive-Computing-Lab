# Garmin Venu 3 Bridge

The Garmin Venu 3 is a wearable-context source, not the main motion sensor. The ESP32/IMU remains the direct hand/object-motion sensor. The watch provides physiological context, especially heart rate, plus a secondary wrist-motion cross-check.

## Payload Contract

The bridge writes a JSON file that the middleware already understands:

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

The runtime path is:

```text
.\runs\validate\wearable_live.json
```

The `run` command points there by default even when the file does not exist yet. Until a bridge writes the first sample, the UI reports the wearable path as missing/stale instead of breaking the camera loop.

The main runtime does not care whether that file came from Connect IQ, BLE, or a Garmin API export. Any bridge that keeps it fresh is enough.

## The Watch App

There is one Connect IQ app:

```text
monkey_c/fitquest_telemetry/
```

It starts its Timer from the View's `onShow()` (the correct lifecycle hook) and posts to the permanent Cloudflare Worker endpoint, so it does not need rebuilding every time a tunnel restarts. It sends heart rate, optional RR intervals, accelerometer, gyroscope, and location fields when the device exposes them.

Build it with the Connect IQ SDK:

```powershell
monkeyc -f monkey_c\fitquest_telemetry\monkey.jungle -o monkey_c\fitquest_telemetry\build\FitQuestTelemetry.prg -y monkey_c\developer_key -d venu3
```

The developer key is intentionally not in git. Generate one with `openssl` or the Connect IQ SDK if you do not have `monkey_c/developer_key`.

### Connect IQ receiver

The normal one-command workflow starts the Connect IQ HTTP receiver:

```powershell
.\run_ironquest.bat
```

The receiver listens on the laptop at:

```text
http://<laptop-wifi-ip>:8765/garmin
```

### Cloudflare Worker

`cloudflare/fitquest-garmin/worker.js` relays samples when the watch cannot reach the laptop directly — a phone hotspot will not route back into a hotspot client, and Connect IQ requires HTTPS. It allowlists the same fields as the local Python bridge instead of storing whatever the client sends, and clamps `heart_rate_bpm` to a plausible 20-240 range.

Deploy it with `cloudflare/fitquest-garmin/wrangler.toml`:

```powershell
cd cloudflare\fitquest-garmin
npx wrangler d1 create fitquest-garmin
npx wrangler deploy
```

Fill in `database_id` in `wrangler.toml` from `npx wrangler d1 list` before the first deploy. The Worker creates its own table on first request, so there is no migration step.

It also supports an opt-in shared secret: if the `FITQUEST_SHARED_TOKEN` Worker secret is set (`wrangler secret put FITQUEST_SHARED_TOKEN`), `POST /garmin` requires a matching `X-FitQuest-Token` header. Leaving the secret unset keeps the endpoint open, so this is safe to leave unconfigured. To enable it, add the same header to the `:headers` options in `FitQuestTelemetryView.mc`, rebuild, and re-sideload.

## BLE Fallback

The BLE bridge is an explicit heart-rate-only fallback. Use `--garmin-bridge` **only** when the Connect IQ app is not running: two writers against the same wearable JSON let a missing-device fallback overwrite a valid Connect IQ sample.

On the watch, enable wrist heart-rate broadcasting first:

```text
Settings > Watch Sensors > Wrist Heart Rate > Broadcast Heart Rate
```

The runtime starts `tools/garmin_ble_heart_rate_bridge.py`, keeps scanning if the watch is not visible yet, and logs to:

```text
runs/validate/garmin_ble_bridge.log
```

Use `.\run_ironquest.bat --no-garmin-bridge` when a demo should skip Bluetooth entirely.

When Connect IQ samples are fresh, the BLE fallback does not overwrite them. That preserves accelerometer, gyroscope, and location values from the watch app while still allowing BLE heart rate when the Connect IQ app is not running.

## Sideloading Over USB

1. Connect the Garmin Venu 3 to the laptop with USB.
2. Open the Garmin storage.
3. Copy `FitQuestTelemetry.prg` into `GARMIN\APPS`.
4. Disconnect/eject the watch and wait for it to finish indexing.
5. On the watch, open the apps list and launch `FitQuest Telemetry`.

The `.iq` files the SDK also produces are for the Connect IQ Store beta/private upload path, not for direct USB copy.

## Reading The Watch Screen

| Screen state | Meaning |
| --- | --- |
| `Sent` increasing, `Last: 200` | Telemetry is reaching the laptop. |
| `No response` | The watch/phone cannot reach the endpoint URL. |
| `Sent 0`, `HTTP -300` | The endpoint is unreachable from the watch. |
| `HTTP -1001` | Garmin is requiring HTTPS. Use the Worker endpoint, not a plain-HTTP laptop IP. |
| `IQ!` icon or immediate exit | The app crashed. See below. |

## Troubleshooting

### The laptop bridge looks dead

The bridge is healthy when `http://<laptop-wifi-ip>:8765/garmin` returns JSON. Test it **from the phone browser**, not only from the laptop: the watch may use the phone as its network bridge, so phone access is the test that matters.

### The phone is the hotspot

If the laptop is connected to the phone's hotspot, the watch request can fail even when the laptop browser works, because the phone is both hotspot gateway and Garmin Connect bridge and may not route back into a hotspot client. Use the Cloudflare Worker endpoint instead of the laptop IP; it is permanent and HTTPS, which also satisfies the `HTTP -1001` case above.

### The watch shows `IQ!`

1. Reconnect the watch by USB.
2. Copy `GARMIN\APPS\LOGS\CIQ_LOG.YML` or `CIQ_LOG.TXT` if either exists.
3. Read the reported file/line; it names the failing call directly.

The one crash observed on this project, on Venu 3 firmware 17.05 / Connect IQ 6.0.2:

```text
Error: Invalid Value
Appname: IronQuest Safe
File: IronQuestSafeApp.mc
Line: 37
Function: onStart
```

The failing line started a `Timer` from the app's `onStart`. The current app starts its timer from the view lifecycle (`onShow()`) instead, matching Garmin's documented Timer usage. If a future change moves timer setup back into `onStart`, expect this crash to return.

If a build crashes after adding sensors, GPS and continuous sensor listeners are the usual causes. Add richer sensors one at a time and re-test.

### The app does not appear on the watch

Check these before changing code:

- The file is in `GARMIN\APPS`, not Downloads or another folder.
- The copied file extension is `.prg`.
- The watch was disconnected/ejected after copying.
- The app is opened from the watch apps list, not from the Connect IQ phone app.
- Reconnect USB and confirm the `.prg` is still there. If it disappeared, the watch rejected it.

If USB sideloading keeps failing, use the generated `.iq` package with the Connect IQ developer portal beta/private workflow.

## What The Watch Can Contribute

| Signal | Practical value now | Likely access path |
| --- | --- | --- |
| Heart rate | High. Useful for exertion and intensity context. | Connect IQ app, BLE heart-rate bridge, Garmin SDK/API, or manual/export bridge. |
| Activity/session summary | Medium. Useful after a test session. | Garmin Health API or export workflow. |
| Stress, respiration, Body Battery, Pulse Ox | Medium/low for this prototype. Useful as context, not real-time controls. | Garmin Health API/SDK if access is available. |
| GPS/location | Low for gym glove tests. Useful only if outdoor movement becomes relevant. | Connect IQ app or Garmin activity export/API. |
| Accelerometer/gyroscope | Useful as an occasional double-check, while ESP32/IMU remains the primary motion sensor. | Connect IQ app. |

## What We Do With The Data

Garmin data adds physiology context to the existing movement signals:

- `heart_rate_bpm`: exertion trend during controlled dumbbell movement.
- `exertion_level`: heart rate normalized into a 0.0-1.0 signal using resting/max HR when available.
- `intensity_zone`: session context classified as low, moderate, high, or peak.
- `rr_intervals_ms`: optional beat-to-beat context if the packet exposes it.
- `activity_state`: label for the capture scenario, for example `controlled_dumbbell_movement`.

The offline capture report summarizes wearable status, HR percentiles, exertion percentiles, and intensity-zone counts.

## Recommended Order

1. Keep `.\run_ironquest.bat` as the only normal startup command.
2. Use the Connect IQ app for richer live watch data.
3. Keep the ESP32/IMU as the primary hand-motion source over UDP.
4. Keep BLE heart rate as a fallback when the Connect IQ app is not running.
5. Use the Garmin Health API/SDK later for post-session health summaries if approval/access is available.
6. Document latency and availability honestly in the paper.

## Source Notes

- Garmin Health API: https://developer.garmin.com/gc-developer-program/health-api/
- Garmin Health SDK: https://developer.garmin.com/health-sdk/
- Garmin Connect IQ: https://developer.garmin.com/connect-iq/
- Connect IQ Sensor API: https://developer.garmin.com/connect-iq/api-docs/Toybox/Sensor.html
- Venu 3 heart-rate broadcast manual: https://www8.garmin.com/manuals/webhelp/GUID-9CC4A873-E034-4A06-B2E0-636DCFE760EE/EN-US/GUID-E224D0CC-A96C-4F5A-B0EB-83691D7BF923.html
- Garmin Venu 3 product information: https://www.garmin.com/en-CA/p/873008
