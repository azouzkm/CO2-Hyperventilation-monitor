# CO2 sensor: Winsen MH-Z19C

Source: Winsen, *MH-Z19C (pins & terminal type) NDIR CO2 module manual*, ver 1.2.
Our unit's label reads **MH-Z19C, 400–5000PPM**.

| Property | Datasheet value |
| --- | --- |
| Principle | Non-dispersive infrared (NDIR) |
| Range (our unit) | 400–5000 ppm (0.04–0.5 % CO2); 2000 and 10000 ppm versions exist |
| Accuracy | ±(50 ppm + 5 % of reading) |
| Response time | T90 < 120 s |
| Preheat | 1 min |
| Supply | 5.0 ± 0.1 V DC (notes allow 4.5–5.5 V); supply ≥ 150 mA |
| Current | < 40 mA average, 125 mA peak |
| Interface | UART, 3.3 V TTL (5 V tolerant), 9600 baud, 8N1; also PWM output |
| Read command | `FF 01 86 00 00 00 00 00 79` → 9-byte reply, CO2 = byte2 × 256 + byte3 |
| Self-calibration | **On by default**: re-zeroes to 400 ppm every 24 h. Turn off for bench work |
| Manual zero | HD pin held low ≥ 7 s, after ≥ 20 min stable at 400 ppm |
| Size | 32.9 × 19.7 × 8.6 mm (L × W × H), 5 g (Winsen product page) |
| Handling | Do not press on the gold chamber from any direction; 0–95 % RH, **no condensation** |

## Measured on our bench (22 Oct 2026, open air, details in the lab notebook)

| Property | Result |
| --- | --- |
| Reading just after power-on | 500 ppm placeholder (ESPHome documents bogus warm-up readings for about 75 s) |
| Supply at the Pico's VBUS pad | 5.18 V |
| Steady room air, evening | 800–850 ppm, noise ±2.5 ppm (1 SD) |
| One breath from 15 cm | +309 to +598 ppm; rise 10–90 % 10.6–12.7 s; fall 90–10 % 51–66 s |
| 15 breaths/min for 1 min from 15 cm | Rise visible at breath 2; +100 ppm at breath 3; plateau about +1,000 ppm; near room air 89 s after stopping |
| Breath-by-breath ripple | About 2 ppm on a 1,000 ppm rise: individual breaths are not resolved |
| HD wire touching ground | Reading held at exactly 400 ppm while it touched; returned to about 840 ppm when freed |

## What this means for the engineering requirements (to discuss as a team)

- **Range:** exhaled breath is around 5 % CO2 (50,000 ppm), ten times the top of this
  sensor's range. Undiluted exhaled gas will read at the ceiling.
- **Speed:** T90 under 120 s versus a breath every few seconds: this hardware cannot
  resolve individual breaths. It can support presence/absence and a slow trend at most.
  The card asks us to measure this and say so plainly; it is the assignment, not a failure.
  First bench numbers (22 Oct) agree: rise 11–13 s, fall about a minute, about 2 ppm of ripple
  per breath. Absence has to be called from the trend, not from the return to room air.
- **Options to evaluate:** sample a known, diluted fraction of the exhaled gas so the
  concentration stays inside the range; define "CO2 present" as a rise above room baseline;
  measure the real 10–90 % response and delay against line length before fixing any numbers.
- **Self-calibration** must be switched off for bench runs (`mhz19c.set_self_calibration(..., False)`),
  otherwise the baseline can shift during the term.
