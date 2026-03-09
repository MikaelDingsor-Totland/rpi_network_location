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
RTSP_URL = 'rtsp://localhost:8554/cam' # RTSP server URL to publish to
CAMERA_RESOLUTION = '1280x720'         # Video resolution (WxH)
CAMERA_FRAMERATE = 15                  # Frames per second
CAMERA_INPUT_FORMAT = 'mjpeg'          # V4L2 input format (mjpeg, yuyv422, etc.)
CAMERA_ENCODER = 'libx264'             # Video encoder (libx264, copy, etc.)
CAMERA_PRESET = 'ultrafast'            # x264 preset (ultrafast, fast, medium, etc.)
RTSP_TRANSPORT = 'tcp'                 # RTSP transport protocol (tcp, udp)