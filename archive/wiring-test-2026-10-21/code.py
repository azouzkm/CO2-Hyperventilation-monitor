# Team 6 - live MH-Z19C wiring test (temporary main program).
# Green LED on the Pico:  STEADY ON = sensor answering  |  BLINKING = no answer yet.
# Readings also print to the serial console (Thonny / Mu) about once a second.
import time
import board
import digitalio
from mhz19c import probe

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

print("Team 6 CO2 sensor test - LED steady = working, blinking = no answer")
while True:
    orientation, ppm = probe()
    if orientation:
        led.value = True
        print("CO2 %d ppm  (wires %s)" % (ppm, orientation))
        time.sleep(1.0)
    else:
        print("no answer from sensor")
        for _ in range(2):
            led.value = True
            time.sleep(0.15)
            led.value = False
            time.sleep(0.35)
