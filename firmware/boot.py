# Team 6 - power-up sensor check.
# Runs once each time the board is plugged in, before code.py.
# Its output is saved in boot_out.txt on the CIRCUITPY drive, so the result can be
# read from a computer without a serial console.
import time
from mhz19c import probe

time.sleep(2.0)  # let the sensor power up
orientation, ppm = None, None
for _ in range(4):
    orientation, ppm = probe()
    if orientation:
        break
    time.sleep(0.5)
if orientation:
    print("CO2 OK: %d ppm, wires %s" % (ppm, orientation))
else:
    print("CO2: NO REPLY either way")
