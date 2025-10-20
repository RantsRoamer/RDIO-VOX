#!/bin/bash

# RDIO-VOX Update Script
# This script updates RDIO-VOX from the official repository

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
TEMP_DIR="/tmp/rdio-vox-update"
REPO_URL="https://github.com/RantsRoamer/RDIO-VOX.git"

echo -e "${GREEN}RDIO-VOX Update Script${NC}"
echo "=================================="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root${NC}"
   exit 1
fi

# Create temporary directory
echo -e "${YELLOW}Creating temporary directory...${NC}"
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

# Clone latest version
echo -e "${YELLOW}Downloading latest version...${NC}"
git clone "$REPO_URL" "$TEMP_DIR"

# Stop the service
echo -e "${YELLOW}Stopping RDIO-VOX service...${NC}"
systemctl stop rdio-vox

# Backup current installation
echo -e "${YELLOW}Backing up current installation...${NC}"
BACKUP_DIR="/opt/rdio-vox.bak.$(date +%Y%m%d_%H%M%S)"
if [ -d "$INSTALL_DIR" ]; then
    mv "$INSTALL_DIR" "$BACKUP_DIR"
    echo -e "${GREEN}Current installation backed up to: $BACKUP_DIR${NC}"
fi

# Install new version
echo -e "${YELLOW}Installing new version...${NC}"
mkdir -p "$INSTALL_DIR"
cp -r "$TEMP_DIR"/* "$INSTALL_DIR/"

# Restore configuration
if [ -f "$CONFIG_DIR/config.json" ]; then
    echo -e "${YELLOW}Restoring existing configuration...${NC}"
    # Check if auto_start exists in current config
    if ! grep -q "auto_start" "$CONFIG_DIR/config.json"; then
        echo -e "${YELLOW}Adding auto_start setting to existing configuration...${NC}"
        # Create a backup
        cp "$CONFIG_DIR/config.json" "$CONFIG_DIR/config.json.bak"
        # Add auto_start setting
        python3 -c "
import json
with open('$CONFIG_DIR/config.json', 'r') as f:
    config = json.load(f)
config['auto_start'] = config.get('auto_start', False)
with open('$CONFIG_DIR/config.json', 'w') as f:
    json.dump(config, f, indent=2)
"
        echo -e "${GREEN}Configuration updated with auto_start setting.${NC}"
        echo -e "${YELLOW}Backup saved as config.json.bak${NC}"
    fi
fi

# Update Python dependencies
echo -e "${YELLOW}Updating Python dependencies...${NC}"
# Create new virtual environment
rm -rf "$INSTALL_DIR/venv"
python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"
pip install -r "$INSTALL_DIR/requirements.txt"
deactivate

# Set permissions
echo -e "${YELLOW}Setting permissions...${NC}"
chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
chmod 755 "$INSTALL_DIR"
chmod 644 "/etc/systemd/system/rdio-vox.service"

# Update service file
echo -e "${YELLOW}Updating service file...${NC}"
cp "$INSTALL_DIR/rdio-vox.service" "/etc/systemd/system/"
systemctl daemon-reload

# Clean up
echo -e "${YELLOW}Cleaning up...${NC}"
rm -rf "$TEMP_DIR"

# Start service
echo -e "${YELLOW}Starting RDIO-VOX service...${NC}"
systemctl start rdio-vox

echo -e "${GREEN}Update completed successfully!${NC}"
echo ""
echo -e "${YELLOW}Update summary:${NC}"
echo "1. Previous installation backed up to: $BACKUP_DIR"
echo "2. New version installed to: $INSTALL_DIR"
echo "3. Configuration preserved at: $CONFIG_DIR/config.json"
echo "4. Python dependencies updated"
echo "5. Service restarted"
echo ""
echo -e "${YELLOW}To check service status:${NC}"
echo "  systemctl status rdio-vox"
echo ""
echo -e "${YELLOW}To view logs:${NC}"
echo "  journalctl -u rdio-vox -f"
echo ""
echo -e "${GREEN}RDIO-VOX has been updated!${NC}"
