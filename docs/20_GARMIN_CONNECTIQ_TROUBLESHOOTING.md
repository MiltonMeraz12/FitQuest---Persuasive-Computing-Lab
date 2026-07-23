# Garmin Connect IQ Troubleshooting

Use this when the Garmin Venu 3 app does not appear on the watch or the UI does not update.

## Current Known Good Laptop State

The laptop bridge is healthy when this URL returns JSON:

```text
http://172.22.236.167:8765/garmin
```

Test it from the phone browser, not only from the laptop. The watch may use the phone as the network bridge, so phone access is the important test.

## If The Phone Is The Hotspot

If the laptop is connected to the phone hotspot, the watch request may fail even when the laptop browser works. In that setup the phone is both the hotspot gateway and the Garmin Connect bridge, and it may not route back into a hotspot client.

Use an HTTPS tunnel instead. The current temporary test tunnel is:

```text
https://edition-consultation-variables-viewers.trycloudflare.com/garmin
```

This URL was tested with GET and POST and correctly updated `runs/validate/wearable_live.json`.

The tunnel must remain running while testing. If it is restarted, Cloudflare may give a new URL; update `IRONQUEST_ENDPOINT` in `monkey_c/ironquest_telemetry/source/IronQuestTelemetryApp.mc` and rebuild the watch app.

## Files To Try

First verify sideloading with the minimal app:

```text
monkey_c/ironquest_smoke/build/IronQuestCheck.prg
```

Then try the telemetry app:

```text
monkey_c/ironquest_telemetry/build/IronQuestTelemetry.prg
```

The current telemetry build points to the HTTPS tunnel above, not the phone hotspot IP.

If `IronQuest Telemetry` shows `IQ!`, try the safer diagnostic build:

```text
monkey_c/ironquest_safe_telemetry/build/IronQuestSafe.prg
```

This build uses a new app ID, avoids GPS, avoids continuous sensor listeners, and only sends a small HTTPS payload. It is the preferred next test after an `IQ!` crash.

The `.iq` files are for a Connect IQ Store beta/private upload path, not for direct USB copy.

## USB Sideload Steps

1. Connect the Garmin Venu 3 to the laptop with USB.
2. Open the Garmin storage.
3. Delete any old `IronQuestTelemetry.prg` from `GARMIN\APPS`.
4. Copy `IronQuestCheck.prg` to `GARMIN\APPS`.
5. Disconnect/eject the watch and wait for it to finish indexing.
6. On the watch, open the apps list and look for `IronQuest Check`.
7. If it appears and shows `CHECK OK`, sideloading works.
8. Reconnect USB, copy `IronQuestTelemetry.prg` to `GARMIN\APPS`, disconnect, and open `IronQuest Telemetry`.

## What The Watch Screen Means

- `Sent` increasing plus `Last: 200`: telemetry is reaching the laptop.
- `No response`: the watch/phone cannot reach the laptop URL.
- `Sent 0` plus `HTTP -300`: the current endpoint is not reachable from the watch, usually because the temporary tunnel stopped or the app still points to an old tunnel URL.
- `HTTP -1001`: Garmin is likely requiring HTTPS, so use the `.iq` beta path or an HTTPS tunnel.
- An `IQ!` icon or immediate app exit: connect USB and check `GARMIN\APPS\LOGS\CIQ_LOG.YML` or `CIQ_LOG.TXT`.

## When The Watch Shows IQ!

1. Reconnect the watch by USB.
2. Copy `GARMIN\APPS\LOGS\CIQ_LOG.YML` or `GARMIN\APPS\LOGS\CIQ_LOG.TXT` if either file exists.
3. If the log mentions `IronQuestTelemetry`, delete the old telemetry `.prg` from `GARMIN\APPS`.
4. Copy `monkey_c/ironquest_safe_telemetry/build/IronQuestSafe.prg` to `GARMIN\APPS`.
5. Disconnect/eject the watch and launch `IronQuest Safe`.

If `IronQuest Safe` works, the previous crash was likely caused by GPS or continuous sensor streaming. Keep the safe build for live testing, then add richer sensors one at a time.

Observed crash on Venu 3 firmware 17.05 / Connect IQ 6.0.2:

```text
Error: Invalid Value
Appname: IronQuest Safe
File: IronQuestSafeApp.mc
Line: 37
Function: onStart
```

The failing line started a `Timer` from the app `onStart`. The safer build now starts the timer from the view lifecycle instead, matching Garmin's documented Timer usage pattern more closely.

## If The App Does Not Appear

Check these before changing code:

- The file is in `GARMIN\APPS`, not Downloads or another folder.
- The copied file extension is `.prg`.
- The watch was disconnected/ejected after copying.
- The app is opened from the watch apps list, not from the Connect IQ phone app.
- Reconnect USB and see whether the `.prg` file is still there. If it disappeared, the watch rejected it.

If USB sideloading keeps failing, use the generated `.iq` package with the Connect IQ developer portal beta/private workflow:

```text
monkey_c/ironquest_telemetry/build/IronQuestTelemetry.iq
```
