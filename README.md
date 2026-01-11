IoT Security Device (Raspberry Pi)

This repository contains the software running on the Raspberry Pi used as the
IoT device in the Vigil security system.

The device is responsible for detecting motion, capturing photos, triggering
an alarm, and communicating securely with the cloud backend using PubNub and HTTPS.

Technologies Used
- Python 3
- Raspberry Pi GPIO
- Camera (rpicam-still)
- PubNub Python SDK
- Requests
- systemd (optional service)

Hardware Components
- Raspberry Pi
- PIR motion sensor
- Camera module
- Buzzer

Device Responsibilities
- Detect motion using a PIR sensor
- Capture photos automatically when motion is detected
- Trigger an audible alarm using a buzzer
- Upload captured photos to the backend over HTTPS
- Publish events to the cloud using PubNub
- Listen for commands from the backend using PubNub

Communication
- PubNub is used for real-time communication between the device and the cloud
- The device subscribes to a command channel:
  vigil_cmd_<device_id>
- The device publishes events to:
  vigil_evt_<device_id>
- PubNub Access Manager tokens are used to restrict publish and subscribe access

Backend Communication
- Photos are uploaded using HTTPS POST requests
- Upload requests require a shared upload token sent via HTTP headers
- No inbound ports are opened on the device

Security Considerations
- No web server runs on the device
- All communication is outbound only
- HTTPS is used for uploads
- PubNub channels are protected using access tokens
- Secrets and keys are stored in a local .env file and not commited to github

Configuration
The device is configured using environment variables stored in a .env file:

- DEVICE_ID
- PUBNUB_PUBLISH_KEY
- PUBNUB_SUBSCRIBE_KEY
- PUBNUB_DEVICE_TOKEN
- BACKEND_URL
- UPLOAD_TOKEN

Running the Device
Activate the virtual environment:
source .venv/bin/activate

yaml
Copiar código

Run the device software:
python3 security_device.py

vbnet
Copiar código

The device will:
- Connect to PubNub
- Announce its online status
- Begin monitoring for motion events

