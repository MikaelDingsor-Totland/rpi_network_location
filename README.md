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
RTSP_URL = 'rtsp://192.168.1.100:8554/cam'  # RTSP server URL
CAMERA_RESOLUTION = '1280x720'
CAMERA_FRAMERATE = 15
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

## Limitations

⚠️ **IP geolocation provides city-level accuracy (~5-25km)**, not precise GPS coordinates. Location is based on your ISP's IP allocation.

## License

MIT License