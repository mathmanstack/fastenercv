# Fastener Bench

For Raspberry Pi 4 B with a USB webcam, see [PI_SETUP.md](PI_SETUP.md). The app supports Linux camera capture and optional LAN access with `--host 0.0.0.0`.

Run `./start.ps1` in PowerShell, then open http://127.0.0.1:8765 .
The default is camera index 1 (the second connected camera). Dependencies are local in `vendor`; Python is the installed KiCad Python.

The current setup uses the protractor's ruler edge. Click **Calibrate ruler: 2 marks**, enter the real distance in mm, and click those marks in the full camera view. The 1-inch to 5-inch span is 101.6 mm. Calibration is saved locally. A visual ruler tracker follows modest translations; if it loses the reference, dimensions stop until recalibration. Camera zoom, focus, rotation, perspective changes or a different ruler require recalibration. The two-point ruler calibration assumes the camera faces the surface squarely and does not correct perspective.

The parts area normally follows the space above the ruler to exclude printed markings. **Set parts area** overrides that area. The view zooms on this area, readings are smoothed across successive frames, and short or unclear silhouettes are labelled without inventing a shaft size. Nominal labels can contain two candidate diameters when they are too close to distinguish.

The app estimates shaft diameter and under-head length from outlines using the SD card as a planar scale reference. Full SD adapters are 32 × 24 mm; microSD cards are 15 × 11 mm. Select the correct card type. Automatic detection works best with a dark card on a plain, light surface. Manual calibration accepts four corners around the outer rectangle; extend the clipped corner to its rectangular intersection.

Place fasteners apart, away from the box edge, lying flat at the same distance from the camera as the card. Improve focus and lighting for narrow shafts. Moving the camera requires recalibration. Automatic scale detection assumes the detected rectangle is the SD card; confirm the green outline before relying on results.

These are visual estimates, not verified specifications. Shadows, reflections, lens distortion, elevation above the card plane, and overlapping objects affect measurements. Pointed tips suggest a screw; blunt bolts and machine screws cannot reliably be distinguished by silhouette. Thread pitch, material, and thread standard are not established. Nominal M labels are nearest metric diameter suggestions.

Save measurement writes an annotated JPEG and JSON into `captures/`. Camera frames are processed locally; the server binds only to 127.0.0.1.

Reference dimensions: https://www.sdcard.org/developers/sd-standard-overview/capacity-sd-sdhc-sdxc-sduc/
