# Vigil device (Raspberry Pi)

This is the code that runs on the Raspberry Pi in Vigil, the home security system I built on my own for the IoT Development module in third year at DkIT. The Pi watches a room with a motion sensor, sounds a buzzer, takes photos and sends everything to the web app. The web app and the dashboard are in [iot-security-web](https://github.com/hypzx2105/iot-security-web).

![Wiring diagram](docs/fritzing-diagram.png)

## Hardware

| Part | Connection |
|---|---|
| Raspberry Pi 4 | Main board |
| PIR motion sensor | OUT to GPIO 17 (pin 11), powered from the 5V and GND rails |
| Active buzzer | Driven by a 2N2222 NPN transistor with a 1kΩ resistor on the base |
| Pi camera module | CSI ribbon cable |

In the code the transistor for the buzzer is on GPIO 21 (pin 40). The diagram still shows GPIO 18, which is where I had it at first.

## How it works

security_device.py is the main program and it runs three things at the same time. The main loop reads the PIR sensor every 0.2 seconds. When it sees motion and the system is armed, it publishes motion_detected to PubNub and adds a job to a queue. A camera thread takes the jobs from that queue, sounds the buzzer, takes a burst of photos with rpicam-still and uploads each one to the server with an HTTPS POST and the X-Upload-Token header. I used a queue so the sensor loop never waits for the camera or the network. There is also a 10 second cooldown so the same movement doesn't trigger it again and again.

The third thread listens to the PubNub command channel. These are the commands the Pi understands:

| Command | What it does |
|---|---|
| ARM | Turns motion monitoring on |
| DISARM | Turns it off and cancels a capture that is running |
| SIREN_ON / SIREN_OFF | Turns the buzzer on or off from the dashboard |
| TAKE_PHOTO | Takes one photo on demand (only when armed) |
| STATUS | Sends back if it is armed, if the siren is on and how many jobs are waiting |

pir_siren_alarm.py is a smaller script that only tests the sensor and the siren, without the camera or the cloud.

## Security

The Pi doesn't run a web server and doesn't open any port, it only makes outgoing connections. It publishes to vigil_evt_pi01 and listens on vigil_cmd_pi01, and its PubNub token only allows those two channels. The photos go to the server over HTTPS and the server rejects any upload without the right token. All keys and tokens are read from a .env file that is not in the repository.

## Running it

On a Raspberry Pi with the camera enabled:

```
git clone https://github.com/hypzx2105/iot-security-device.git
cd iot-security-device
pip install -r requirements.txt
cp .env.example .env
python security_device.py
```

Put your PubNub keys, the device token, the backend URL and the upload token in .env. The PIR sensor needs about 30 seconds to warm up before the system is ready.

Iker Arza, DkIT, BSc in Computing in Software Development
