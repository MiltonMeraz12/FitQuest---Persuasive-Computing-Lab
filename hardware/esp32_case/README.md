# ESP32 + BNO08x Glove Case

Physical case for the ESP32-S3 + BNO08x IMU that mounts in the right-hand gym
glove (see [docs/16_ESP32_IMU_WIRELESS_NEXT_STEP.md](../../docs/16_ESP32_IMU_WIRELESS_NEXT_STEP.md)
and [docs/21_WEEKLY_DETAILED_REPORT_2026_07_20.md](../../docs/21_WEEKLY_DETAILED_REPORT_2026_07_20.md)).

| File | Purpose |
| --- | --- |
| `ESP32_Case.blend` | Source Blender model. Edit this file for design changes. |
| `ESP32_Case.blend1` | Blender's automatic backup of the previous save. Safe to delete; Blender regenerates it on every save. |
| `ESP32_Case.stl` | Exported mesh for slicing on any printer/slicer. Matches the current `ESP32_Case.blend` revision. |
| `CE5_ESP32_Case.gcode` | Print-ready G-code, first revision, sliced for the CE5 printer profile. |
| `CE5_ESP32_Case_2.gcode` | Print-ready G-code, second revision (matches the current `ESP32_Case.stl`/`.blend`). Use this one unless you specifically need the first revision. |
