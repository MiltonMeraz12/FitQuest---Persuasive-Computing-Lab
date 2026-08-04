# Project Improvement Backlog

The backlog is ordered for the August 7, 2026 paper deadline.

## Priority 1: Runtime Cleanup Validation

- Confirm `python -m ironquest --help`.
- Confirm `full`, `detect`, `capture-motion-data`, `check-wearable`, and `check-esp32`.
- Confirm removed commands are not shown in help.
- Run `pytest`.

## Priority 2: Dynamic Signal Calibration

- Validate `--calibration-seconds` with a short user-specific calibration routine.
- Confirm left/right normalized range trends with controlled arm movements.
- Confirm `symmetry_score` behaves correctly for intentionally asymmetric motions.
- Export `signal_log` with Pandas and create one movement-signal graph.

## Priority 3: UI Improvement

- Make the clean HUD easier to explain in a supervisor demo.
- Keep vision status, ESP32 status, and Garmin status visible.
- Add clear but non-intrusive calibration/status text if needed.
- Keep debug mode useful for JSON payload inspection.
- Save screenshots for paper figures.

## Priority 4: Dumbbell Dataset Evidence

- Capture controlled videos with the real weights.
- Label new frames only for active object classes.
- Validate object detector metrics.
- Save representative success and failure frames.

## Priority 5: ESP32 + IMU Bring-Up

- Confirm BNO08x serial JSON reaches Python.
- Log pitch, roll, yaw, acceleration, and gyroscope data.
- Confirm `stability_index` and motion deltas are logged without reducing camera FPS.
- Confirm the IMU mount inside the gym glove stays stable during dumbbell movement.

## Priority 6: Garmin Venu 3 Bridge

- Confirm what access path is available: BLE heart-rate, Garmin SDK, Connect IQ, or exported file bridge.
- Write heart-rate samples to the existing wearable JSON shape.
- Align samples with JSONL frame logs.
- Validate `exertion_level` and `intensity_zone` with controlled mock data.
- Document latency and access limits honestly.

## Priority 7: Paper Package

- Freeze example payload schema.
- Create figures for architecture, UI, and sample data.
- Write limitations around 2D camera depth, sensor latency, mounting, and dataset size.
- Prepare reproducible commands.

## Priority 8: Minimal Web Game Slice

- Create a browser client that reads the normalized `game_control` payload.
- Map two or three stable signals or motion events to visible actions.
- Add simple feedback such as a target, score, progress bar, or success state.
- Capture one short end-to-end demonstration and document the mapping and limitations.

## Do Not Prioritize Now

- Complex game mechanics, multiplayer, large content systems, or production-grade backend work.
- New unrelated sensors.
- Broad refactors that do not improve the paper evidence.
