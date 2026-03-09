# 🛰️ RPi5 Network Location Tracker

A network-based location system for Raspberry Pi 5 that determines your approximate location using IP geolocation - no GPS hardware required!

## Features

- **No Hardware Required** - Uses your network IP to determine location
- **Multi-API Fallback** - Uses ipinfo.io, ip-api.com, and ipwho.is for redundancy
- **Live Web Dashboard** - Dark-themed map with real-time updates
- **REST API** - JSON endpoints for integration with other systems
- **Location History** - Stores last 1000 location points
- **Auto-Refresh** - Updates every 60 seconds
- **Camera Streaming** - RTSP video streaming with automatic device detection and libcamera fallback

## Quick Start on Raspberry Pi 5

### 1. Clone the repository

```bash
git clone https://github.com/MikaelDingsor-Totland/rpi_network_location.git
cd rpi_network_location
```

### 2. Set up Python environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the tracker

```bash
python web_server.py
```

### 4. Open the dashboard

Open your browser and go to:
```
http://<your-pi-ip>:5000
```

Or on the Pi itself:
```
http://localhost:5000
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Web dashboard with live map |
| `GET /api/location` | Get current location as JSON |
| `GET /api/location/update` | Force a location refresh |
| `GET /api/history` | Get location history (last 100 points) |
| `GET /api/status` | Get tracker status |
| `GET /api/camera/status` | Get camera stream status |
| `GET /api/camera/detect` | Detect available cameras |
| `GET /api/camera/start` | Start RTSP camera stream |
| `GET /api/camera/stop` | Stop RTSP camera stream |

## Example API Response

```json
{
  "ip": "203.0.113.42",
  "city": "Oslo",
  "region": "Oslo",
  "country": "NO",
  "latitude": 59.9139,
  "longitude": 10.7522,
  "org": "AS12345 Example ISP",
  "timezone": "Europe/Oslo",
  "timestamp": "2026-02-25T13:00:00Z"
}
```

## Run on Boot (Optional)

To start the tracker automatically when your Pi boots:

```bash
# Create a systemd service
sudo nano /etc/systemd/system/location-tracker.service
```

Add this content:
```ini
[Unit]
Description=RPi Network Location Tracker
After=network.target

[Service]
ExecStart=/home/pi/rpi_network_location/venv/bin/python /home/pi/rpi_network_location/web_server.py
WorkingDirectory=/home/pi/rpi_network_location
User=pi
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable location-tracker
sudo systemctl start location-tracker
```

## Camera Streaming (Optional)

The project includes RTSP camera streaming support. It automatically detects available video devices and falls back to `libcamera` on modern Raspberry Pi OS when `/dev/video0` is not present.

### Prerequisites

```bash
sudo apt install ffmpeg
```

For Raspberry Pi Camera Module on Bookworm or later:
```bash
sudo apt install rpicam-apps
```

### Configuration

Edit `config.py` to set camera parameters:

```python
CAMERA_DEVICE = '/dev/video0'          # V4L2 video device path
RTSP_URL = 'rtsp://192.168.100.101:30555/cam01'  # go2rtc / Frigate RTSP URL
CAMERA_RESOLUTION = '1280x720'
CAMERA_FRAMERATE = 15
CAMERA_AUTO_START = True               # start streaming on boot
CAMERA_RESTART_DELAY = 5              # auto-restart after crash (0 = disable)
```

### Detect cameras

```bash
python camera_streamer.py
```

Or use the API:
```bash
curl http://localhost:5000/api/camera/detect
```

### Start / stop streaming

```bash
curl http://localhost:5000/api/camera/start
curl http://localhost:5000/api/camera/stop
```

### Troubleshooting: "Cannot open video device /dev/video0"

If you see `No such file or directory` when accessing `/dev/video0`:

1. **Check connected devices:** `ls /dev/video*`
2. **Enable the camera** via `sudo raspi-config` → Interface Options → Camera
3. **Load the V4L2 driver** (older Pi OS): `sudo modprobe bcm2835-v4l2`
4. **Use libcamera** (Bookworm+): The streamer automatically falls back to `rpicam-vid`/`libcamera-vid` when no V4L2 device is found.
5. **USB cameras:** Ensure the camera is plugged in and recognised (`lsusb`).

## Frigate NVR Integration

Stream your RPi camera to [Frigate](https://frigate.video) for AI-powered object detection, recording and alerts.

### How it works

```
RPi (camera_streamer.py)
  └─ ffmpeg → RTSP push → go2rtc (:30555) → Frigate (detect + record)
```

The RPi pushes an H.264 RTSP stream to the **go2rtc** component that ships inside Frigate. Frigate then uses that stream for object detection and recording.

### Step 1 — Configure the RPi

Edit `config.py` so the stream points at your Frigate server:

```python
RTSP_URL = 'rtsp://192.168.100.101:30555/cam01'   # go2rtc RTSP listener
CAMERA_AUTO_START = True                           # start on boot
CAMERA_RESTART_DELAY = 5                           # auto-reconnect
```

### Step 2 — Configure Frigate

Copy the included example and adapt it:

```bash
cp frigate.yml.example /path/to/your/frigate/config/frigate.yml
```

Key sections in `frigate.yml`:

```yaml
go2rtc:
  streams:
    cam01:
      - rtsp://127.0.0.1:30555/cam01
  rtsp:
    listen: ":30555"          # must match RTSP_URL port in config.py

cameras:
  rpi_cam01:
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:30555/cam01
          roles: [detect, record]
    detect:
      width: 1280
      height: 720
      fps: 5
```

### Step 3 — Start everything

On the RPi:

```bash
python web_server.py
```

The camera stream auto-starts and Frigate should show **"Rpi Cam01"** as online within a few seconds.

### Troubleshooting Frigate "No frames have been received"

| Symptom | Fix |
|---------|-----|
| *"Rpi cam01 is offline"* in Frigate UI | Make sure `camera_streamer.py` is running on the RPi and the RTSP_URL matches the go2rtc `listen` port. |
| *"No frames have been received, check error logs"* | Verify the RPi can reach the Frigate server: `curl -v rtsp://192.168.100.101:30555/` from the RPi. Check firewall rules. |
| Stream starts then drops | The auto-restart watchdog re-launches ffmpeg automatically. Check `CAMERA_RESTART_DELAY` in `config.py`. |
| High latency | Use `CAMERA_ENCODER = 'libx264'`, `CAMERA_PRESET = 'ultrafast'`, and `RTSP_TRANSPORT = 'tcp'` (all defaults). |

## Limitations

⚠️ **IP geolocation provides city-level accuracy (~5-25km)**, not precise GPS coordinates. Location is based on your ISP's IP allocation.

## License

MIT License