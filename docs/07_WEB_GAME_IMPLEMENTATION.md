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
| `ironquest/web_gateway.py` | Standard-library HTTP server, Server-Sent Events stream, health endpoint and annotated MJPEG preview. |
| `tools/simulate_game_control_stream.py` | Offline dev/demo tool. Drives the real `MotionAnalyzer`/`build_body_context`/`build_game_control_payload` with a scripted synthetic pose sequence and publishes it through `WebGateway`, so the browser client can be exercised end to end (calibration, all ten exercises, the posture-precondition hard gates, the glove grip gate, rep counting, sensor cards, set completion, results screen, and the avatar's bent-over-row torso hinge) with no camera, ESP32, or Garmin watch attached. Its own `EXERCISE_SCRIPT` cycle runs independently of whatever exercise the browser is currently coaching (the browser prescribes its own sequence -- see below), so the label on screen and the motion actually being simulated can be out of sync; that's expected for this tool and not a bug. |
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

## Hardware-live start gate

A session (the very first start, or any later restart -- same user or a
different one) cannot begin until both the ESP32 hand sensor and the
smartwatch are actively reporting `LIVE` data, re-checked fresh every time
the Start button is pressed. There is deliberately no override or "continue
without hardware" option. The gate is implemented client-side: the SSE
control stream connects once at page load (not only when a session starts)
and stays open across stop/restart, so `updateSensorUI()`'s existing
freshness classification (`LIVE`/`DELAY`/`STALE`/`WAIT`) already runs
continuously and can drive the setup screen's `Hand motion sensor
(required)` / `Heart-rate wearable (required)` rows and disable the Start
button before any session exists. No backend change was needed for this --
`sensor_status`/`esp32_glove.status`/`wearable_watch.status` were already
published on every frame regardless of browser session state.

## Exercise controller: program-prescribed, not auto-detected

Earlier versions mapped the Python sensor-fusion layer's `exercise_candidate`
(derived from the calibrated movement signature) directly into the browser's
active exercise. In practice this single-frame heuristic flickered on real
pose noise -- a live test session spent most of its time on "detecting
movement" despite good tracking, because small joint-angle jitter flips
between token sets frame to frame. The browser now prescribes the sequence
itself instead of guessing it: the default coach-led order is `curl ->
hammer_curl -> front_raise -> lateral_raise -> press ->
overhead_triceps_extension -> bent_over_row -> front_hold -> double_press ->
combo` (ten exercises total; "Random mix" shuffles this order and "Choose
exercises" runs only the picked subset in the same relative order),
announced one at a time (name, subtitle, ~3.2s "get ready" card) before each
set starts, the same way a coach would call out the next movement.
`exercise_candidate` still exists in the server payload/schema unchanged --
it remains useful as a research signal (e.g. comparing the camera-inferred
signature against the prescribed ground truth) -- it is just no longer
consumed to select the active exercise.

Per exercise:

- alternating curl and hammer curl count `extended -> bent -> extended` on
  the arm-extension signal;
- single-arm press, alternating front raise, and double-arm press count the
  equivalent height-signal threshold crossing; alternating lateral raise
  counts the same way on the reach-signal (lateral distance from the torso)
  instead;
- bilateral front hold counts a sustained hold once both arms clear the
  height threshold together;
- overhead triceps extension and bent-over row also use the arm-extension
  signal, but see the posture preconditions below for what actually tells
  them apart from curl;
- the combo movement (overhead press + opposite front hold) reads
  `left_overhead_right_front_candidate` / `right_overhead_left_front_candidate`
  from the live token list to render whichever physical side is actually
  overhead, since that can vary session to session or mid-set.

**Posture preconditions, not just a shared threshold.** curl, hammer_curl,
overhead_triceps_extension, bent_over_row, and combo's moving side all read
the same underlying elbow-bend (`arm_extension`) signal -- nothing
previously stopped a triceps-extension elbow bend from counting as a curl
rep, or a rowing pull from counting as either. `processRep()`'s
`posturePrecondition()` now requires the actual body posture each movement
needs before a rep counts, using two additional camera signals (see
`06_SENSOR_FUSION_PAYLOAD.md`): `upper_arm_angle_deg` (curl/hammer curl
require it to stay low -- upper arm near the torso; overhead triceps
extension requires it to stay high -- upper arm genuinely overhead) and
`torso_hinge_deg` (bent-over row requires a forward hinge; combo's anchor
side requires a roughly upright torso). These read the **raw degree**
values rather than the calibrated 0..1 signals, because a movement that
deliberately keeps the upper arm still (curl) can leave that signal's
per-session calibrated span near-degenerate, which is unstable enough to
false-trigger early in a session. When a precondition fails, the rep is
skipped (not counted) for that frame and a brief corrective message shows in
the feedback bar (e.g. "Raise your arm fully overhead before extending.",
"Hinge forward from your hips to row."), rather than either miscounting
silently or blocking with no explanation.

Curl vs. hammer curl is additionally a hard grip-rotation check on the
glove-mounted side: the ESP32's roll orientation must be non-neutral for a
curl rep or neutral (thumbs-up) for a hammer-curl rep to count on that side.
This only applies to the glove's own mounted side -- with one glove on one
wrist by design, the other arm's grip cannot be verified by any current
sensor and keeps counting from the camera's elbow-bend signal alone (the
`Camera + ...` chip above the stage says which sensors are actually
corroborating the current rep, including whether grip is checked this side).

A repetition is also gated by pose confidence, fused hand-motion stability,
and dumbbell association. On the glove-mounted side, a rep additionally
benefits from (but does not require) real IMU motion having been observed
during the bent/down phase, contributing to the "IMU CONFIRMED" counter --
that corroboration gate is soft and only applies when the hand sensor is
live, so camera-only counting keeps working when the glove is unavailable.
Heart rate is displayed as context and does not enter the form score or act
as a medical stop condition. Body position is inferred from the camera; if
the lower body is outside the frame, the system assumes a seated posture.

Difficulty is changed from the main page, outside the setup modal. The four
levels (`BEGINNER`/`ADVANCED`/`EXPERT`/`FIT`) set the target rep count and
form strictness only -- there is no session time limit. Changing the level
during a running session resets the current set with the new target and
stricter thresholds, and shows a brief reminder card (difficulty + new rep
target + the current exercise's own instruction) instead of only a toast, so
the player knows both what changed and what to do next for whichever
exercise they're on.

A related fix: `state.inTransition` (set while the "next movement" card is
showing, to pause rep counting during the transition) was previously never
cleared back to `false` once that card auto-dismissed -- only a full session
start/stop reset it. In practice this meant reps stopped counting for every
exercise after the first one in a coach-led session. `showTemporaryInstruction()`
now clears the flag itself when its timer fires, before invoking the
transition's `done` callback.

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
cylinder limbs, deltoid caps at the shoulders, sphere head, soft key + rim
lighting, subtle idle sway) with Three.js, vendored locally at
`web/vendor/three.min.js` rather than loaded from a CDN, so it keeps working
without internet in the lab. Bone angles use `pointFor3D()`, which
reprojects the exact same extension/height -> angle formulas already
validated for the project's earlier 2D model into 3D coordinates -- the
geometry logic did not change, only its output space. A
`requestAnimationFrame` loop continuously eases the drawn pose toward the
latest signal (`AVATAR_LERP_RATE`) instead of snapping on every Server-Sent
Event, so the figure reads as fluid movement regardless of how evenly the
backend publishes frames. An earlier 2D SVG model (and a still-earlier
unreachable dead-code Three.js prototype before it) were both fully removed
rather than kept as a fallback.

The avatar is split into two Three.js groups: a fixed `lowerBody` (hips,
legs, feet) and an `upperBody` pivot (torso, head, shoulders, arms,
dumbbells) parented at hip height (`AVATAR_HIP_PIVOT_Y`). Rotating
`upperBody.rotation.x` -- driven by the same raw `torso_hinge_deg` the
bent-over-row posture precondition hard-gates on -- makes the avatar
actually bend forward at the hips for that exercise, rather than only ever
animating the arms against a permanently upright torso. Everything parented
to `upperBody` (including the arm bones) rotates rigidly with it, so
`pointFor3D()`'s per-side arm math needed no changes beyond re-anchoring its
fixed shoulder point to the pivot's local coordinate space.

**Movement plane per exercise.** A real captured session
(`FitQuest_Game_7.mp4`) showed curl, hammer curl, and front raise all
rendering as the same sideways reach a lateral raise makes -- `toPoint3D()`
only ever swung a limb's "away from vertical" motion into world X (sideways,
mirrored by `sign`), with a token Z wobble for depth, so nothing
distinguished a movement's real plane. It now takes a `planeBias` parameter:
`0` is purely lateral (unchanged for `lateral_raise`, which genuinely is
sideways), positive values push the swing toward the camera (`front_raise`/
`front_hold` use `1`, a press-family movement uses a moderate `0.35`),
negative values push it away from the camera (`bent_over_row`'s elbow pulls
backward toward the ribs; `overhead_triceps_extension`'s forearm folds
behind the head instead of out to the side). Curl/hammer curl's upper arm
was also re-anchored close to vertical (previously swung 40-50deg off
vertical even at rest, reading as the arm held out and away from the body)
so only the forearm carries the visible motion, the same way a real curl
barely moves the upper arm.

**Straight arms actually render straight.** Every mode gave the forearm a
constant angular offset from the upper arm (curl 66° vs 80°, row −22°,
triceps +15°, height +9°), so a fully extended arm always drew a visible kink
at the elbow — reported as "cuando se tiene el brazo extendido, el modelo lo
dobla". The offsets look small as raw angles but the *swing* component
diverges sharply near vertical (cos 80° = 0.17 vs cos 66° = 0.41), which is
why 14° rendered as an obvious bend. Each mode is now written so that when
its driving signal reports the arm extended, the forearm angle *equals* the
upper-arm angle. Press is the one movement where "extended" is the top of the
rep, so its invariant is asserted at lockout instead: the elbow starts bent
~80° with the weight racked and converges to 0° overhead.

**Lateral raise no longer starts horizontal.** Its upper arm began at 8° —
already shoulder height — so the avatar held a permanent T-pose for the whole
set. It now starts hanging and lifts to horizontal, which is the movement.

**Anatomy.** The torso is two tapered sections (chest 0.56→0.47, waist
0.47→0.44) scaled elliptically on Z, giving a real chest-over-waist V-taper;
it previously flared *outward* toward the hips and read as a skirt. Added:
deltoid caps sized so the arm bone starts inside them at any angle, a
trapezius wedge filling the neck/shoulder notch, fists at the end of each
forearm (the dumbbell used to float at a bare stump), knees and calves.
The head is now ~1/7.5 of standing height, the real adult ratio, instead of
~1/6. Flat shading is off and segment counts are up, and the light rig gained
a fill light so the shadow side is no longer solid black.

**Dumbbell orientation.** `drawAvatar3D()` used to copy the forearm bone's
own quaternion onto the dumbbell mesh group. `placeBone3D()`'s
`setFromUnitVectors()` only constrains where the bone's +Y axis points, not
its roll around that axis -- invisible for a roll-symmetric cylinder bone,
but the same captured session showed the dumbbell's two plates ending up
stacked vertically like a totem pole instead of sitting horizontally across
the fist, because a dumbbell's bar+plates are not roll-symmetric and that
arbitrary roll has nothing to do with how one actually sits in a gripped
hand. `placeDumbbell3D()` now builds the dumbbell's own orientation instead:
its bar axis is `forearmDirection × worldUp`, which is naturally
perpendicular to the arm and level, matching gravity + grip regardless of
which way the forearm points.

**Canvas sizing survives browser zoom.** `renderer.setSize(w, h, false)` left
the canvas with a drawing buffer of `w * pixelRatio` and no CSS size at all;
an unstyled canvas lays out at its *intrinsic* (buffer) size, i.e.
`pixelRatio` times too large. At `devicePixelRatio` 1 that happened to look
correct, which is why it survived earlier testing — any zoom step or HiDPI
display broke it, rendering the avatar oversized and pushed off-screen or
leaving the stage blank. `setPixelRatio` also ran only once at init, while
browser zoom changes `devicePixelRatio`. Both are now re-applied together
from three independent triggers: `window.resize`, a `ResizeObserver` on the
mount (layout reflow never fires a window resize), and a per-frame
reconciliation in the render loop, which makes any desync self-correcting
within one frame. The per-frame check early-outs unless the size actually
changed. Note that a hidden/non-compositing tab suspends both `rAF` and
`ResizeObserver` delivery, so all three paths are inert there by design —
`window.resize` remains the synchronous fallback.

There is no session time limit -- a session ends when all of its prescribed
exercises are done, or whenever Stop is pressed with at least a few seconds
of activity, and either way a results screen shows total reps, sets, active
time, and average form quality before returning to setup, so a session has a
real beginning-to-end arc instead of resetting silently.

## Calibration

Pressing Calibrate no longer closes on a blind fixed timer. It watches the
real `control.calibration` payload every frame (`elapsed_seconds`,
`target_seconds`, `state`, `quality`) and only closes the modal once the
server actually reports `state: "tracking"`, with a live countdown and
progress bar instead of a canned animation, plus a generous safety timeout
in case the server never responds. On close it shows a quality-aware
confirmation (`calibration.quality_note`, or a client-side fallback) instead
of a plain "calibration complete" with no indication of whether the captured
range was actually meaningful -- see `06_SENSOR_FUSION_PAYLOAD.md` for
what `quality` measures and why calibration can technically "complete" (the
timer/sample-count gates pass) with a near-degenerate range if the user
barely moved.

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

Dumbbell occlusion has three tiers, not just detected/not-detected. A
side's own dumbbell status card shows:

- `CONFIRMED` (folded into "N DETECTED") -- the object detector currently sees it;
- `RECOVERING` -- `stableLoaded()`'s grace period is running (a single
  missing frame is treated as noise, not proof the weight was set down; the
  window is longer when a load was declared at setup or the glove
  corroborates real hand motion on that side), still counted loaded;
- `lost` (the feedback bar's "Dumbbell out of view" message) -- the grace
  window actually expired.

The feedback message is also side-specific and, for an alternating exercise,
keyed to whichever side is actually moving right now rather than requiring
both sides to be missing before saying anything -- a resting arm's dumbbell
going briefly out of frame no longer silently masks the active arm's
dumbbell actually being gone.

**Alternation is enforced, not just labelled.** `countMode: "alternating"`
used to be inert: `processRep()` awarded a rep to any side that completed a
down/up transition whenever `countMode` wasn't `"bilateral"`. Curling both
arms together therefore scored *two* reps from one movement, and doing eight
consecutive reps on the same arm finished an "alternating" set. Both were
reproduced from real sessions. Two rules now apply whenever the prescribed
movement alternates:

1. if both sides are in the `bent` phase simultaneously, no side may resolve
   a rep and the coach line reads "One arm at a time";
2. a resolving rep must come from the opposite side to `state.lastRepSide`
   (the first rep of a set is free); a same-side repeat returns the phase to
   `extended` without counting and names the arm to switch to.

**The forearm armband discriminates between exercises.** The ESP32+IMU case
rides a forearm armband, so its pitch measures the forearm's own elevation
against gravity (`_forearm_signals` in `ironquest/game_controls.py` normalizes
it: 0 = pointing straight down, 0.5 = horizontal, 1 = straight up, exposed as
`esp32_glove.forearm.elevation` and the `forearm_elevation` axis). This
resolves an ambiguity a single 2D camera physically cannot: curl, press, row
and triceps extension all present a bent elbow, but the forearm travels
completely differently in each.

The browser accumulates the forearm's elevation range across each rep, then
gates on three features — `span` (how far it travelled), `trough` (did it ever
hang?) and `peak` (did it ever go up?). Span is a difference, so any constant
offset from how the case is rotated on the strap cancels out of it; trough and
peak are mount-sensitive and are therefore used only as coarse bands.

Span alone was verified insufficient. A confusion matrix over the four
movements' characteristic ranges showed a `span >= 0.18` curl rule accepting a
press, a row *and* a triceps extension, because all of them also move a lot.
Adding trough/peak and raising the curl span floor to 0.32 (a row also starts
hanging and has a ~0.20 span) makes all sixteen cells correct — each rule
accepts its own movement and rejects the other three — while still accepting a
half-range curl. The bounds are estimates from movement geometry, not yet
fitted to captured data; `forearm_elevation` is exported in `signal_log`
precisely so they can be tuned against real sessions.

This gate applies only on the armband's side and only while the sensor is
live, so the camera-only arm keeps counting exactly as before.

**Gates must not block on evidence the system does not have.** The first
version of the three rules above was too aggressive and stalled a real
session at 0/8 for its entire duration. Four separate corrections came out of
that recording:

- *Alternation was a global early-return.* It tested only "both sides are in
  the bent phase", so one mis-tracked arm (the session had the left pinned at
  `arm_extension` 0.23 while it hung motionless) blocked **both** arms
  forever. It now fires only when both sides entered the bent phase within
  `SIMULTANEOUS_REP_WINDOW_MS` (700ms) — genuinely concurrent work, not
  merely concurrent state.
- *A side could get stuck bent.* If extension dropped below the down
  threshold and never recovered, that side stayed `bent` indefinitely.
  `STUCK_BENT_RESET_MS` (9s, longer than any plausible rep) releases it.
- *Alternation is only enforceable when the other arm is observable.* If the
  opposite side has shown no phase activity for `ALTERNATION_OBSERVABLE_MS`
  (12s) it is untracked, and the user may be alternating perfectly without
  the camera seeing it. Rejecting reps then would punish correct form for a
  tracking failure, so an unobservable partner disables the rule.
- *A stale `false` outlived its evidence.* Once a side was marked unloaded,
  every later unresolved frame kept returning that `false`, so the UI kept
  saying "Dumbbell out of view" while the detector reported accepted
  dumbbells in frame. `stableLoaded()` now clears a stale `false` back to
  unknown when the scene has accepted dumbbells again.

**The forearm rules are advisory, not a gate — for now.** Live hardware
disproved the absolute elevation mapping: a hanging arm reported pitch 88°
and roll −89°, giving elevation 0.99 ("straight up"), which is both wrong for
that pose and sitting in Euler gimbal lock. Gating on it rejected every curl.
The mount's rotation on the strap is not what the mapping assumes. Until
that is calibrated — record the hanging-arm orientation and measure relative
to it, or derive elevation from the accelerometer's gravity vector, which has
no singularity — the check can only advise, and the feedback bar labels it
"Form tip" rather than claiming it blocked the rep. The confusion-matrix
result above stands as the design target; it is the *input signal* that is
not yet trustworthy, not the rules.

**A dumbbell must be positively confirmed.** `loaded` is tri-state: `true`
(seen, or inside `stableLoaded()`'s occlusion grace window), `false` (grace
expired), or `null` when the detector has never reported that side. Only
`false` used to block counting, so a session where a dumbbell was never
detected at all counted every rep. Counting now requires `loaded === true`,
with a load declared at setup still sufficient on its own — that is an
explicit user statement that weight is in hand, and it is what keeps reps
counting through the occlusions the tiered status above is designed for.

**Camera framing guidance.** The same captured session that surfaced the
avatar/dumbbell issues above also showed the likely biggest real-world
driver of "dumbbell out of view" events: the webcam was framed tight and
high, so the arms (and any dumbbell in hand) were below the visible frame
for large stretches, independent of any detection logic. `updateFramingGuidance()`
watches for both arm chains (`body_posture.sides.left/right.visible`) being
missing at once; once that has been sustained for `FRAMING_GUIDANCE_MIN_LOW_MS`
(4.5s, not a single bad frame) it shows a one-time toast suggesting the user
move back or reposition the camera, then waits out `FRAMING_GUIDANCE_COOLDOWN_MS`
(25s) before it can fire again so it can't spam every frame the condition
persists.

## Camera latency

The live preview visibly lagged the user's real movement. The root cause was
not encoding or transport: `cv2.VideoCapture` was opened without configuring
its buffer, and a capture device queues several frames by default. This
pipeline runs YOLO pose plus dumbbell detection per frame, comfortably slower
than a webcam's native 30fps, so that queue fills and never drains — and
`cap.read()` returns the *oldest* queued frame. `CAP_PROP_BUFFERSIZE = 1`
(live devices only; a video file must not skip frames) makes the driver keep
only the newest frame.

This costs no accuracy. The dropped frames are ones the pipeline had no time
to process anyway, and it is what keeps the vision reading time-aligned with
the IMU and watch samples it is fused against, rather than fusing current
sensor data against several-hundred-millisecond-old vision.

Separately, the preview JPEG was being encoded at 960px for a card the browser
renders at ~290px — roughly 3x oversampling, paid for on the publishing thread
and again in browser decode. It is now 640px at quality 72
(`PREVIEW_MAX_WIDTH` / `PREVIEW_JPEG_QUALITY` in `web_gateway.py`). Detection
still runs on the full-resolution frame.

## Layout

Every column is verified to fit its viewport with no clipping at 1920x1080,
1440x900, 1366x768 and 1280x720, measured via `scrollHeight` vs `clientHeight`
rather than by eye. Two things made this fail before: the Calibrate/Start
action card scrolled away with the metric cards (it is now pinned outside
`.column-scroll`), and the right column overflowed by 36px at 1366x768 and a
further 44px at 1280x720. Two height breakpoints recover that — `max-height:
820px` tightens card padding and type, `max-height: 760px` additionally drops
the heart-rate sparkline, which is decorative next to the BPM number and zone
label it sits under.

## Verification

Run the relevant test files with the project environment (none of these
need the PyTorch/Ultralytics runtime):

```powershell
.\ironquest_env\Scripts\python.exe -m pytest tests\test_web_gateway.py tests\test_signal_motion_analysis.py tests\test_sensor_fusion_payload.py -q
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
