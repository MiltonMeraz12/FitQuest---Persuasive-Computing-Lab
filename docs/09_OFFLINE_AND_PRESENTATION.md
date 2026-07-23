# Offline and Presentation Workflow

This guide explains what to do without internet, without materials, or when preparing a meeting/demo.

## If There Is No Internet

You can still run the detector if these local files exist:

```text
yolo26n-pose.pt
yolo26n.pt
runs/detect/dumbbell_combined_yolo26n/weights/best.pt
```

Run:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest detect --source 0 --object-model .\runs\detect\dumbbell_combined_yolo26n\weights\best.pt --object-conf 0.35 --dumbbell-conf 0.45 --weight-conf 0.65 --min-object-area-ratio 0.0015 --mirror
```

Capture data offline:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest capture-motion-data --label offline_capture --source 0 --duration 20 --save-every 5 --video --mirror
```

Label and train later when internet or labeling tools are available.

## If There Is No Smartwatch Yet

The prototype still works with YOLO pose and dumbbell detection. Keep saving detector payloads and videos so wearable data can be added later and compared against the same movements.

The software can already test a sample wearable file:

```powershell
.\ironquest_env\Scripts\python.exe -m ironquest check-wearable --path .\docs\wearable_sample.json --seconds 2 --stale-seconds 0
```

## If You Want To Check The Web Game Without Any Hardware

Run the offline simulator instead of the live detector. It drives the same
`MotionAnalyzer`/`build_body_context`/`build_game_control_payload` functions
with a scripted pose sequence, so the browser client can be checked end to
end (calibration, all six exercises, rep counting, sensor cards, set
completion, results screen) with no camera, ESP32, or Garmin watch:

```powershell
.\ironquest_env\Scripts\python.exe -m tools.simulate_game_control_stream
```

## If There Is No ESP32 Hardware Yet

That is fine. ESP32 + IMU is a secondary extension. The program already outputs:

```json
"esp32": {
  "status": "not_configured"
}
```

You can continue developing camera, wearable-context, and game-control logic.

## If the Detector Guesses Wrong

First decide which layer is wrong.

| Symptom | Likely layer | What to do |
| --- | --- | --- |
| No person detected | YOLO pose | Improve lighting/camera angle, lower `--conf`. |
| Wrist or elbow missing | Keypoint confidence | Lower `--pose-joint-conf` carefully. |
| Dumbbell missing | Object detector | Collect and label more local dumbbell images. |
| Expected game cue missing | Middleware payload | Inspect `motion_analysis` and `game_control` instead of exercise names. |
| Motion token wrong | Motion primitives | Tune `motion_analysis.py` thresholds. |
| Game action wrong | Game mapping | Change `game_controls.py`. |

## If Adding a Movement

Do not immediately train a model.

Recommended order:

1. Capture 5-10 clips with `capture-motion-data`.
2. Inspect `motion_analysis.signature`.
3. Decide whether existing tokens already describe it.
4. Add a primitive token only if needed.
5. Add a game mapping later.
6. Train a temporal classifier only after many labeled examples exist.

## Suggested Slide Structure

1. Project goal: turn physical dumbbell movement into structured game-ready controls.
2. Hardware plan: webcam and smartwatch first, ESP32/IMU only if direct dumbbell sensing is needed.
3. Computer vision pipeline: YOLO26 pose plus dumbbell detector.
4. Motion primitives: open-ended analysis instead of fixed exercises only.
5. Current prototype window: live camera plus dashboard.
6. Dataset workflow: capture, label, train, validate.
7. Next steps: smartwatch data access, game mapping, optional ESP32 serial/BLE, temporal classifier.

## Repository Hygiene Before Delivery

Keep:

- `ironquest/`
- `docs/`
- `README.md`
- model notes or links
- small example files if allowed

Do not commit huge generated folders unless explicitly required:

- `runs/`
- full `data/datasets/`
- videos
- cache files
- virtual environment folder `ironquest_env/`

If the repository is initialized with Git later, keep `.gitignore` updated before committing.



