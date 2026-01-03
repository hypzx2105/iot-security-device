import os
import time
import threading
import subprocess
import queue
from datetime import datetime, timezone

import RPi.GPIO as GPIO
import requests
from dotenv import load_dotenv

from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub
from pubnub.callbacks import SubscribeCallback

load_dotenv()

# -------------------------
# Config
# -------------------------
DEVICE_ID = os.getenv("DEVICE_ID", "pi01")
PUBNUB_PUBLISH_KEY = os.getenv("PUBNUB_PUBLISH_KEY")
PUBNUB_SUBSCRIBE_KEY = os.getenv("PUBNUB_SUBSCRIBE_KEY")

BACKEND_URL = os.getenv("BACKEND_URL", "http://192.168.1.8:5000/api/upload")
UPLOAD_TOKEN = os.getenv("UPLOAD_TOKEN", "change_me_token")

PIR_PIN = 17
BUZZER_PIN = 21

PHOTOS_PER_TRIGGER = int(os.getenv("PHOTOS_PER_TRIGGER", "3"))
PHOTO_DELAY = float(os.getenv("PHOTO_DELAY", "1"))
COOLDOWN = float(os.getenv("COOLDOWN", "10"))

# -------------------------
# State
# -------------------------
armed = True
siren_forced_on = False
last_trigger = 0.0

cancel_capture = threading.Event()
camera_jobs: "queue.Queue[dict]" = queue.Queue(maxsize=20)

# -------------------------
# GPIO
# -------------------------
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

buzzer = GPIO.PWM(BUZZER_PIN, 1000)
buzzer.start(0)


def buzzer_on():
    buzzer.ChangeDutyCycle(80)


def buzzer_off():
    buzzer.ChangeDutyCycle(0)


def alarm(duration=5):
    buzzer_on()
    time.sleep(duration)
    buzzer_off()


def take_photo(path):
    subprocess.run(
        ["rpicam-still", "-o", path, "--nopreview"],
        check=True
    )


def upload_photo(path):
    with open(path, "rb") as f:
        r = requests.post(
            BACKEND_URL,
            headers={"X-Upload-Token": UPLOAD_TOKEN},
            files={"file": f},
            timeout=20
        )
    print("Upload:", r.status_code, r.text)
    r.raise_for_status()


def pubnub_client():
    if not PUBNUB_PUBLISH_KEY or not PUBNUB_SUBSCRIBE_KEY:
        raise RuntimeError("Missing PUBNUB keys in .env")

    pnconfig = PNConfiguration()
    pnconfig.publish_key = PUBNUB_PUBLISH_KEY
    pnconfig.subscribe_key = PUBNUB_SUBSCRIBE_KEY
    pnconfig.uuid = f"device-{DEVICE_ID}"
    return PubNub(pnconfig)


pubnub = pubnub_client()
CMD_CH = f"vigil_cmd_{DEVICE_ID}"
EVT_CH = f"vigil_evt_{DEVICE_ID}"


def publish_event(event_type, payload=None):
    msg = {
        "device_id": DEVICE_ID,
        "event": event_type,
        "ts": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {}
    }
    pubnub.publish().channel(EVT_CH).message(msg).sync()


def camera_worker():
    """
    Único lugar donde se usa la cámara.
    Así nunca hay 2 capturas al mismo tiempo.
    """
    while True:
        job = camera_jobs.get()
        try:
            job_type = job.get("type")
            if job_type == "TAKE_PHOTO":
                _job_take_photo(job)
            elif job_type == "MOTION_BURST":
                _job_motion_burst(job)
            else:
                publish_event("error", {"where": "camera_worker", "err": f"Unknown job {job_type}"})
        except Exception as e:
            publish_event("error", {"where": "camera_worker", "err": str(e)})
        finally:
            camera_jobs.task_done()


def _job_take_photo(job):
    if cancel_capture.is_set():
        publish_event("cmd_cancelled", {"command": "TAKE_PHOTO"})
        return

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    path = f"/tmp/manual_{ts}.jpg"
    take_photo(path)
    upload_photo(path)
    publish_event("photo_uploaded", {"filename": os.path.basename(path), "manual": True})


def _job_motion_burst(job):
    global armed

    if not armed or cancel_capture.is_set():
        publish_event("motion_ignored", {"reason": "disarmed_or_cancelled"})
        return

    alarm(5)

    uploaded = []
    for _ in range(PHOTOS_PER_TRIGGER):
        if not armed or cancel_capture.is_set():
            publish_event("capture_cancelled", {"files_so_far": uploaded})
            return

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        path = f"/tmp/intruder_{ts}.jpg"
        take_photo(path)
        upload_photo(path)
        uploaded.append(os.path.basename(path))
        time.sleep(PHOTO_DELAY)

    publish_event("photos_uploaded", {"files": uploaded})


def enqueue_job(job: dict) -> bool:
    try:
        camera_jobs.put_nowait(job)
        return True
    except queue.Full:
        publish_event("error", {"where": "enqueue_job", "err": "camera queue full"})
        return False


class CommandListener(SubscribeCallback):
    def message(self, pubnub, message):
        global armed, siren_forced_on

        m = message.message
        cmd = (m.get("command") or "").upper()
        print("CMD:", cmd, m)

        if cmd == "ARM":
            armed = True
            siren_forced_on = False
            cancel_capture.clear()
            buzzer_off()
            publish_event("armed", {"armed": True})

        elif cmd == "DISARM":
            armed = False
            siren_forced_on = False
            cancel_capture.set()
            buzzer_off()
            publish_event("armed", {"armed": False})

        elif cmd == "SIREN_ON":
            siren_forced_on = True
            cancel_capture.set()
            buzzer_on()
            publish_event("siren", {"on": True})

        elif cmd == "SIREN_OFF":
            siren_forced_on = False
            buzzer_off()
            publish_event("siren", {"on": False})

        elif cmd == "TAKE_PHOTO":
            if not armed:
                publish_event("cmd_rejected", {"command": "TAKE_PHOTO", "reason": "disarmed"})
                return

            ok = enqueue_job({"type": "TAKE_PHOTO"})
            publish_event("cmd_ack", {"command": "TAKE_PHOTO", "queued": ok})

        elif cmd == "STATUS":
            publish_event("status", {"armed": armed, "siren": siren_forced_on, "queue": camera_jobs.qsize()})


def start_pubnub():
    pubnub.add_listener(CommandListener())
    pubnub.subscribe().channels([CMD_CH]).execute()
    publish_event("online", {"armed": armed})


# -------------------------
# Motion loop
# -------------------------
def motion_loop():
    global last_trigger

    print(f"Device {DEVICE_ID} online.")
    print(f"Listening: {CMD_CH}")
    print(f"Publishing: {EVT_CH}")

    print("Warming up PIR 30s...")
    time.sleep(30)
    print("System ready.")

    while True:
        time.sleep(0.2)

        if siren_forced_on:
            continue

        if not armed:
            continue

        if time.time() - last_trigger < COOLDOWN:
            continue

        if GPIO.input(PIR_PIN):
            last_trigger = time.time()
            print("Motion detected!")
            publish_event("motion_detected")

            enqueue_job({"type": "MOTION_BURST"})


# -------------------------
# Main
# -------------------------
try:
    threading.Thread(target=camera_worker, daemon=True).start()
    threading.Thread(target=start_pubnub, daemon=True).start()

    motion_loop()

except KeyboardInterrupt:
    print("Exiting...")

finally:
    try:
        buzzer.stop()
    except Exception:
        pass
    GPIO.cleanup()
