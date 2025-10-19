#!/bin/bash

# RDIO-VOX Installation Script
# This script installs RDIO-VOX as a systemd service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/rdio-vox"
SERVICE_USER="rdio-vox"
SERVICE_GROUP="audio"
CONFIG_DIR="/etc/rdio-vox"
LOG_DIR="/var/log"

echo -e "${GREEN}RDIO-VOX Installation Script${NC}"
echo "=================================="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root${NC}"
   exit 1
fi

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is required but not installed${NC}"
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}pip3 is required but not installed${NC}"
    exit 1
fi

echo -e "${YELLOW}Installing system dependencies...${NC}"

# Install system dependencies
if command -v apt-get &> /dev/null; then
    # Debian/Ubuntu
    apt-get update
    apt-get install -y python3-pip python3-dev portaudio19-dev libasound2-dev
elif command -v yum &> /dev/null; then
    # CentOS/RHEL
    yum install -y python3-pip python3-devel portaudio-devel alsa-lib-devel
elif command -v pacman &> /dev/null; then
    # Arch Linux
    pacman -S --noconfirm python-pip portaudio alsa-lib
else
    echo -e "${YELLOW}Please install the following packages manually:${NC}"
    echo "- python3-pip"
    echo "- portaudio development libraries"
    echo "- alsa development libraries"
fi

echo -e "${YELLOW}Creating service user...${NC}"

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$INSTALL_DIR" "$SERVICE_USER"
    echo -e "${GREEN}Created user: $SERVICE_USER${NC}"
else
    echo -e "${YELLOW}User $SERVICE_USER already exists${NC}"
fi

# Add user to audio group
usermod -a -G audio "$SERVICE_USER"

echo -e "${YELLOW}Creating directories...${NC}"

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"

# Copy files to installation directory
echo -e "${YELLOW}Copying files to installation directory...${NC}"
cp rdio_vox.py "$INSTALL_DIR/"
cp requirements.txt "$INSTALL_DIR/"
cp -r templates "$INSTALL_DIR/"
cp -r static "$INSTALL_DIR/"

# Set permissions
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$CONFIG_DIR"
chmod 755 "$INSTALL_DIR"
chmod 755 "$CONFIG_DIR"

echo -e "${YELLOW}Installing Python dependencies...${NC}"

# Create virtual environment
python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"

# Install Python dependencies in virtual environment
pip install -r "$INSTALL_DIR/requirements.txt"

# Deactivate virtual environment
deactivate

# Set permissions for virtual environment
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/venv"

echo -e "${YELLOW}Installing service files...${NC}"

# Copy service file
cp rdio-vox.service /etc/systemd/system/
chmod 644 /etc/systemd/system/rdio-vox.service

# Reload systemd
systemctl daemon-reload

echo -e "${YELLOW}Creating initial configuration...${NC}"

# Create initial configuration
python3 -c "
import json
from werkzeug.security import generate_password_hash

config = {
    'server_url': '',
    'api_key': '',
    'device_index': 0,
    'sample_rate': 44100,
    'channels': 1,
    'vox_threshold': 0.1,
    'frequency': '',
    'source': '',
    'system': '',
    'system_label': '',
    'talkgroup': '',
    'talkgroup_group': '',
    'talkgroup_label': '',
    'talkgroup_tag': '',
    'web_password': 'admin',
    'web_password_hash': generate_password_hash('admin'),
    'web_port': 8080
}

with open('$CONFIG_DIR/config.json', 'w') as f:
    json.dump(config, f, indent=2)
"

chown "$SERVICE_USER:$SERVICE_GROUP" "$CONFIG_DIR/config.json"
chmod 600 "$CONFIG_DIR/config.json"

echo -e "${YELLOW}Setting up log rotation...${NC}"

# Create logrotate configuration
cat > /etc/logrotate.d/rdio-vox << EOF
$LOG_DIR/rdio-vox.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 $SERVICE_USER $SERVICE_GROUP
    postrotate
        systemctl reload rdio-vox
    endscript
}
EOF

echo -e "${GREEN}Installation completed successfully!${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Configure the service:"
echo "   - Edit $CONFIG_DIR/config.json"
echo "   - Set your server URL and API key"
echo "   - Configure audio device and VOX threshold"
echo ""
echo "2. Start the service:"
echo "   systemctl start rdio-vox"
echo "   systemctl enable rdio-vox"
echo ""
echo "3. Access the web interface:"
echo "   http://localhost:8080"
echo "   Default password: admin"
echo ""
echo -e "${YELLOW}Service management commands:${NC}"
echo "  systemctl start rdio-vox     # Start service"
echo "  systemctl stop rdio-vox      # Stop service"
echo "  systemctl restart rdio-vox   # Restart service"
echo "  systemctl status rdio-vox    # Check status"
echo "  journalctl -u rdio-vox -f    # View logs"
echo ""
echo -e "${GREEN}RDIO-VOX is ready to use!${NC}"
