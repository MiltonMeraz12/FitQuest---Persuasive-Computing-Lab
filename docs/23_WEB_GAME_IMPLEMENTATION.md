# FitQuest Web Game Implementation

The browser client is a lightweight vertical slice over the existing
sensor-fusion middleware. It does not run YOLO or read the ESP32 directly.
The Python runtime remains the owner of the camera and hardware connections,
then publishes the resulting `game_control` payload locally.

## Files

| File | Purpose |
| --- | --- |
| `web/fitquest_game.html` | Live browser UI, automatic exercise selection, difficulty controls, lightweight 2D movement model, and feedback. |
| `web/demo_game_control.jsonl` | Legacy regression fixture retained outside the production route. |
| `ironquest/web_gateway.py` | Standard-library HTTP server, Server-Sent Events stream, health endpoint and annotated MJPEG preview. |
| `tests/test_web_gateway.py` | Gateway and stream smoke tests. |

## Run the live application

The normal detector owns the camera, YOLO pose, dumbbell model, ESP32 bridge,
and wearable file bridge. The launcher enables the web gateway and opens the
browser client automatically:

```powershell
.\run_ironquest.bat
```

The browser receives:

- `GET /events`: one Server-Sent Event per latest sensor-fusion frame;
- `GET /preview.mjpg`: the camera image with body and accepted-weight detections only;
- `GET /api/health`: gateway status and endpoint information;
- `GET /api/latest`: latest published frame when available.

## Current exercise controller

The Python sensor-fusion layer publishes an `exercise_candidate` from the
calibrated movement signature. The browser only maps that identifier to the
matching instruction, avatar motion, and repetition rule:

- alternating curl when a loaded dumbbell is detected;
- single-arm press or double-arm press when one or both arms reach overhead;
- alternating front raise when an extended arm reaches shoulder height;
- bilateral front hold when both extended arms reach shoulder height;
- front hold plus opposite curl when the cross-body combination token is detected.

For curls, a repetition moves through `extended -> bent -> extended`. For a
press, the equivalent threshold is based on calibrated height. A repetition is
gated by pose confidence, hand-motion stability, and dumbbell association. Heart
rate is displayed as context and does not enter the form score or act as a
medical stop condition. Body position is inferred from the camera; if the lower
body is outside the frame, the system assumes a seated posture.

Difficulty is changed from the main page, outside the setup modal. The available
levels are `BEGINNER` (8 reps / 60 seconds), `ADVANCED` (12 / 50), `EXPERT`
(16 / 45), and `FIT` (20 / 40). Changing the level during a session resets the
current set with the new target and stricter form thresholds.

The movement stage uses a lightweight adult-neutral 2D vector model with clothing,
jointed arms, dumbbells, subtle facial details, and a floor target. It receives
the same live normalized arm signals as the repetition controller, so the visual
movement and the counted movement use one source of truth without adding a 3D
rendering dependency or a continuous graphics workload.

The browser preview intentionally excludes the developer HUD. The standalone
OpenCV monitor still keeps that technical interface for diagnostics when it is
run separately with its display enabled.

Sensor cards use signal freshness rather than connection metadata alone. A hand
motion signal is held for 3.2 seconds and wearable context for 6.5 seconds. The
card shows `DELAY` during that short cooldown, then clears the old values and
shows `STALE` when no new sample arrives. This makes a real disconnection
distinguishable from a brief transport delay without changing the movement
signals used by the game.

The hardware bridges are also late-start tolerant. The serial transport keeps
scanning for a device when the program starts without one, the UDP listener
reopens after a transient bind failure, and the wearable file bridge keeps
polling for a file that is created or updated later. The optional background
wearable pullers remain alive and retry their source independently, so starting
the hardware after the camera pipeline does not require restarting the game.

When a target is completed, the live stream stays open. A short transition card
resets the set and waits for the next movement candidate from Python instead of
choosing the next exercise inside the browser.

## Sensor failure behavior

The client continues to render when one sensor is missing. It marks the
individual source as `WAIT`, `STALE` or `N/A`, lowers confidence-dependent
feedback, and avoids counting a side whose dumbbell is explicitly reported as
not loaded. This is intentional: a missing wearable should not crash camera
tracking, and a missing camera frame should not be presented as a valid rep.

## Verification

Run the web gateway smoke tests with the project environment:

```powershell
.\ironquest_env\Scripts\python.exe -m pytest tests\test_web_gateway.py -q
```

The broader test suite still depends on the local PyTorch/Ultralytics runtime.
On the current Windows environment, that dependency is blocked by an
Application Control policy while loading `torch\\lib\\shm.dll`; this is an
environment limitation rather than a failure in the web gateway tests.
