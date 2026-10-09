# Raspberry Pi 4 B: first camera test

First milestone: run Fastener Bench on the Pi with a USB webcam, view it from your PC, and measure stationary parts reliably. Pi hardware performance has not been tested yet. The ribbon-connected Pi Camera needs a separate Picamera2 capture integration; these steps use a USB webcam.

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
scp app.py vision.py ruler.py index-v2.html YOUR_USER@fastener-pi.local:~/fastener-cv/
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
python3 app.py --camera 0 --host 0.0.0.0 --reset-calibration
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
