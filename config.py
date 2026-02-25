# Configuration for the location tracker

import os

# Optional: Get a free API token from https://ipinfo.io/signup
# Set the IPINFO_API_TOKEN environment variable to use it
IPINFO_API_TOKEN = os.environ.get('IPINFO_API_TOKEN', None)

# Update interval in seconds
UPDATE_INTERVAL = 60

# Web server settings
WEB_HOST = '0.0.0.0'
WEB_PORT = 5000

# Enable debug mode (set to False in production)
DEBUG = False