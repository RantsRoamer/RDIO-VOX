// RDIO-VOX Web Interface JavaScript
class RDIOVOXApp {
    constructor() {
        this.statusInterval = null;
        this.audioVisualizer = null;
        this.audioContext = null;
        this.analyser = null;
        this.dataArray = null;
        this.isVisualizing = false;

        this.init();
    }

    async init() {
        await this.loadConfig();
        await this.loadAudioDevices();
        this.setupEventListeners();
        this.startStatusUpdates();
        this.initAudioVisualizer();
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            const config = await response.json();

            // Populate form fields
            document.getElementById('server-url').value = config.server_url || '';
            document.getElementById('api-key').value = config.api_key || '';
            document.getElementById('audio-device').value = config.device_index || 0;
            document.getElementById('sample-rate').value = config.sample_rate || 44100;
            document.getElementById('channels').value = config.channels || 1;
            document.getElementById('vox-threshold-input').value = config.vox_threshold || 0.1;
            document.getElementById('frequency').value = config.frequency || '';
            document.getElementById('source').value = config.source || '';
            document.getElementById('system').value = config.system || '';
            document.getElementById('system-label').value = config.system_label || '';
            document.getElementById('talkgroup').value = config.talkgroup || '';
            document.getElementById('talkgroup-group').value = config.talkgroup_group || '';
            document.getElementById('talkgroup-label').value = config.talkgroup_label || '';
            document.getElementById('talkgroup-tag').value = config.talkgroup_tag || '';
            document.getElementById('web-port').value = config.web_port || 8080;

            // Update sliders
            document.getElementById('vox-slider').value = config.vox_threshold || 0.1;
            document.getElementById('vox-value').textContent = config.vox_threshold || 0.1;
            document.getElementById('vox-threshold').textContent = config.vox_threshold || 0.1;
            
            document.getElementById('gain-slider').value = config.input_gain || 0.5;
            document.getElementById('gain-value').textContent = config.input_gain || 0.5;

            // Set auto-start checkbox
            document.getElementById('auto-start').checked = config.auto_start || false;

            // If auto-start is enabled, start the service
            if (config.auto_start) {
                await this.startService();
            }

        } catch (error) {
            console.error('Error loading config:', error);
            this.showToast('Error loading configuration', 'error');
        }
    }

    async loadAudioDevices() {
        try {
            const response = await fetch('/api/devices');
            const devices = await response.json();

            const select = document.getElementById('audio-device');
            select.innerHTML = '';

            devices.forEach(device => {
                const option = document.createElement('option');
                option.value = device.index;
                option.textContent = `${device.name} (${device.channels} ch, ${device.sample_rate} Hz)`;
                select.appendChild(option);
            });

        } catch (error) {
            console.error('Error loading audio devices:', error);
        }
    }

    setupEventListeners() {
        // VOX slider
        document.getElementById('vox-slider').addEventListener('input', (e) => {
            const value = parseFloat(e.target.value);
            document.getElementById('vox-value').textContent = value.toFixed(2);
            document.getElementById('vox-threshold').textContent = value.toFixed(2);
            document.getElementById('vox-threshold-input').value = value;
        });

        // Gain slider
        document.getElementById('gain-slider').addEventListener('input', (e) => {
            const value = parseFloat(e.target.value);
            document.getElementById('gain-value').textContent = value.toFixed(1);
        });

        // Auto-start checkbox
        document.getElementById('auto-start').addEventListener('change', async (e) => {
            const config = {
                auto_start: e.target.checked
            };
            await this.saveConfig(config);
        });

        // Form submissions
        document.getElementById('server-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveServerConfig();
        });

        document.getElementById('audio-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveAudioConfig();
        });

        document.getElementById('metadata-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveMetadataConfig();
        });

        document.getElementById('settings-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.changePassword();
        });
    }

    async saveServerConfig() {
        const config = {
            server_url: document.getElementById('server-url').value,
            api_key: document.getElementById('api-key').value
        };

        await this.saveConfig(config);
    }

    async saveAudioConfig() {
        const config = {
            device_index: parseInt(document.getElementById('audio-device').value),
            sample_rate: parseInt(document.getElementById('sample-rate').value),
            channels: parseInt(document.getElementById('channels').value),
            vox_threshold: parseFloat(document.getElementById('vox-threshold-input').value),
            input_gain: parseFloat(document.getElementById('gain-slider').value)
        };

        await this.saveConfig(config);
    }

    async saveMetadataConfig() {
        const config = {
            frequency: document.getElementById('frequency').value,
            source: document.getElementById('source').value,
            system: document.getElementById('system').value,
            system_label: document.getElementById('system-label').value,
            talkgroup: document.getElementById('talkgroup').value,
            talkgroup_group: document.getElementById('talkgroup-group').value,
            talkgroup_label: document.getElementById('talkgroup-label').value,
            talkgroup_tag: document.getElementById('talkgroup-tag').value
        };

        await this.saveConfig(config);
    }

    async changePassword() {
        const currentPassword = document.getElementById('current-password').value;
        const newPassword = document.getElementById('new-password').value;
        const confirmPassword = document.getElementById('confirm-password').value;
        const webPort = document.getElementById('web-port').value;

        // Validate password input
        if (currentPassword && newPassword && confirmPassword) {
            if (newPassword !== confirmPassword) {
                this.showToast('New passwords do not match', 'error');
                return;
            }
            
            if (newPassword.length < 6) {
                this.showToast('Password must be at least 6 characters long', 'error');
                return;
            }
        }

        try {
            // Use the main config endpoint for consistency
            const config = {};
            
            // Add password if provided
            if (currentPassword && newPassword && confirmPassword) {
                config.web_password = newPassword;
            }
            
            // Add web port if provided
            if (webPort) {
                const port = parseInt(webPort);
                if (port < 1024 || port > 65535) {
                    this.showToast('Port must be between 1024 and 65535', 'error');
                    return;
                }
                config.web_port = port;
            }

            const response = await fetch('/api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });

            if (response.ok) {
                this.showToast('Settings saved successfully', 'success');

                // Show restart warning if port changed
                if (webPort) {
                    setTimeout(() => {
                        this.showToast('Please restart the service for port changes to take effect', 'warning');
                    }, 2000);
                }

                // Clear password fields
                document.getElementById('current-password').value = '';
                document.getElementById('new-password').value = '';
                document.getElementById('confirm-password').value = '';
            } else {
                const result = await response.json();
                this.showToast(result.message || 'Error saving settings', 'error');
            }
        } catch (error) {
            console.error('Error changing settings:', error);
            this.showToast('Error changing settings', 'error');
        }
    }

    async saveConfig(config) {
        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });

            if (response.ok) {
                this.showToast('Configuration saved successfully', 'success');
            } else {
                throw new Error('Failed to save configuration');
            }
        } catch (error) {
            console.error('Error saving config:', error);
            this.showToast('Error saving configuration', 'error');
        }
    }

    async startService() {
        try {
            const response = await fetch('/api/control', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ action: 'start' })
            });

            if (response.ok) {
                this.showToast('Service started', 'success');
                this.updateControlButtons(true);
            } else {
                throw new Error('Failed to start service');
            }
        } catch (error) {
            console.error('Error starting service:', error);
            this.showToast('Error starting service', 'error');
        }
    }

    async stopService() {
        try {
            const response = await fetch('/api/control', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ action: 'stop' })
            });

            if (response.ok) {
                this.showToast('Service stopped', 'success');
                this.updateControlButtons(false);
            } else {
                throw new Error('Failed to stop service');
            }
        } catch (error) {
            console.error('Error stopping service:', error);
            this.showToast('Error stopping service', 'error');
        }
    }

    async updateStatus() {
        try {
            const response = await fetch('/api/status');
            const status = await response.json();

            // Update status indicators
            const serviceStatus = document.getElementById('service-status');
            const recordingStatus = document.getElementById('recording-status');
            const audioLevel = document.getElementById('audio-level');

            serviceStatus.textContent = status.monitoring ? 'Running' : 'Stopped';
            serviceStatus.className = `badge ${status.monitoring ? 'bg-success' : 'bg-secondary'}`;

            recordingStatus.textContent = status.recording ? 'Yes' : 'No';
            recordingStatus.className = `badge ${status.recording ? 'bg-warning' : 'bg-secondary'}`;

            audioLevel.textContent = `${status.db_level.toFixed(1)} dB`;

            // Update control buttons
            this.updateControlButtons(status.monitoring);

            // Update visualizer
            this.updateVisualizer(status.level, status.db_level);

        } catch (error) {
            console.error('Error updating status:', error);
        }
    }

    updateControlButtons(isRunning) {
        const startBtn = document.getElementById('start-btn');
        const stopBtn = document.getElementById('stop-btn');

        startBtn.disabled = isRunning;
        stopBtn.disabled = !isRunning;

        startBtn.className = `btn ${isRunning ? 'btn-outline-success' : 'btn-success'} me-2`;
        stopBtn.className = `btn ${isRunning ? 'btn-danger' : 'btn-outline-danger'}`;
    }

    initAudioVisualizer() {
        const canvas = document.getElementById('audio-visualizer');
        this.audioVisualizer = canvas.getContext('2d');

        // Set canvas size
        canvas.width = canvas.offsetWidth;
        canvas.height = canvas.offsetHeight;

        // Initialize visualizer data
        this.visualizerData = new Array(100).fill(0);
    }

    updateVisualizer(level, dbLevel) {
        if (!this.audioVisualizer) return;

        const canvas = document.getElementById('audio-visualizer');
        const ctx = this.audioVisualizer;

        // Shift data
        this.visualizerData.shift();
        this.visualizerData.push(level);

        // Clear canvas
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Draw grid
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 10; i++) {
            const y = (canvas.height / 10) * i;
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(canvas.width, y);
            ctx.stroke();
        }

        // Draw audio level
        ctx.strokeStyle = '#0d6efd';
        ctx.lineWidth = 2;
        ctx.beginPath();

        const stepX = canvas.width / this.visualizerData.length;
        for (let i = 0; i < this.visualizerData.length; i++) {
            const x = i * stepX;
            const y = canvas.height - (this.visualizerData[i] * canvas.height);

            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        }
        ctx.stroke();

        // Draw threshold line
        const threshold = parseFloat(document.getElementById('vox-slider').value);
        const thresholdY = canvas.height - (threshold * canvas.height);

        ctx.strokeStyle = '#ffc107';
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.moveTo(0, thresholdY);
        ctx.lineTo(canvas.width, thresholdY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Draw dB level text
        ctx.fillStyle = '#fff';
        ctx.font = '14px monospace';
        ctx.fillText(`${dbLevel.toFixed(1)} dB`, 10, 20);
        ctx.fillText(`Threshold: ${threshold.toFixed(2)}`, 10, 40);
    }

    startStatusUpdates() {
        this.statusInterval = setInterval(() => {
            this.updateStatus();
        }, 100);
    }

    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        const toastBody = document.getElementById('toast-body');

        toastBody.textContent = message;

        // Set toast color based on type
        toast.className = `toast ${type === 'error' ? 'bg-danger' : type === 'success' ? 'bg-success' : 'bg-info'} text-white`;

        // Show toast
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();
    }
}

// Global functions for button clicks
function startService() {
    app.startService();
}

function stopService() {
    app.stopService();
}

function logout() {
    window.location.href = '/logout';
}

// Initialize app when DOM is loaded
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new RDIOVOXApp();
});
