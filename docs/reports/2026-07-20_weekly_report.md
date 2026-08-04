# Weekly Detailed Report — July 20, 2026

## Project

**FitQuest — Sensor-Fusion Engine for Physical Interaction**  
**Original project title:** *IronQuest 3D - Smart Dumbbell Fitness Gaming Platform*  
**Reporting period:** July 13-19, 2026  
**Internship start date from invitation:** May 18, 2026  
**Maximum internship duration:** 12 weeks  
**Current project/paper deadline:** August 7, 2026

## Executive Summary

This week the project moved closer to a stable, demonstrable physical prototype. The 3D model of the protective case for the ESP32 and IMU was completed; the remaining hardware step is to print the first version and validate the fit during motion testing. In parallel, I continued consolidating the ESP32/IMU runtime and the Garmin Venu 3 telemetry path so that motion and physiological context can be recorded through the project's normalized wearable-data pipeline. The final application scope is now explicit: a small web-based game prototype will consume the resulting `game_control` signals.

## Alignment With the Original Project and Current Intro Slide

The original invitation describes **IronQuest 3D - Smart Dumbbell Fitness Gaming Platform**: sensor-enabled dumbbells connected to a 3D web game, with repetition, tempo, and range-of-motion signals supporting feedback, goals, analytics, and exercise adherence. It also frames the internship around an application or system for monitoring health and well-being. The invitation records a May 18, 2026 start date and a maximum duration of 12 weeks.

The current introduction slide presents the active research phase as **FitQuest**. Its problem statement, camera + YOLO, ESP32 + IMU, Garmin Venu 3, normalized JSON/JSONL pipeline, and expected HCI/rehabilitation impact accurately describe the work now being completed at the lab. The slide also includes the institutional logos, profile photo, Mitacs role, origin, supervisors, ORCID, and contact information.

After arriving at Dalhousie, the immediate research deliverable was narrowed to a reliable sensor-fusion middleware foundation because of the research-paper timeline. The original game direction remains part of the project, but its final scope is intentionally small: a web-based proof-of-concept that consumes the normalized signals and demonstrates a few movement-to-action mappings. The current case, camera, IMU, wearable, calibration, and JSON/JSONL work directly supports that application.

## Teams Update

Last week:

- Completed the 3D model of the ESP32/IMU case. The first physical print is still pending.
- Improved the ESP32/IMU integration so the system can listen through USB and Wi-Fi from the same normal launcher.
- Kept the live pipeline focused on the camera, dumbbell detection, ESP32 motion data, and normalized sensor-fusion payloads.
- Continued the Garmin Venu 3 connection path through the Connect IQ HTTP receiver and wearable JSON contract, with BLE available as a fallback.
- Updated the analysis and runtime flow so Garmin data can support heart-rate, exertion, and intensity context for recorded sessions.

This week:

- Improve the ESP32/IMU setup so it is more stable and easier to test inside the printed case.
- Print and validate the case, including sensor orientation, cable routing, USB access, reset/button access, LED visibility, and mounting stability.
- Improve the UI so the live demo clearly shows camera, ESP32/IMU, and wearable status.
- Build the confirmed minimal web-based game slice using the existing `game_control` signals, with two or three movement-to-action mappings and visible feedback.
- Run one controlled end-to-end session and capture screenshots, normalized JSON/JSONL output, and game input-to-action evidence for the paper.

Next four-week focus:

- Improve the ESP32/IMU, UI, and physical case.
- Build and connect the small web-based game prototype.
- Complete integrated camera, dumbbell, ESP32/IMU, and wearable testing where available.
- Restructure and clean the project only where needed for reproducibility.
- Prepare the final research paper, figures, limitations, and demonstration package.

## Plan Through the End of the Internship / Current Deadline

### July 27–August 2

- Complete the first case-print validation and make one small revision if fit or cable access requires it.
- Repeat integrated trials and verify arm extension, range, symmetry, stability, and exertion-related signals.
- Freeze the first version of the payload schema and organize reproducible logs, screenshots, and figures.
- Implement and test the small web-based game prototype using the existing `game_control` payload. Avoid unrelated sensors, large refactors, multiplayer, and complex game mechanics.

### August 3–7

- Freeze the system configuration and document the reproducible commands and data flow into the browser game.
- Finalize the game demo, figures, screenshots, results, limitations, and the paper package.
- Rehearse the demonstration and prepare a concise explanation of the hardware case, sensor-fusion pipeline, and next steps.

## Current Status

| Component | Status |
|---|---|
| Camera / YOLO pose and object detection | Functional; continuing controlled validation |
| ESP32 / IMU USB and Wi-Fi telemetry | Integrated; stability and physical mounting still being refined |
| ESP32 / IMU 3D case | CAD model complete; printing and fit validation pending |
| Garmin Venu 3 / Connect IQ bridge | Bridge and data contract implemented; final live-watch validation pending |
| Wearable JSON/JSONL and offline analysis | Available for HR, intensity, and exertion context |
| UI / demo flow | Functional; status visibility and presentation polish ongoing |
| Web-based game prototype | Confirmed deliverable; minimal browser vertical slice to be implemented and connected to `game_control` |
| Research-paper evidence package | In progress; logs, screenshots, figures, and limitations still to be finalized |

## Risks and Mitigation

- **Case fit or cable access may need revision:** print a first version early, test it with the actual board and sensor, and document the revision.
- **Garmin live access may be intermittent:** keep the Connect IQ path, the documented fallback, and recorded/mock data available for validation; clearly report access and latency limitations.
- **Limited time before August 7:** keep the web game to a minimal playable slice and prioritize stable sensor-fusion evidence and paper-ready documentation over extra features.

## Short Speech

Last week I completed the 3D model of the protective case for the ESP32 and BNO08x IMU. The purpose is to move from a fragile electronics setup to a repeatable physical prototype that keeps the sensor orientation stable during movement tests. I have not printed it yet, so this week I will print the first version and check the fit, cable access, reset and LED access, and mounting stability. Then I will run a short integrated test with the camera and IMU, use Garmin heart-rate data as supplementary context, and connect the resulting signals to a simple web-based game prototype. This will give me a more reliable setup, a concrete end-to-end demonstration, and stronger evidence for the sensor-fusion pipeline and final paper.
