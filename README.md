# RDIO-VOX - Audio Monitoring Service

**Version:** 1.0  
**Author:** John F. Gonzales

RDIO-VOX is a Linux service that monitors audio input and automatically sends recordings to an Rdio Scanner server when audio levels exceed a configured threshold (VOX - Voice Operated Exchange).

## Features

- **Real-time Audio Monitoring**: Continuously monitors audio input levels
- **VOX Detection**: Automatically triggers recording when audio exceeds threshold
- **Web Interface**: Modern, responsive web interface for configuration and monitoring
- **Audio Visualization**: Real-time audio level display with dB meter
- **Device Selection**: Choose from available audio input devices
- **Secure Configuration**: Password-protected web interface
- **Systemd Integration**: Runs as a proper Linux service
- **Automatic Upload**: Sends recordings to Rdio Scanner server via API

## Requirements

- Linux operating system
- Python 3.7 or higher
- Audio input device (microphone, line input, etc.)
- Network access to Rdio Scanner server
- Root privileges for installation

## Installation

### Quick Install

1. Download or clone the RDIO-VOX repository
2. Run the installation script as root:

```bash
sudo ./install.sh
```

### Manual Installation

1. **Install system dependencies**:

```bash
# Debian/Ubuntu
sudo apt-get update
sudo apt-get install python3-pip python3-dev portaudio19-dev libasound2-dev

# CentOS/RHEL
sudo yum install python3-pip python3-devel portaudio-devel alsa-lib-devel

# Arch Linux
sudo pacman -S python-pip portaudio alsa-lib
```

2. **Create service user**:

```bash
sudo useradd -r -s /bin/false -d /opt/rdio-vox rdio-vox
sudo usermod -a -G audio rdio-vox
```

3. **Install Python dependencies**:

```bash
# Create virtual environment
python3 -m venv /opt/rdio-vox/venv
source /opt/rdio-vox/venv/bin/activate
pip install -r requirements.txt
deactivate

# Set permissions
chown -R rdio-vox:audio /opt/rdio-vox/venv
```

4. **Copy files to installation directory**:

```bash
sudo mkdir -p /opt/rdio-vox
sudo cp -r * /opt/rdio-vox/
sudo chown -R rdio-vox:audio /opt/rdio-vox
```

5. **Install systemd service**:

```bash
sudo cp rdio-vox.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rdio-vox
```

## Configuration

### Initial Setup

1. **Edit configuration file**:

```bash
sudo nano /etc/rdio-vox/config.json
```

2. **Set basic configuration**:

```json
{
  "server_url": "https://your-rdio-scanner.com",
  "api_key": "your-api-key-here",
  "device_index": 0,
  "sample_rate": 44100,
  "channels": 1,
  "vox_threshold": 0.1,
  "frequency": "774031250",
  "source": "4424000",
  "system": "11",
  "system_label": "RSP25MTL",
  "talkgroup": "54241",
  "talkgroup_group": "Fire",
  "talkgroup_label": "TDB A1",
  "talkgroup_tag": "Fire dispatch",
  "web_password": "admin"
}
```

### Web Interface Configuration

1. **Start the service**:

```bash
sudo systemctl start rdio-vox
```

2. **Access web interface**:

Open your browser and navigate to: `http://localhost:8080`

3. **Login**:
   - Default password: `admin`
   - Change password in the web interface

4. **Configure settings**:
   - **Server Settings**: Set Rdio Scanner server URL and API key
   - **Audio Settings**: Select audio device, sample rate, channels, and VOX threshold
   - **Metadata**: Configure frequency, system, talkgroup information

## Usage

### Service Management

```bash
# Start service
sudo systemctl start rdio-vox

# Stop service
sudo systemctl stop rdio-vox

# Restart service
sudo systemctl restart rdio-vox

# Check status
sudo systemctl status rdio-vox

# View logs
journalctl -u rdio-vox -f
```

### Web Interface

The web interface provides:

- **Dashboard**: Real-time status and audio level monitoring
- **Control Panel**: Start/stop service, adjust VOX threshold
- **Audio Visualizer**: Real-time audio level display
- **Configuration**: Server, audio, and metadata settings
- **Device Selection**: Choose from available audio input devices

### Audio Level Monitoring

- **Real-time Display**: Shows current audio level in dB
- **VOX Threshold**: Adjustable threshold for triggering recordings
- **Visual Feedback**: Audio level visualization with threshold indicator
- **Automatic Recording**: Starts recording when threshold is exceeded
- **Automatic Upload**: Sends recordings to Rdio Scanner server

## Configuration Options

### Server Settings

- `server_url`: Rdio Scanner server URL
- `api_key`: API key for authentication

### Audio Settings

- `device_index`: Audio input device index
- `sample_rate`: Audio sample rate (Hz)
- `channels`: Number of audio channels (1=mono, 2=stereo)
- `vox_threshold`: VOX trigger threshold (0.0-1.0)

### Metadata Settings

- `frequency`: Radio frequency in Hz
- `source`: Unit/source ID
- `system`: System ID
- `system_label`: System label
- `talkgroup`: Talkgroup ID
- `talkgroup_group`: Talkgroup group
- `talkgroup_label`: Talkgroup label
- `talkgroup_tag`: Talkgroup tag

## Troubleshooting

### Common Issues

1. **No audio devices found**:
   - Check audio device connections
   - Verify user is in `audio` group
   - Check ALSA configuration

2. **Service won't start**:
   - Check logs: `journalctl -u rdio-vox`
   - Verify configuration file syntax
   - Check file permissions

3. **Upload failures**:
   - Verify server URL and API key
   - Check network connectivity
   - Review server logs

4. **Audio not detected**:
   - Adjust VOX threshold
   - Check audio input levels
   - Verify device selection

### Logs

- Service logs: `journalctl -u rdio-vox -f`
- Application logs: `/var/log/rdio-vox.log`
- System logs: `/var/log/syslog`

### Debug Mode

To run in debug mode:

```bash
sudo systemctl stop rdio-vox
cd /opt/rdio-vox
source venv/bin/activate
sudo -u rdio-vox python rdio_vox.py
```

## Security Considerations

- Change default password immediately
- Use HTTPS for web interface in production
- Restrict network access to web interface
- Regularly update dependencies
- Monitor logs for suspicious activity

## API Integration

RDIO-VOX integrates with Rdio Scanner using the `/api/call-upload` endpoint. The service automatically:

1. Monitors audio input levels
2. Triggers recording when VOX threshold is exceeded
3. Records audio in WAV format
4. Uploads recordings with metadata to Rdio Scanner
5. Cleans up temporary files

## Support

For issues and questions:

1. Check the troubleshooting section
2. Review logs for error messages
3. Verify configuration settings
4. Test audio device functionality
5. Check network connectivity

## License

This project is licensed under the MIT License. See LICENSE file for details.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Changelog

### Version 1.0.0
- Initial release
- Audio monitoring with VOX detection
- Web interface for configuration
- Rdio Scanner API integration
- Systemd service support
- Real-time audio visualization
