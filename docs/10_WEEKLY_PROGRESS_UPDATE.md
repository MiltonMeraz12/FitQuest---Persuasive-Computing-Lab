# Weekly Progress Update - Iron Quest 3D

## Teams Update

Last week:

- Improved the ESP32/IMU integration so the system can listen through USB and Wi-Fi from the same normal launcher.
- Kept the live pipeline focused on the camera, dumbbell detection, ESP32 motion data, and normalized sensor-fusion payloads.
- Added the Garmin Venu 3 connection path into the system through a BLE heart-rate bridge and wearable JSON file.
- Updated the analysis flow so Garmin data can support heart-rate, exertion, and intensity context for recorded sessions.

This week:

- Improve the ESP32/IMU setup so it is more stable and easier to test.
- Improve the UI so the live demo is clearer and easier to understand.
- Start designing and printing the ESP32/IMU case.
- Keep the Garmin path as a secondary signal for session intensity and data quality.

Next four-week focus:

- Improve the ESP32/IMU, UI, and physical case.
- Build a small game prototype that uses the system signals.
- Restructure and clean the project where needed.
- Prepare the final research paper.

## Short Speech

Last week I improved the hardware side of the project. The ESP32 and IMU path is now more stable because the system can listen through USB and Wi-Fi using the same launcher. I also added the Garmin Venu 3 path, so the system can start collecting heart-rate context through the wearable data pipeline.

This week I will focus on the parts that need to become more stable and presentable: the ESP32/IMU, the interface, and the first physical case for the sensor. I will be designing and 3D printing a custom case specifically for this ESP32 and IMU combo. I need to design it so it can be easily strapped to an armband or a gym glove for real testing.
