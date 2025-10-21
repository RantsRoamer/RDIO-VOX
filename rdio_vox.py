#!/usr/bin/env python3
"""
RDIO-VOX - Audio monitoring service for Rdio Scanner
A Linux service that monitors audio input and sends recordings to Rdio Scanner server

Version: 1.0
Author: John F. Gonzales
"""

import os
import sys
import json
import time
import threading
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import pyaudio
import sounddevice as sd
import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from pydub import AudioSegment
import io

# Version information
VERSION = "1.0"
AUTHOR = "John F. Gonzales"

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/rdio-vox.log'),
        logging.StreamHandler()
    ]
)

# Set Werkzeug (Flask's web server) logging to WARNING level to suppress access logs
logging.getLogger('werkzeug').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

class AudioMonitor:
    """Audio monitoring and recording class"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.is_monitoring = False
        self.is_recording = False
        self.audio_data = []
        self.current_level = 0.0
        self.recording_thread = None
        self.monitoring_thread = None
        self.pyaudio_instance = None
        self.stream = None
        self.recording_start_time = None
        self.min_recording_duration = 1.0  # Minimum recording duration in seconds
        
    def get_audio_devices(self) -> List[Dict]:
        """Get list of available audio devices"""
        devices = []
        try:
            p = pyaudio.PyAudio()
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:
                    devices.append({
                        'index': i,
                        'name': info['name'],
                        'channels': info['maxInputChannels'],
                        'sample_rate': info['defaultSampleRate']
                    })
            p.terminate()
        except Exception as e:
            logger.error(f"Error getting audio devices: {e}")
        return devices
    
    def start_monitoring(self):
        """Start audio monitoring"""
        if self.is_monitoring:
            return
        
        # Test server connection first
        logger.info("Testing server connection...")
        if not self._test_server_connection():
            logger.warning("Server connection test failed - uploads may not work")
        else:
            logger.info("Server connection test passed")
            
        self.is_monitoring = True
        self.monitoring_thread = threading.Thread(target=self._monitor_audio)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        logger.info("Audio monitoring started")
    
    def stop_monitoring(self):
        """Stop audio monitoring"""
        self.is_monitoring = False
        if self.monitoring_thread:
            self.monitoring_thread.join()
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.pyaudio_instance:
            self.pyaudio_instance.terminate()
        logger.info("Audio monitoring stopped")
    
    def _monitor_audio(self):
        """Monitor audio levels and trigger recording"""
        try:
            self.pyaudio_instance = pyaudio.PyAudio()
            
            # Audio parameters
            chunk_size = 1024
            sample_rate = int(self.config.get('sample_rate', 44100))
            channels = int(self.config.get('channels', 1))
            device_index = int(self.config.get('device_index', 0))
            vox_threshold = float(self.config.get('vox_threshold', 0.1))
            
            logger.info(f"Audio recording parameters:")
            logger.info(f"  Sample rate: {sample_rate} Hz")
            logger.info(f"  Channels: {channels}")
            logger.info(f"  Device index: {device_index}")
            logger.info(f"  VOX threshold: {vox_threshold}")
            
            # Store the sample rate being used
            self.actual_sample_rate = sample_rate
            logger.info(f"PyAudio stream created with sample rate: {sample_rate} Hz")
            
            # Apply input gain reduction to prevent clipping
            input_gain = 0.5  # Reduce input level by half
            
            def input_callback(in_data, frame_count, time_info, status):
                # Convert input data to numpy array
                data = np.frombuffer(in_data, dtype=np.float32)
                # Apply gain reduction
                data = data * input_gain
                return (data.tobytes(), pyaudio.paContinue)
            
            self.stream = self.pyaudio_instance.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=chunk_size,
                stream_callback=input_callback
            )
            
            logger.info(f"Monitoring audio: device={device_index}, rate={sample_rate}, channels={channels}")
            
            while self.is_monitoring:
                try:
                    # With callback mode, we just need to check levels
                    try:
                        # Get latest audio data from callback
                        data = self.stream.read(chunk_size, exception_on_overflow=False)
                        audio_array = np.frombuffer(data, dtype=np.float32)
                        
                        # Calculate RMS level for VOX
                        rms = np.sqrt(np.mean(audio_array**2))
                        self.current_level = rms
                        
                        # Store audio data if recording
                        if self.is_recording:
                            self.audio_data.append(data)
                            # Log peak level periodically
                            if len(self.audio_data) % 10 == 0:
                                peak = np.max(np.abs(audio_array))
                                rms = np.sqrt(np.mean(audio_array**2))
                                logger.info(f"Recording levels - peak: {peak:.4f}, RMS: {rms:.4f}")
                    except Exception as e:
                        logger.error(f"Error processing audio: {e}")
                    
                    # Calculate RMS level
                    rms = np.sqrt(np.mean(audio_array**2))
                    self.current_level = rms
                    
                    # Convert to dB
                    if rms > 0:
                        db_level = 20 * np.log10(rms)
                    else:
                        db_level = -100
                    
                    # Check VOX threshold with hysteresis
                    if not self.is_recording:
                        # Higher threshold to start recording (avoid false triggers)
                        if rms > vox_threshold * 1.2:  # 20% higher threshold to start
                            logger.info(f"VOX triggered: {rms:.4f} > {vox_threshold * 1.2:.4f}")
                            self._start_recording()
                    else:
                        # Lower threshold to maintain recording (prevent choppy audio)
                        if rms < vox_threshold * 0.4:  # 60% lower threshold to stop
                            self._stop_recording()
                        
                except Exception as e:
                    logger.error(f"Error in audio monitoring: {e}")
                    # If stream is closed, try to restart monitoring
                    if "Stream closed" in str(e) or "Unanticipated host error" in str(e):
                        logger.info("Audio stream closed, stopping monitoring")
                        self.is_monitoring = False
                        break
                    time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Error starting audio monitoring: {e}")
        finally:
            if hasattr(self, 'stream') and self.stream:
                self.stream.close()
            if hasattr(self, 'pyaudio_instance') and self.pyaudio_instance:
                self.pyaudio_instance.terminate()
    
    def _start_recording(self):
        """Start recording audio"""
        if self.is_recording:
            return
            
        self.is_recording = True
        self.audio_data = []
        self.recording_start_time = time.time()
        self.recording_thread = threading.Thread(target=self._record_audio)
        self.recording_thread.daemon = True
        self.recording_thread.start()
        logger.info("Recording started")
    
    def _stop_recording(self):
        """Stop recording and upload audio"""
        if not self.is_recording:
            return
            
        # Check if minimum duration has elapsed
        if self.recording_start_time and time.time() - self.recording_start_time < self.min_recording_duration:
            logger.info(f"Recording too short (< {self.min_recording_duration}s), discarding")
            self.is_recording = False
            self.audio_data = []
            if self.recording_thread:
                self.recording_thread.join()
            return
            
        self.is_recording = False
        if self.recording_thread:
            self.recording_thread.join()
        
        if self.audio_data:
            self._upload_audio()
        
        logger.info("Recording stopped")
    
    def _record_audio(self):
        """Record audio data - data is collected in the monitoring loop"""
        # The recording data is collected in the monitoring loop
        # This function just waits for recording to finish
        while self.is_recording:
            time.sleep(0.1)
    
    def _upload_audio(self):
        """Upload recorded audio to Rdio Scanner server - using pi2rdio.pl method"""
        try:
            # Safety check - don't upload if no data
            if not self.audio_data:
                logger.warning("No audio data to upload")
                return
                
            # Convert audio data to numpy array (matching pi2rdio.pl method)
            if not self.audio_data:
                logger.error("No audio data to process")
                return
                
            audio_bytes = b''.join(self.audio_data)
            # Verify we have enough audio data
            min_bytes = 1024 * 4  # At least 1024 samples
            if len(audio_bytes) < min_bytes:
                logger.error(f"Audio data too short: {len(audio_bytes)} bytes")
                return
                
            logger.info(f"Processing {len(audio_bytes)} bytes of audio data")
            
            # Clear audio data immediately to prevent any chance of re-upload
            self.audio_data = []
            
            audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
            
            # Verify audio data isn't silent or corrupted
            peak = np.max(np.abs(audio_array))
            mean = np.mean(np.abs(audio_array))
            if peak < 0.001:
                logger.error(f"Audio data appears to be silent: peak={peak:.6f}, mean={mean:.6f}")
                return
            logger.info(f"Audio data verified: peak={peak:.4f}, mean={mean:.4f}")
            
            # Log original audio stats
            logger.info(f"Original audio - min: {np.min(audio_array):.4f}, max: {np.max(audio_array):.4f}, mean: {np.mean(np.abs(audio_array)):.4f}")
            
            # Check if audio is too quiet
            if np.max(np.abs(audio_array)) < 0.01:
                logger.warning("Audio levels very low, applying gain")
                gain = 1.0 / np.max(np.abs(audio_array)) if np.max(np.abs(audio_array)) > 0 else 1.0
                audio_array = audio_array * min(gain, 100.0)  # Limit gain to 100x
            
            # Normalize to [-1.0, 1.0] range
            max_val = np.max(np.abs(audio_array))
            if max_val > 0:
                audio_array = audio_array / max_val
            
            # Log normalized audio stats
            logger.info(f"Normalized audio - min: {np.min(audio_array):.4f}, max: {np.max(audio_array):.4f}, mean: {np.mean(np.abs(audio_array)):.4f}")
            
            # Scale to 16-bit range
            audio_16bit = (audio_array * 32767).astype(np.int16)
            
            # Create temporary WAV file in memory
            timestamp = datetime.now().isoformat()
            filename = f'audio_{timestamp}.m4a'
            filepath = f"/tmp/{filename}"
            
            # Get audio parameters
            actual_sample_rate = getattr(self, 'actual_sample_rate', int(self.config.get('sample_rate', 44100)))
            channels = int(self.config.get('channels', 1))
            
            # Create WAV in memory first
            wav_io = io.BytesIO()
            import wave
            try:
                with wave.open(wav_io, 'wb') as wav_file:
                    wav_file.setnchannels(channels)
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(actual_sample_rate)
                    audio_bytes = audio_16bit.tobytes()
                    if len(audio_bytes) == 0:
                        logger.error("No audio data to write to WAV")
                        return
                    wav_file.writeframes(audio_bytes)
                    logger.info(f"WAV file created: {wav_file.getnframes()} frames, {channels} channels, {actual_sample_rate} Hz")
            except Exception as e:
                logger.error(f"Error creating WAV file: {e}")
                return
            
            # Log WAV file stats
            wav_io.seek(0)
            with wave.open(wav_io, 'rb') as wav_check:
                wav_frames = wav_check.readframes(wav_check.getnframes())
                wav_array = np.frombuffer(wav_frames, dtype=np.int16)
                logger.info(f"WAV file stats - min: {np.min(wav_array)}, max: {np.max(wav_array)}, mean: {np.mean(np.abs(wav_array)):.2f}")
            
            # Convert to M4A (AAC)
            wav_io.seek(0)
            audio = AudioSegment.from_wav(wav_io)
            
            # Log audio segment stats
            logger.info(f"AudioSegment stats - duration: {len(audio)/1000.0:.2f}s, channels: {audio.channels}, sample_width: {audio.sample_width}, frame_rate: {audio.frame_rate}")
            
            # Save original WAV for debugging
            debug_wav = "/tmp/debug_audio.wav"
            audio.export(debug_wav, format="wav")
            logger.info(f"Saved debug WAV file: {debug_wav}")
            
            # Create MP3 file instead of M4A
            # Create clean timestamp without colons or dots
            now = datetime.now()
            timestamp = now.strftime('%Y%m%d_%H%M%S_%f')[:17]  # Limit microseconds to 3 digits
            filename = f'audio_{timestamp}.mp3'
            filepath = f"/tmp/{filename}"
            
            try:
                import subprocess
                # First analyze audio levels
                analyze_cmd = [
                    "ffmpeg",
                    "-i", debug_wav,
                    "-af", "loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json",
                    "-f", "null",
                    "-"
                ]
                result = subprocess.run(analyze_cmd, capture_output=True, text=True)
                logger.info(f"Audio analysis: {result.stderr}")

                # Then normalize audio with measured values
                norm_wav = "/tmp/norm_audio.wav"
                norm_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", debug_wav,
                    "-af", "compand=attacks=0.02:decays=0.05:points=-80/-80|-50/-10|0/0|20/20,loudnorm=I=-16:LRA=11:TP=-1.5,volume=3.0",  # Compression, normalization and boost
                    norm_wav
                ]
                subprocess.run(norm_cmd, check=True, capture_output=True)
                logger.info("Audio normalization successful")

                # Verify normalized audio
                verify_cmd = ["ffprobe", "-v", "error", "-show_streams", "-of", "json", norm_wav]
                verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
                logger.info(f"Normalized audio info: {verify_result.stdout}")
                
                # Then convert to MP3 with forced mono and resampling
                mp3_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", norm_wav,
                    "-codec:a", "libmp3lame",
                    "-qscale:a", "0",  # Highest quality VBR
                    "-ar", str(actual_sample_rate),
                    "-ac", "1",  # Force mono
                    "-af", "aresample=resampler=soxr:precision=28:osf=s16,volume=3.0",  # High quality resampling and boost
                    "-write_xing", "0",  # Disable VBR header for better compatibility
                    "-id3v2_version", "3",  # Use ID3v2.3 for better compatibility
                    filepath
                ]
                subprocess.run(mp3_cmd, check=True, capture_output=True)
                logger.info("MP3 conversion successful")
                
                # Verify the MP3 file
                check_cmd = ["ffmpeg", "-v", "error", "-i", filepath, "-f", "null", "-"]
                try:
                    subprocess.run(check_cmd, check=True, capture_output=True)
                    logger.info("MP3 file verification successful")
                except subprocess.CalledProcessError as e:
                    logger.error(f"MP3 file verification failed: {e.stderr.decode()}")
                    return
                subprocess.run(mp3_cmd, check=True, capture_output=True)
                logger.info("MP3 conversion successful")
                
                # Verify the output file
                file_info_cmd = ["ffprobe", "-v", "error", "-show_format", "-show_streams", filepath]
                result = subprocess.run(file_info_cmd, capture_output=True, text=True)
                logger.info(f"Output file info: {result.stdout}")
                
            except Exception as e:
                logger.error(f"FFmpeg processing failed: {e}")
                # Fallback to direct MP3 export
                audio.export(filepath, format='mp3', parameters=["-q:a", "0"])
            finally:
                # Clean up temporary files
                try:
                    os.remove(norm_wav)
                except:
                    pass
            
            logger.info(f'Audio saved as MP3: {filepath} (sample rate: {actual_sample_rate} Hz, channels: {channels})')
            
            # Upload to server using exact same method as pi2rdio.pl
            self._send_to_server(filepath, filename)
            
            # Clean up
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"Error uploading audio: {e}")
    
    def _test_small_upload(self):
        """Test upload with a very small file to check if it's a size issue"""
        try:
            server_url = self.config.get('server_url')
            api_key = self.config.get('api_key')
            
            # Create a tiny test file
            test_filepath = "/tmp/tiny_test.mp3"
            test_filename = "tiny_test.mp3"
            
            # Create minimal WAV in memory first
            wav_io = io.BytesIO()
            import wave
            with wave.open(wav_io, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(44100)
                wav_file.writeframes(b'\x00\x00' * 100)  # 200 bytes of silence
            
            # Convert to MP3
            wav_io.seek(0)
            audio = AudioSegment.from_wav(wav_io)
            audio.export(test_filepath, format='ipod', parameters=["-c:a", "aac", "-b:a", "192k"])  # High quality AAC
            
            logger.info(f"Testing with tiny file: {os.path.getsize(test_filepath)} bytes")
            
            # Test with actual configured values
            logger.info("Testing with configured values...")
            files_pi2rdio = {
                'audio': open(test_filepath, 'rb'),
                'audioName': (None, test_filename),
                'audioType': (None, 'audio/mpeg'),
                'dateTime': (None, datetime.now().isoformat()),
                'frequencies': (None, json.dumps([])),
                'frequency': (None, self.config.get('frequency', '')),
                'key': (None, api_key),
                'patches': (None, json.dumps([])),
                'source': (None, self.config.get('source', '')),
                'sources': (None, json.dumps([])),
                'system': (None, self.config.get('system', '')),
                'systemLabel': (None, self.config.get('system_label', '')),
                'talkgroup': (None, self.config.get('talkgroup', '')),
                'talkgroupGroup': (None, self.config.get('talkgroup_group', '')),
                'talkgroupLabel': (None, self.config.get('talkgroup_label', '')),
                'talkgroupTag': (None, self.config.get('talkgroup_tag', ''))
            }
            
            response = requests.post(f"{server_url}/api/call-upload", files=files_pi2rdio, timeout=10)
            logger.info(f"pi2rdio.pl format test - Status: {response.status_code}")
            logger.info(f"pi2rdio.pl format test - Response: {response.text}")
            
            files_pi2rdio['audio'].close()
            
            # Test with minimal required fields
            logger.info("Testing with minimal required fields...")
            files_minimal = {
                'audio': open(test_filepath, 'rb'),
                'key': (None, api_key),
                'system': (None, self.config.get('system', '')),
                'talkgroup': (None, self.config.get('talkgroup', ''))
            }
            
            response = requests.post(f"{server_url}/api/call-upload", files=files_minimal, timeout=10)
            logger.info(f"Minimal fields test - Status: {response.status_code}")
            logger.info(f"Minimal fields test - Response: {response.text}")
            
            files_minimal['audio'].close()
            os.remove(test_filepath)
            
        except Exception as e:
            logger.error(f"Tiny file test failed: {e}")
    
    def _test_server_connection(self):
        """Test server connection and API key validity"""
        try:
            server_url = self.config.get('server_url')
            api_key = self.config.get('api_key')
            
            if not server_url or not api_key:
                logger.error("Server URL or API key not configured")
                return False
            
            # Test with actual configuration
            test_files = {
                'audio': ('test.wav', b'test audio data', 'audio/mpeg'),
                'audioName': (None, 'test.wav'),
                'audioType': (None, 'audio/mpeg'),
                'dateTime': (None, datetime.now().isoformat()),
                'frequencies': (None, json.dumps([])),
                'frequency': (None, self.config.get('frequency', '')),
                'key': (None, api_key),
                'patches': (None, json.dumps([])),
                'source': (None, self.config.get('source', '')),
                'sources': (None, json.dumps([])),
                'system': (None, self.config.get('system', '')),
                'systemLabel': (None, self.config.get('system_label', '')),
                'talkgroup': (None, self.config.get('talkgroup', '')),
                'talkgroupGroup': (None, self.config.get('talkgroup_group', '')),
                'talkgroupLabel': (None, self.config.get('talkgroup_label', '')),
                'talkgroupTag': (None, self.config.get('talkgroup_tag', ''))
            }
            
            logger.info(f"Testing server connection to {server_url}")
            logger.info(f"Test API Key: {api_key[:10]}...")
            
            response = requests.post(f"{server_url}/api/call-upload", files=test_files, timeout=10)
            
            logger.info(f"Test response status: {response.status_code}")
            logger.info(f"Test response headers: {dict(response.headers)}")
            logger.info(f"Test response: {response.text}")
            
            return response.status_code != 400  # 400 means "unknown request" (bad API key)
            
        except Exception as e:
            logger.error(f"Server connection test failed: {e}")
            logger.error(f"Test error details: {type(e).__name__}: {str(e)}")
            return False

    def _send_to_server(self, filepath: str, filename: str):
        """Send audio file to Rdio Scanner server"""
        try:
            server_url = self.config.get('server_url')
            api_key = self.config.get('api_key')
            
            if not server_url or not api_key:
                logger.error("Server URL or API key not configured")
                return
            
            # Prepare form data using the working format from pi2rdio.pl
            files = {
                'audio': open(filepath, 'rb'),
                'audioName': (None, filename),
                'audioType': (None, 'audio/mpeg'),
                'dateTime': (None, datetime.now().isoformat()),
                'frequencies': (None, json.dumps([])),
                'frequency': (None, self.config.get('frequency', '')),
                'key': (None, api_key),
                'patches': (None, json.dumps([])),
                'source': (None, self.config.get('source', '')),
                'sources': (None, json.dumps([])),
                'system': (None, self.config.get('system', '')),
                'systemLabel': (None, self.config.get('system_label', '')),
                'talkgroup': (None, self.config.get('talkgroup', '')),
                'talkgroupGroup': (None, self.config.get('talkgroup_group', '')),
                'talkgroupLabel': (None, self.config.get('talkgroup_label', '')),
                'talkgroupTag': (None, self.config.get('talkgroup_tag', ''))
            }
            
            # Send request with detailed debugging
            logger.info(f"Uploading audio to {server_url}/api/call-upload")
            logger.info(f"File: {filename}, Size: {os.path.getsize(filepath)} bytes")
            logger.info(f"API Key: {api_key[:10]}...")
            logger.info(f"Form data keys: {list(files.keys())}")
            
            # Log all form data values (except the file content)
            for key, value in files.items():
                if key != 'audio':
                    logger.info(f"  {key}: {value}")
            
            # Add request debugging
            logger.info(f"Request URL: {server_url}/api/call-upload")
            logger.info(f"Request timeout: 30 seconds")
            
            # Try with different timeout and connection settings
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'RDIO-VOX/1.0',
                'Accept': '*/*',
                'Connection': 'keep-alive'
            })
            
            # Log the exact request being sent
            prepared_request = session.prepare_request(
                requests.Request('POST', f"{server_url}/api/call-upload", files=files)
            )
            logger.info(f"Prepared request URL: {prepared_request.url}")
            logger.info(f"Prepared request headers: {dict(prepared_request.headers)}")
            
            # Log the raw request body (first 1000 chars)
            if hasattr(prepared_request, 'body') and prepared_request.body:
                body_preview = prepared_request.body[:1000] if isinstance(prepared_request.body, (str, bytes)) else str(prepared_request.body)[:1000]
                logger.info(f"Request body preview: {body_preview}")
            
            # Send with detailed error handling
            try:
                response = session.send(prepared_request, timeout=30, stream=False)
                logger.info(f"Response received successfully")
                logger.info(f"Response status: {response.status_code}")
                logger.info(f"Response headers: {dict(response.headers)}")
                logger.info(f"Response content length: {len(response.content)}")
                logger.info(f"Response content: {response.text[:500]}...")  # First 500 chars
                
            except requests.exceptions.ChunkedEncodingError as e:
                logger.error(f"ChunkedEncodingError details: {e}")
                logger.error(f"Server cut off connection during upload")
                # Try to get partial response if available
                if hasattr(e, 'response') and e.response:
                    logger.error(f"Partial response status: {e.response.status_code}")
                    logger.error(f"Partial response headers: {dict(e.response.headers)}")
                raise
            except requests.exceptions.ConnectionError as e:
                logger.error(f"ConnectionError details: {e}")
                raise
            except requests.exceptions.Timeout as e:
                logger.error(f"Timeout details: {e}")
                raise
            
            if response.status_code == 200:
                logger.info(f"Audio uploaded successfully: {filename}")
            else:
                logger.error(f"Upload failed: {response.status_code} - {response.text}")
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error sending to server: {e}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout error sending to server: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error sending to server: {e}")
            logger.error(f"Request error details: {type(e).__name__}: {str(e)}")
        except Exception as e:
            logger.error(f"Error sending to server: {e}")
            logger.error(f"Error details: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            if 'audio' in files:
                files['audio'].close()

class ConfigManager:
    """Configuration management"""
    
    def __init__(self, config_file: str = "/etc/rdio-vox/config.json"):
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load configuration from file"""
        default_config = {
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
            'web_port': 8080,
            'auto_start': False
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults
                    for key, value in default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            else:
                # Only set default password for new installations
                config = default_config.copy()
                config['web_password_hash'] = generate_password_hash('admin')
                return config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            # If there's an error, return defaults with default password
            config = default_config.copy()
            config['web_password_hash'] = generate_password_hash('admin')
            return config
    
    def save_config(self, config: Dict):
        """Save configuration to file"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            self.config = config
            logger.info("Configuration saved")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def get_config(self) -> Dict:
        """Get current configuration"""
        # Reload from file to get current state
        return self._load_config()

# Global instances
config_manager = ConfigManager()
audio_monitor = AudioMonitor(config_manager.get_config())

# Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

def login_required(f):
    """Decorator for login required routes"""
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/')
@login_required
def index():
    """Main dashboard"""
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        password = request.form['password']
        config = config_manager.get_config()
        
        if check_password_hash(config.get('web_password_hash', ''), password):
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout"""
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/api/config', methods=['GET', 'POST'])
@login_required
def api_config():
    """Configuration API"""
    if request.method == 'GET':
        config = config_manager.get_config()
        # Remove sensitive data
        config.pop('web_password_hash', None)
        return jsonify(config)
    
    elif request.method == 'POST':
        new_config = request.json
        # Get current config and merge with new values
        current_config = config_manager.get_config()
        current_config.update(new_config)
        
        # Hash password if provided
        if 'web_password' in current_config and current_config['web_password']:
            current_config['web_password_hash'] = generate_password_hash(current_config['web_password'])
            current_config.pop('web_password', None)
        
        config_manager.save_config(current_config)
        audio_monitor.config = config_manager.get_config()
        return jsonify({'status': 'success'})

@app.route('/api/devices')
@login_required
def api_devices():
    """Get available audio devices"""
    devices = audio_monitor.get_audio_devices()
    return jsonify(devices)

@app.route('/api/status')
@login_required
def api_status():
    """Get service status"""
    return jsonify({
        'monitoring': audio_monitor.is_monitoring,
        'recording': audio_monitor.is_recording,
        'level': float(audio_monitor.current_level),
        'db_level': float(20 * np.log10(audio_monitor.current_level)) if audio_monitor.current_level > 0 else -100
    })

@app.route('/api/version')
@login_required
def api_version():
    """Get version information"""
    return jsonify({
        'version': VERSION,
        'author': AUTHOR,
        'name': 'RDIO-VOX'
    })

@app.route('/api/control', methods=['POST'])
@login_required
def api_control():
    """Control service"""
    action = request.json.get('action')
    
    if action == 'start':
        audio_monitor.start_monitoring()
    elif action == 'stop':
        audio_monitor.stop_monitoring()
    
    return jsonify({'status': 'success'})

@app.route('/api/change-settings', methods=['POST'])
@login_required
def api_change_settings():
    """Change web interface settings (password and port)"""
    try:
        data = request.json
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        web_port = data.get('web_port')
        
        # Get current config
        config = config_manager.get_config()
        changes_made = []
        
        # Handle password change if provided
        if current_password and new_password and confirm_password:
            # Validate password input
            if new_password != confirm_password:
                return jsonify({'status': 'error', 'message': 'New passwords do not match'}), 400
            
            if len(new_password) < 6:
                return jsonify({'status': 'error', 'message': 'Password must be at least 6 characters long'}), 400
            
            current_hash = config.get('web_password_hash', '')
            
            # Verify current password
            if not check_password_hash(current_hash, current_password):
                return jsonify({'status': 'error', 'message': 'Current password is incorrect'}), 400
            
            # Update password
            config['web_password_hash'] = generate_password_hash(new_password)
            changes_made.append('password')
            logger.info("Web interface password changed")
        
        # Handle port change if provided
        if web_port is not None:
            try:
                port = int(web_port)
                if port < 1024 or port > 65535:
                    return jsonify({'status': 'error', 'message': 'Port must be between 1024 and 65535'}), 400
                
                config['web_port'] = port
                changes_made.append('port')
                logger.info(f"Web server port changed to {port}")
            except ValueError:
                return jsonify({'status': 'error', 'message': 'Invalid port number'}), 400
        
        # Save config if changes were made
        if changes_made:
            config_manager.save_config(config)
            
            # Check if port changed and warn about restart
            if 'port' in changes_made:
                message = f"Settings saved successfully. Port changed to {web_port}. Service restart required for port change to take effect."
            else:
                message = "Settings saved successfully."
            
            return jsonify({'status': 'success', 'message': message, 'restart_required': 'port' in changes_made})
        else:
            return jsonify({'status': 'error', 'message': 'No changes provided'}), 400
        
    except Exception as e:
        logger.error(f"Error changing settings: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to change settings'}), 500

if __name__ == '__main__':
    # Create templates directory
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    # Get configuration
    config = config_manager.get_config()
    port = config.get('web_port', 8080)
    
    # Start monitoring if auto-start is enabled
    if config.get('auto_start', False):
        logger.info("Auto-start enabled, starting audio monitoring...")
        audio_monitor.start_monitoring()
    
    # Start the service
    logger.info(f"Starting RDIO-VOX v{VERSION} by {AUTHOR} on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
