# Wiring

The Pico 2 W sits in the Grove Shield for Pi Pico v1.0. Each Pico pin is also available
in the shield's black header rows on either side of the Pico, with the pin name printed
beside each hole.

## MH-Z19C CO2 sensor (7-wire terminal cable)

| Wire | Sensor pin (datasheet) | Shield hole | Notes |
| --- | --- | --- | --- |
| Red | Vin, 5 V | **5V** (right row, top hole = Pico VBUS) | Needs 5 V; do not use a 3V3 hole |
| Black | GND | **GND** (any GND hole) | Without it the sensor has no power |
| Blue | RXD (sensor listens) | **GP0** (Pico TX) | Confirmed 22 Oct |
| Green | TXD (sensor talks) | **GP1** (Pico RX) | Confirmed 22 Oct |
| Brown | HD, zero calibration | not connected, tip insulated, taped back along the cable | Held to ground for 7 s it re-zeroes the sensor. On 22 Oct it touched the laptop's grounded case and held the reading at 400 ppm; keep it away from metal |
| White | reserved | not connected, taped | |
| Yellow | PWM output | not connected, taped | Not used; we read the sensor over UART |

**Data-wire orientation confirmed on the bench (22 Oct 2026): `normal`**, Pico TX on GP0 to the
sensor's RXD (blue), sensor TXD (green) to the Pico's RX on GP1. `boot_out.txt` reported
`CO2 OK ... wires normal` at two power-ups.

### Current bench wiring (through the half-size breadboard, since 21 Oct)

| Wire | Goes to |
| --- | --- |
| Sensor red (Vin) | Breadboard left + column |
| Sensor black (GND) | Breadboard left − column |
| Sensor blue (RXD) | Breadboard row 5, hole a |
| Sensor green (TXD) | Breadboard row 7, hole a |
| Jumper J1 | + column to shield **5V** (right row, top hole) |
| Jumper J2 | − column to shield **GND** (left row, 3rd hole) |
| Jumper J3 | Row 5, hole e to shield **GP0** (left row, top hole) |
| Jumper J4 | Row 7, hole e to shield **GP1** (left row, 2nd hole) |

Measured 22 Oct with USB connected: 5.18 V at the Pico's VBUS pad, 3.31 V at its 3V3 pad.

### Notes

- Colour-to-pin mapping is inferred from the datasheet pin order (1 HD, 2 reserved, 3 GND,
  4 Vin, 5 RXD, 6 TXD, 7 PWM) and the colour order on the plug (brown, white, black, red,
  blue, green, yellow). On 21 Oct the data wires seemed reversed, but that was the unstripped
  wire ends; on 22 Oct the datasheet order was confirmed. The driver still accepts either
  orientation, so a swapped pair never stops the readings.
- The shield's 3.3 V/5 V switch only powers the Grove sockets, not the header holes above.
- Sensor current: under 40 mA average, 125 mA peak at 5 V (datasheet).

### Pulling a data wire (fault test, 25 Oct)

Pulling the **green** wire (sensor TXD, breadboard row 7) stops the sensor's answers: the board
shows TECHNICAL (cyan) within 1-2 s. Pulling the taped brown, white or yellow wires does nothing.

## Light ring (wired 25 Oct)

NeoPixel Ring 16, soldered to a Grove lead, plugged into the shield's **D16** Grove socket
(data on **GP16**). The shield's power switch for the Grove sockets is on **5V**. Brightness is
capped at 8 % in `firmware/lib/indicator.py` (about 0.1 A for the whole ring).
Picture: `hardware/ring_where_it_plugs.png`.

## Speaker and button (wired 25 Oct, no soldering yet)

The shield's black pin strip just right of the Pico, counted from the bottom:
GP16, GP17, GND, **GP18**, GP19, **GP20**, GP21, GND (GP16 and GP17 are the ring's).

| Part | Connection now |
| --- | --- |
| Button, one wire | Breadboard row 11 (hole a); jumper from row 11 (hole e) to **GP20** |
| Button, other wire | Breadboard − column (ground) |
| Speaker red | Breadboard row 17 (hole a) |
| Speaker black | Breadboard − column (ground) |
| Resistor, 220-470 Ω | Row 17 (hole c) to row 20 (hole c): protects the pin, and makes the speaker quiet |
| Jumper | Row 20 (hole e) to **GP18** (sound, PWM) |

The button uses the Pico's internal pull-up: pressed = GP20 reads low. Row numbers are the ones in
the diagram, `hardware/button_speaker_wiring_no_solder.png`; any free rows work as long as each pair
shares a row.

**After the amplifier is soldered** (planned Monday 26 Oct, `hardware/soldering-speaker-button.pdf`):
the speaker moves to the PAM8302A's speaker + and − holes, and the amplifier takes Vin from 5V, Gnd
and A− from GND, and A+ from **GP18**, in place of the resistor. The firmware stays the same.

## Safety clip on the sampling line (wired 1 Nov, CR-3)

A loop from **GP21** to **GND** that opens when the tube comes off the SAMPLE barb.

| Part | Connection |
| --- | --- |
| Orange male-to-female jumper | Pin end in **GP21** (shield strip right of the Pico, the hole above the button's GP20); socket end out of the case through a small hole beside SAMPLE |
| Grey-black male-to-female jumper | Pin end in **GND** (the top hole of the same strip); socket end out through the same hole |
| Purple male-to-male jumper | Taped along the tube, its two pins pushed halfway into the two sockets: closes the loop |

Read with the Pico's internal pull-up: loop closed (tube on) = GP21 low; tube pulled off = the
purple pins come out = GP21 high = "LINE OFF". The pins must be pulled along their length by the
tube: built inside the case first, nothing moved when the tube came off. Check with the meter
(USB unplugged): tube on = beep between GP21 and GND, tube off = silent; and 5V to GND must never
beep. Pictures: `cr3_safety_clip_plug_and_socket.png`, `cr3_step1_safety_clip.png`.

## Not yet wired

| Part | Planned connection |
| --- | --- |
| PAM8302A amplifier | As above, once soldered |
| Water-trap probe | divider to an analog pin (CR-3 idea) |
