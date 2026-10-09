# Raspberry Pi: camera setup

Fastener Bench supports ribbon-connected Raspberry Pi cameras through Picamera2 and USB webcams through OpenCV. Pi hardware performance has not been tested yet.

## Quick start: ribbon-connected Pi Camera over Tailscale

Use Raspberry Pi OS with the modern libcamera camera stack (Bookworm or newer recommended). Power off the Pi before connecting the camera ribbon. A Pi Zero uses a different camera ribbon connector from a Pi 4.

In your Pi SSH terminal, install dependencies and confirm that the camera is detected:

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-opencv python3-numpy rpicam-apps git
rpicam-hello --list-cameras
```

For a fresh checkout:

```bash
git clone https://github.com/mathmanstack/fastenercv.git
cd fastenercv
```

If you already cloned it, use `cd ~/fastenercv` and `git pull` instead. Then start:

```bash
python3 app.py --host 0.0.0.0 --reset-calibration
```

Open `http://PI_TAILSCALE_IP:8765` on your PC with Tailscale connected. Keep SSH open; Ctrl+C stops the app. The camera runs without a desktop preview. Calibrate using two ruler marks in the browser. On later launches omit `--reset-calibration` to keep your saved calibration. If you change resolution or camera placement, recalibrate.

The Pi Camera defaults to 1280x960 output and explicitly chooses a sensor mode with the largest field of view. On Camera V2 this uses the 1640x1232 binned mode covering the full 3280x2464 sensor, avoiding the cropped 1080p and 640x480 sensor modes. Smaller output such as 640x480 is scaled from that wide sensor mode. Keep a 4:3 output aspect ratio to retain nearly the entire V2 view; 16:9 output trims the top and bottom. The browser starts with **Zoom on parts** disabled and keeps the full view after calibration; you can enable zoom manually. Recalibrate after switching from the old view.

The default `--camera-backend auto` tries detected ribbon cameras first, verifying a captured frame, then looks for a working USB webcam. On Linux it scans USB video devices only, skipping Pi codec/ISP nodes and video nodes that cannot deliver frames. Missing Picamera2 also allows USB fallback. The selected camera appears in the terminal and browser status. If capture fails, discovery retries, again preferring the Pi Camera. While a USB camera is working, restart the app to select a newly connected Pi Camera (power off before handling the ribbon).

In auto mode, `--camera` and the browser's Camera index control specify the preferred USB index; the Pi Camera still has priority. Use `--camera-backend picamera2 --camera 0` to force the Pi Camera, or `--camera-backend opencv --camera 0` to force USB. With forced Picamera2, use the index from `rpicam-hello --list-cameras`.

Auto mode defaults to 1280x960 and clears calibration when the camera identity or delivered resolution changes. Calibrate the newly selected camera before measuring; settings are saved when you calibrate in the browser. A USB webcam may negotiate a different resolution.

Troubleshooting:

- If no camera is listed, power off and check the ribbon seating, orientation, and camera compatibility. Confirm camera detection before starting the app.
- If the camera is busy, close other camera applications, including any `rpicam-*` preview.
- If Python cannot import Picamera2, use the system `python3` with the apt packages above. For a virtual environment, create it with `python3 -m venv --system-site-packages .venv`.
- On a slower Pi, try `--width 640 --height 480` and recalibrate; lower resolution reduces measurement detail. No Pi Zero frame-rate guarantee has been measured.
- Focus the lens on your measurement surface before calibrating. For a Camera Module 3, allow autofocus to settle; changing focus can affect measurement scale.

Picamera2 provides BGR arrays using its `RGB888` format, matching the existing OpenCV detection pipeline. See the [official Picamera2 manual](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf) and [installation instructions](https://github.com/raspberrypi/picamera2#installation).

## USB webcam setup

## 1. Prepare the Pi

Use Raspberry Pi Imager to install Raspberry Pi OS Lite (64-bit) for a headless setup. In Imager, set hostname `fastener-pi`, create your own username/password, configure Wi-Fi, and enable SSH. Use a suitable Pi 4 power supply, microSD card, and cooling. Connect the USB camera and boot. Keep the PC and Pi on the same local network.

Official instructions: https://www.raspberrypi.com/documentation/computers/getting-started.html

## 2. Install dependencies on the Pi

Replace `YOUR_USER` throughout with the username you created. From Windows PowerShell:

```powershell
ssh YOUR_USER@fastener-pi.local
```

Then in the Pi terminal:

```bash
sudo apt update
sudo apt install -y python3-opencv python3-numpy v4l-utils
mkdir -p ~/fastener-cv
exit
```

## 3. Copy the application from Windows

In PowerShell, from this project directory:

```powershell
scp app.py camera.py vision.py ruler.py index-v2.html YOUR_USER@fastener-pi.local:~/fastener-cv/
```

Do not copy `vendor` (Windows binary dependencies), `start.ps1`, or the old camera calibration/reference. Linux dependencies come from apt. No KiCad installation is needed on the Pi.

## 4. Start the camera

```powershell
ssh YOUR_USER@fastener-pi.local
```

On the Pi:

```bash
cd ~/fastener-cv
v4l2-ctl --list-devices
python3 app.py --camera-backend opencv --camera 0 --host 0.0.0.0 --reset-calibration
```

Open `http://fastener-pi.local:8765` in your PC browser. If the hostname fails, find the Pi's IP in your router or with `hostname -I` on the Pi, then use `http://PI_IP:8765`. The camera must be plugged into the Pi. Keep the SSH terminal open; Ctrl+C stops the application. The server has no authentication: use it only on a trusted LAN, without internet port forwarding.

If no image appears, use the capture device index reported by `v4l2-ctl`; a webcam can expose multiple video nodes. Check supported formats with `v4l2-ctl -d /dev/video0 --list-formats-ext`.

Mount the camera squarely above the table, use diffuse lighting, and keep parts separated. Click **Calibrate ruler: 2 marks**, enter the known spacing, select both marks, and set the parts area. Use known fasteners and calipers to assess measurement error. New calibration saves when you use the UI. On later launches, omit `--reset-calibration` to reuse it.

The default request is 1920x1080, matching the original application. If processing is slow, try `--width 1280 --height 720 --reset-calibration` and recalibrate. Cameras can negotiate a different actual resolution. Lower resolution affects measurement quality and pixel-based detection thresholds; verify accuracy again. There is no measured Pi frame-rate guarantee.

## 5. Move toward the SCARA sorter

Suggested architecture: USB camera -> Pi (vision, part selection, bin choice) -> USB serial -> microcontroller (homing, motor timing, limit switches) -> motor drivers -> arm. Power motors through a suitable separate motor supply.

Build up in stages:

1. Stable measurements on the Pi with a fixed camera and stationary parts.
2. Add grasp position and angle, a camera-to-robot coordinate calibration, and frame timestamps. The current ruler scale measures dimensions; it does not establish the robot origin or arm coordinates.
3. Home the arm and prove slow moves to known table positions, with working limits and emergency stop.
4. Implement command acknowledgments and a detect/pick/place/recheck cycle for one stationary part at a time. Suppress duplicate picks and verify successful removal.
5. Measure cycle time, then optimize vision and arm motion. Moving conveyor picks additionally require motion tracking and timing/encoder integration.

The current app is a measurement interface, not yet a robot controller. Its `/state` endpoint exposes detections but is not a complete or freshness-checked robot command interface.

Camera documentation: https://www.raspberrypi.com/documentation/computers/camera_software.html
