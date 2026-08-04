# Weekly Report — July 27, 2026

**Project:** FitQuest — Sensor-Fusion Engine for Physical Interaction  
**Reporting period:** July 20–26, 2026  
**Current deadline:** August 7, 2026

## 1. Summary

This week FitQuest moved from an early web-game prototype toward a more reliable end-to-end system. Two real sessions using the camera, ESP32/IMU glove, and Garmin Venu 3 exposed concrete issues that could not be identified through isolated testing. I improved the sensor-fusion flow so brief dumbbell occlusions do not immediately invalidate the load, and so no single sensor can permanently block a repetition from counting. I also kept the Python detector as the authority over the browser by adding coordinated reset/recalibration and signal-freshness handling for delayed or late-start sensors. The IMU motion-intensity signal was strengthened, while the wearable now contributes independent motion and physiological context instead of only heart rate. The web game was expanded to ten exercises, three session modes, a timer-free session flow, and a fully animated 3D avatar with clearer feedback. In parallel, the ESP32/IMU case progressed to a second printed revision with updated geometry and print files. The next step is to validate the revised calibration and physical fit under real movement, then freeze the payload and organize evidence for the final paper.

## 2. Teams Update

### Last Week

- Tested the complete system using the camera, the smart glove, and the smartwatch all at the same time.
- Fixed a few bugs to make sure the movement tracking is smooth and doesn't get interrupted.
- Added more exercises to the fitness game (it now has 10 different exercises).
- Printed a better, stronger version of the plastic case for the glove sensor.

### This Week

- Make general improvements to the tracking system and the fitness game, including updates to the 3D models inside the app.
- Carefully check all the data coming into and going out of the game to make sure the tracking results are completely accurate.
- Get a gym glove or armband to securely attach the printed sensor case and run proper physical tests.
- Clean up and organize the code repository to get the whole project ready for smooth, live demo tests.

## 3. Speech

Last week, I tested the complete system using the camera, the smart sensor, and the smartwatch together. I fixed a few bugs to make the movement tracking smoother, added more exercises to the game, and printed a better version of the protective case.

This week, I will be making general improvements to the game and its 3D models, and making sure all the tracking data is completely accurate. I am also going to get a gym glove or armband to properly attach the sensor and run real physical tests. Finally, I will clean up the code repository so the whole project is ready for live demos.
