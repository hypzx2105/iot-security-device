import RPi.GPIO as GPIO
import time

PIR_PIN = 17      # PIR OUT -> BCM17 (pin físico 11)
BUZZER_PIN = 21   # Control buzzer -> BCM21 (pin físico 40)

GPIO.setmode(GPIO.BCM)

# Pull-down para evitar lecturas "flotantes"
GPIO.setup(PIR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

pwm = GPIO.PWM(BUZZER_PIN, 1000)  # frecuencia inicial (se cambia en la sirena)

def siren(seconds=10):
    """
    Sirena tipo alarma: sube y baja la frecuencia.
    """
    end_time = time.time() + seconds
    f_min = 900
    f_max = 3200
    step = 40

    pwm.start(80)  # duty alto para máximo volumen

    try:
        while time.time() < end_time:
            # Subida
            for f in range(f_min, f_max, step):
                pwm.ChangeFrequency(f)
                time.sleep(0.003)
                if time.time() >= end_time:
                    break
            # Bajada
            for f in range(f_max, f_min, -step):
                pwm.ChangeFrequency(f)
                time.sleep(0.003)
                if time.time() >= end_time:
                    break
    finally:
        pwm.ChangeDutyCycle(0)
        pwm.stop()

print("Loading, please wait 60s (PIR warm-up).")
time.sleep(60)
print("Ready. Move your hand to trigger the alarm.")

try:
    while True:
        if GPIO.input(PIR_PIN) == GPIO.HIGH:
            print("Movement detected -> ALARM 10s")
            siren(10)

            # Esperar a que el PIR vuelva a LOW para no re-disparar instantáneo
            while GPIO.input(PIR_PIN) == GPIO.HIGH:
                time.sleep(0.05)

            # Pequeño cooldown (opcional)
            time.sleep(1)

        time.sleep(0.05)

except KeyboardInterrupt:
    print("Exiting...")

finally:
    try:
        pwm.stop()
    except Exception:
        pass
    GPIO.cleanup()
