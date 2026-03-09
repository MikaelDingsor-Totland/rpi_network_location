# Configuration for the location tracker

# Optional: Get a free API token from https://ipinfo.io/signup
IPINFO_API_TOKEN = None  # e.g., "your_token_here"

# Update interval in seconds
UPDATE_INTERVAL = 60

# Web server settings
WEB_HOST = '0.0.0.0'
WEB_PORT = 5000

# Enable debug mode (set to False in production)
DEBUG = False

# Camera streaming settings
CAMERA_DEVICE = '/dev/video0'          # V4L2 video device path
CAMERA_RESOLUTION = '1280x720'         # Video resolution (WxH)
CAMERA_FRAMERATE = 15                  # Frames per second
CAMERA_INPUT_FORMAT = 'mjpeg'          # V4L2 input format (mjpeg, yuyv422, etc.)
CAMERA_ENCODER = 'libx264'             # Video encoder (libx264, copy, etc.)
CAMERA_PRESET = 'ultrafast'            # x264 preset (ultrafast, fast, medium, etc.)
RTSP_TRANSPORT = 'tcp'                 # RTSP transport protocol (tcp, udp)

# Frigate / go2rtc integration
# Point this at the go2rtc RTSP listener on your Frigate server.
# Default go2rtc RTSP port is 8554; change to match your setup.
RTSP_URL = 'rtsp://192.168.100.101:30555/cam01'

# Auto-start: begin streaming as soon as web_server.py starts
CAMERA_AUTO_START = True

# If the ffmpeg process exits, wait this many seconds before restarting.
# Set to 0 to disable auto-restart.
CAMERA_RESTART_DELAY = 5

# Maximum consecutive restart attempts before giving up (0 = unlimited).
CAMERA_MAX_RESTARTS = 0