# Weekly Detailed Report - Iron Quest 3D

| Field | Value |
| --- | --- |
| Date | 2026-07-13 |
| Reporting focus | ESP32/IMU improvements, UI refinement, physical case planning, and Garmin Venu 3 integration |
| Current deadline | 2026-08-07 |
| Primary output | Reliable multi-sensor middleware evidence for the research paper |

## 1. Executive Summary

This week focused on improving the full sensor-fusion workflow and preparing the next project phase. The ESP32/IMU path was strengthened so the normal launcher can handle both USB serial and Wi-Fi telemetry through the same runtime. This makes the motion-sensor side more practical for testing because the system no longer depends on choosing one transport manually before each run.

The Garmin Venu 3 path was also integrated into the project architecture. The watch is being treated as a wearable context source, mainly for heart rate, exertion level, and intensity zone. This is useful because it can provide a secondary check on session effort while the ESP32/IMU remains the primary motion sensor. The BLE bridge and wearable JSON contract are now connected to the one-command runtime, although live watch discovery still needs final validation with the watch actively broadcasting heart rate.

## 2. Last Week

- Improved the ESP32/IMU runtime so the normal launcher can listen for USB serial and Wi-Fi telemetry together.
- Preserved the ESP32/IMU as the main motion source for hand and glove movement.
- Added the Garmin Venu 3 BLE heart-rate bridge into the system startup flow.
- Connected the Garmin path to the existing wearable JSON contract used by the main middleware.
- Extended the wearable data structure to support heart rate, heart-rate contact, resting/max heart-rate references, and optional RR interval values.
- Updated offline capture analysis so recorded sessions can summarize Garmin/wearable status, heart-rate values, exertion level, and intensity zones.
- Confirmed that the system can still run through the single launcher command.

## 3. This Week

- Improve the ESP32/IMU setup so it is more stable for repeated testing.
- Improve the live UI so the demo is easier to understand.
- Start designing and printing a physical case for the ESP32/IMU prototype.
- Keep testing the Garmin path as a secondary source for effort and session context.

## 4. Remaining Four-Week Plan

- Improve the ESP32/IMU, UI, and physical case first.
- Build a small game prototype that consumes the system signals.
- Continue project restructuring and cleanup where needed.
- Assemble the final research paper with evidence from the working system.

## 5. Current Technical Status

| Area | Current status |
| --- | --- |
| Camera tracking | Functional and ready for combined testing. |
| Dumbbell/object detection | Functional within the current middleware scope. |
| ESP32/IMU over USB | Functional as the stable baseline. |
| ESP32/IMU over Wi-Fi | Functional as the wireless telemetry path. |
| ESP32 auto transport | Improved so USB and Wi-Fi can be handled from the same runtime. |
| Garmin Venu 3 bridge | Implemented in the software path through BLE heart-rate and wearable JSON. |
| Garmin live validation | Still needs final confirmation with the watch broadcasting and visible to the laptop. |
| Offline analysis | Extended to include wearable heart-rate and intensity summaries. |
| Game prototype | Planned for the next phase using the normalized system signals. |

## 6. Why The Garmin Data Helps

The Garmin Venu 3 should not replace the ESP32/IMU as the motion sensor. The ESP32 is better positioned for direct hand and glove motion because it provides acceleration, gyroscope, orientation, and timing data from the mounted hardware.

The Garmin data is useful as a complementary source:

- It can show whether a recorded session had low, moderate, high, or peak effort.
- It can provide heart-rate context for comparing similar movement sessions.
- It can help identify unusual recordings, for example strong motion with no physiological change or a high heart-rate session with weak movement signals.
- It can support paper evidence by showing that the middleware accepts both movement telemetry and wearable context.
- It can become a lightweight double-check for calibration and session quality, as long as it is not treated as a medical decision signal.

## 7. Risks And Decisions

- Garmin BLE heart-rate broadcast may not always be visible to the laptop, so the project should keep the JSON bridge design even if the data comes from another Garmin path later.
- Raw accelerometer or gyroscope data from the Garmin would require a more complex route such as Connect IQ, SDK access, or exported activity files.
- The safest technical decision is to finish reliable heart-rate context first, then only pursue deeper watch sensors if they clearly improve the research evidence.
- The ESP32/IMU should remain the primary motion source while the game prototype uses the normalized signals produced by the middleware.

## 8. Short Speech For Meeting

Last week I improved the sensor side of the project. The ESP32 and IMU are now better integrated because the system can listen through USB and Wi-Fi using the same normal launcher. I also added the Garmin Venu 3 path into the system, so it can provide heart-rate and intensity context through the wearable data pipeline.

This week I will focus on the main pieces that need to become stable and presentable: improving the ESP32/IMU, improving the UI, and starting the physical case. After that, the remaining work will move toward a small game prototype, project cleanup, and the final paper.

## 9. Summary For Supervisor

The project has moved from separate hardware tests toward a more complete multi-sensor runtime. The ESP32/IMU path is now stronger because USB and Wi-Fi telemetry can be handled from the same workflow. The next priority is to make the prototype more stable, clearer to demonstrate, and physically easier to use, while preparing for a small signal-driven game prototype and the final paper.
