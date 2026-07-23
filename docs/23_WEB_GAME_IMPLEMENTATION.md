# FitQuest Web Game Implementation

The browser client is a lightweight vertical slice over the existing
sensor-fusion middleware. It does not run YOLO or read the ESP32 directly.
The Python runtime remains the owner of the camera and hardware connections,
then publishes the resulting `game_control` payload locally.

## Files

| File | Purpose |
| --- | --- |
| `web/fitquest_game.html` | Live browser UI, program-prescribed exercise sequence, difficulty controls, 3D movement model, and feedback. |
| `web/vendor/three.min.js` | Vendored Three.js r149 (last classic global-script UMD build). Fetched once and committed so the 3D avatar keeps working without internet in the lab; served by `web_gateway.py`'s `/vendor/` route. |
| `web/demo_game_control.jsonl` | Legacy regression fixture retained outside the production route. |
| `ironquest/web_gateway.py` | Standard-library HTTP server, Server-Sent Events stream, health endpoint and annotated MJPEG preview. |
| `tools/simulate_game_control_stream.py` | Offline dev/demo tool. Drives the real `MotionAnalyzer`/`build_body_context`/`build_game_control_payload` with a scripted synthetic pose sequence and publishes it through `WebGateway`, so the browser client can be exercised end to end (calibration, all six exercises, rep counting, sensor cards, set completion, results screen) with no camera, ESP32, or Garmin watch attached. |
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

## Exercise controller: program-prescribed, not auto-detected

Earlier versions mapped the Python sensor-fusion layer's `exercise_candidate`
(derived from the calibrated movement signature) directly into the browser's
active exercise. In practice this single-frame heuristic flickered on real
pose noise -- a live test session spent most of its time on "detecting
movement" despite good tracking, because small joint-angle jitter flips
between token sets frame to frame. The browser now prescribes the sequence
itself instead of guessing it: `curl -> front_raise -> press -> front_hold ->
double_press -> combo`, announced one at a time (name, subtitle, ~3.2s "get
ready" card) before each set starts, the same way a coach would call out the
next movement. `exercise_candidate` still exists in the server payload/schema
unchanged -- it remains useful as a research signal (e.g. comparing the
camera-inferred signature against the prescribed ground truth) -- it is just
no longer consumed to select the active exercise.

Per exercise:

- alternating curl counts `extended -> bent -> extended` on the arm-extension
  signal;
- single-arm press, alternating front raise, and double-arm press count the
  equivalent height-signal threshold crossing;
- bilateral front hold counts a sustained hold once both arms clear the
  height threshold together;
- the combo movement (overhead press + opposite front hold) reads
  `left_overhead_right_front_candidate` / `right_overhead_left_front_candidate`
  from the live token list to render whichever physical side is actually
  overhead, since that can vary session to session or mid-set.

A repetition is gated by pose confidence, fused hand-motion stability, and
dumbbell association. On the glove-mounted side, a rep additionally requires
real IMU motion to have been observed during the bent/down phase before it
completes -- a soft gate that only applies when the hand sensor is live, so
camera-only counting keeps working when the glove is unavailable. Heart rate
is displayed as context and does not enter the form score or act as a medical
stop condition. Body position is inferred from the camera; if the lower body
is outside the frame, the system assumes a seated posture.

Difficulty is changed from the main page, outside the setup modal. The available
levels are `BEGINNER` (8 reps / 60 seconds), `ADVANCED` (12 / 50), `EXPERT`
(16 / 45), and `FIT` (20 / 40). Changing the level during a session resets the
current set with the new target and stricter form thresholds.

## Sensor fusion beyond status display

Camera and glove signals are blended rather than one overriding the other:
fused stability is 60% hand-sensor / 40% camera-derived when the glove is
live, shown alongside a dedicated "HAND STABILITY" tile for the raw glove
value. Session Signals also tracks how many reps were IMU-confirmed
(`imuConfirmedReps` vs `totalReps`), surfaced live and again on the results
screen ("N of M reps confirmed by the hand motion sensor") as concrete
evidence the camera, glove, and watch are working together rather than each
just displaying its own status independently.

## Movement stage: 3D avatar

The movement stage renders a low-poly, flat-shaded 3D humanoid (capsule/
cylinder limbs, sphere head, soft key + rim lighting, subtle idle sway) with
Three.js, vendored locally at `web/vendor/three.min.js` rather than loaded
from a CDN, so it keeps working without internet in the lab. Bone angles use
`pointFor3D()`, which reprojects the exact same extension/height -> angle
formulas already validated for the project's earlier 2D model into 3D
coordinates -- the geometry logic did not change, only its output space. A
`requestAnimationFrame` loop continuously eases the drawn pose toward the
latest signal (`AVATAR_LERP_RATE`) instead of snapping on every Server-Sent
Event, so the figure reads as fluid movement regardless of how evenly the
backend publishes frames. An earlier 2D SVG model (and a still-earlier
unreachable dead-code Three.js prototype before it) were both fully removed
rather than kept as a fallback.

When a session ends, either by reaching the difficulty's time budget or by
pressing Stop with at least a few seconds of activity, a results screen shows
total reps, sets, active time, and average form quality before returning to
setup, so a session has a real beginning-to-end arc instead of resetting
silently.

The browser preview intentionally excludes the developer HUD. The standalone
OpenCV monitor still keeps that technical interface for diagnostics when it is
run separately with its display enabled.

Sensor cards use signal freshness rather than connection metadata alone. A hand
motion signal is held for up to 3.2 seconds and wearable context for up to 6.5
seconds after the last sample before falling back. Within that window, `LIVE`
persists for roughly 1.6x the sensor's own reported `sample_interval_ms` (with
a small minimum), not just the single tick a new sample arrives -- sizing the
LIVE window off each device's real cadence instead of a fixed instant. A
device posting every ~3 seconds (the Garmin Connect IQ app) would otherwise
spend most of its time misreported as `DELAY` even while working normally.
Beyond the full cooldown the card clears to `STALE`, distinguishing a real
disconnection from a normal reporting gap without changing the movement
signals used by the game.

The hardware bridges are also late-start tolerant. The serial transport keeps
scanning for a device when the program starts without one, the UDP listener
reopens after a transient bind failure, and the wearable file bridge keeps
polling for a file that is created or updated later. The optional background
wearable pullers remain alive and retry their source independently, so starting
the hardware after the camera pipeline does not require restarting the game.

When a target is completed, the live stream stays open. A short transition card
announces the next prescribed movement and resets the set, chosen by the
browser's fixed exercise sequence rather than a fresh guess from Python.

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

To manually check the browser client itself (layout, avatar motion, rep
counting, sensor cards, difficulty switching, the results screen) without a
camera or hardware attached, run the offline simulator and open the printed
URL:

```powershell
.\ironquest_env\Scripts\python.exe -m tools.simulate_game_control_stream
```

The broader test suite still depends on the local PyTorch/Ultralytics runtime.
On the current Windows environment, that dependency is blocked by an
Application Control policy while loading `torch\\lib\\shm.dll`; this is an
environment limitation rather than a failure in the web gateway tests.
