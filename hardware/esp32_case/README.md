# ESP32 + BNO08x Glove Case

Physical case for the ESP32-S3 + BNO08x IMU that mounts in the right-hand gym
glove (see [docs/09_ESP32_IMU_HARDWARE.md](../../docs/09_ESP32_IMU_HARDWARE.md)
and [docs/reports/2026-07-20_weekly_report.md](../../docs/reports/2026-07-20_weekly_report.md)).

| File | Purpose |
| --- | --- |
| `ESP32_Case.blend` | Source Blender model. Edit this file for design changes. |
| `ESP32_Case.stl` | Exported mesh for slicing on any printer/slicer. Matches the current `ESP32_Case.blend`. |
| `CE5_ESP32_Case_2.gcode` | Print-ready G-code for the current revision, sliced for the CE5 printer profile. |

The case is on its second revision; the first revision's G-code was dropped once
revision 2 was printed and validated. Blender's `.blend1` autosave is gitignored,
since Blender regenerates it on every save.

After changing `ESP32_Case.blend`, re-export `ESP32_Case.stl` and re-slice the
G-code so all three files describe the same physical part.
