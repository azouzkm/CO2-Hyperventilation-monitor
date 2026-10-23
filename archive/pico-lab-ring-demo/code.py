# Pico 2 W playground: the board makes its own Wi-Fi network and serves a
# web page that shows the chip temperature and controls the on-board LED
# and a 16-LED NeoPixel ring.
#
# 1. On your phone, join Wi-Fi  "Pico-Lab"  password  "picolab123"
# 2. Open  http://192.168.4.1  in the phone's browser
#
# Ring wiring (Pico stays in the Grove shield, use the shield's OUTER header):
#   ring 5V DC Power -> VBUS (pin 40)   ring Ground -> GND (pin 38)
#   ring Data Input  -> GP15 (pin 20)
#
# CircuitPython 9, no extra libraries needed (uses the built-in neopixel_write).

import time
import math
import json
import board
import digitalio
import microcontroller
import neopixel_write
import wifi
import socketpool

SSID = "Pico-Lab"
PASSWORD = "picolab123"   # at least 8 characters

RING_PIN = board.GP15
RING_COUNT = 16
MAX_BRIGHTNESS = 0.30     # cap at 30 % of full power so a laptop USB port copes
TEMP_LOW, TEMP_HIGH = 20.0, 45.0   # chip temperature range shown by "Temp" mode

# ---------------------------------------------------------------- on-board LED
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

DOT, DASH, GAP = 0.15, 0.45, 0.15
PATTERNS = {                       # list of (LED on?, seconds)
    "off":       [(0, 1.0)],
    "on":        [(1, 1.0)],
    "blink":     [(1, 0.25), (0, 0.25)],
    "every2s":   [(1, 0.2), (0, 1.8)],
    "heartbeat": [(1, 0.1), (0, 0.12), (1, 0.1), (0, 0.8)],
    "sos": [(1, DOT), (0, GAP)] * 3 + [(0, DASH)]
         + [(1, DASH), (0, GAP)] * 3 + [(0, DASH)]
         + [(1, DOT), (0, GAP)] * 3 + [(0, 1.2)],
}
mode = "every2s"
step = 0
step_end = time.monotonic()


def update_led():
    global step, step_end
    now = time.monotonic()
    if now >= step_end:
        pattern = PATTERNS[mode]
        step = (step + 1) % len(pattern)
        on, dur = pattern[step]
        led.value = bool(on)
        step_end = now + dur


def set_mode(new_mode):
    global mode, step, step_end
    if new_mode in PATTERNS:
        mode = new_mode
        step = -1
        step_end = 0


def chip_temp():
    try:
        return round(microcontroller.cpu.temperature, 1)
    except Exception:
        return None


# ---------------------------------------------------------------- NeoPixel ring
ring_pin = digitalio.DigitalInOut(RING_PIN)
ring_pin.direction = digitalio.Direction.OUTPUT
ring_buf = bytearray(RING_COUNT * 3)          # GRB byte order
RING_MODES = ("solid", "spin", "breathe", "rainbow", "temp", "off")
ring_mode = "rainbow"
ring_color = (0, 120, 255)
ring_bright = 50                               # percent of MAX_BRIGHTNESS
next_frame = 0.0
temp_cache = None
temp_time = 0.0


def wheel(h):
    """Hue 0..1 -> fully saturated (r, g, b)."""
    h = (h % 1.0) * 6
    i = int(h)
    f = h - i
    up = int(255 * f)
    down = int(255 * (1 - f))
    if i == 0:
        return (255, up, 0)
    if i == 1:
        return (down, 255, 0)
    if i == 2:
        return (0, 255, up)
    if i == 3:
        return (0, down, 255)
    if i == 4:
        return (up, 0, 255)
    return (255, 0, down)


def set_px(i, rgb, level=1.0):
    s = level * MAX_BRIGHTNESS * ring_bright / 100
    j = i * 3
    ring_buf[j] = int(rgb[1] * s)       # green
    ring_buf[j + 1] = int(rgb[0] * s)   # red
    ring_buf[j + 2] = int(rgb[2] * s)   # blue


def update_ring():
    global next_frame, temp_cache, temp_time
    now = time.monotonic()
    if now < next_frame:
        return
    next_frame = now + 0.03                      # about 33 frames per second
    if ring_mode == "off":
        for k in range(len(ring_buf)):
            ring_buf[k] = 0
    elif ring_mode == "solid":
        for i in range(RING_COUNT):
            set_px(i, ring_color)
    elif ring_mode == "rainbow":
        for i in range(RING_COUNT):
            set_px(i, wheel(i / RING_COUNT + now * 0.2))
    elif ring_mode == "spin":
        head = int(now * 16) % RING_COUNT
        for i in range(RING_COUNT):
            d = (head - i) % RING_COUNT
            set_px(i, ring_color, max(0.0, 1 - d / 5))
    elif ring_mode == "breathe":
        lvl = 0.1 + 0.9 * (0.5 - 0.5 * math.cos(2 * math.pi * now / 3))
        for i in range(RING_COUNT):
            set_px(i, ring_color, lvl)
    elif ring_mode == "temp":
        if now - temp_time > 1:
            temp_cache = chip_temp()
            temp_time = now
        tc = temp_cache if temp_cache is not None else 25.0
        lit = int(round((tc - TEMP_LOW) / (TEMP_HIGH - TEMP_LOW) * RING_COUNT))
        lit = max(1, min(RING_COUNT, lit))
        for i in range(RING_COUNT):
            if i < lit:
                f = i / (RING_COUNT - 1)
                set_px(i, (int(255 * f), 30, int(255 * (1 - f))))   # blue -> red
            else:
                set_px(i, (0, 0, 0))
    neopixel_write.neopixel_write(ring_pin, ring_buf)


def set_ring(q):
    global ring_mode, ring_color, ring_bright
    if "c" in q:
        v = q["c"].replace("%23", "").lstrip("#")
        if len(v) == 6:
            try:
                ring_color = (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
                if ring_mode in ("off", "rainbow", "temp"):
                    ring_mode = "solid"
            except ValueError:
                pass
    if "m" in q and q["m"] in RING_MODES:
        ring_mode = q["m"]
    if "b" in q:
        try:
            ring_bright = max(0, min(100, int(q["b"])))
        except ValueError:
            pass


# ---------------------------------------------------------------- web page
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pico Lab</title><style>
body{font-family:-apple-system,system-ui,sans-serif;margin:0;padding:20px;
background:#0f1720;color:#e8eef3;text-align:center}
h1{font-size:22px;margin:4px 0 16px}
.card{background:#1b2633;border-radius:14px;padding:16px;margin:0 auto 14px;max-width:420px}
.big{font-size:44px;font-weight:700}
.sub{color:#93a4b5;font-size:13px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:12px}
button{font-size:17px;padding:14px;border:0;border-radius:10px;background:#2b3a4b;color:#e8eef3}
button.on{background:#2fae66;color:#fff}
input[type=color]{width:100%;height:56px;border:0;border-radius:10px;background:none;padding:0}
input[type=range]{width:100%;margin-top:8px}
</style></head><body>
<h1>Pico 2 W Lab</h1>
<div class="card"><div class="sub">Chip temperature</div>
<div class="big" id="t">--</div><div class="sub" id="u">up --</div></div>
<div class="card"><div class="sub" style="margin-bottom:10px">NeoPixel ring</div>
<input type="color" id="c" value="#0078ff">
<div class="grid3" id="r"></div>
<div class="sub" style="margin-top:14px">Brightness <span id="bv">--</span> %</div>
<input type="range" id="br" min="0" max="100" value="50"></div>
<div class="card"><div class="sub" style="margin-bottom:10px">Built-in LED</div>
<div class="grid" id="b"></div></div>
<script>
const modes=[["on","On"],["off","Off"],["blink","Blink"],["every2s","Every 2 s"],
["heartbeat","Heartbeat"],["sos","SOS"]];
const rmodes=[["solid","Solid"],["spin","Spin"],["breathe","Breathe"],
["rainbow","Rainbow"],["temp","Temp"],["off","Off"]];
const $=id=>document.getElementById(id);
function add(box,list,pre,url){list.forEach(([m,l])=>{const x=document.createElement('button');
x.textContent=l;x.id=pre+m;x.onclick=()=>fetch(url+m).then(r=>r.json()).then(show);
$(box).appendChild(x);});}
add('b',modes,'m_','/mode?m=');
add('r',rmodes,'r_','/ring?m=');
let last=0;
$('c').addEventListener('input',e=>{const n=Date.now();if(n-last<150)return;last=n;
fetch('/ring?c='+e.target.value.slice(1)).then(r=>r.json()).then(show);});
$('c').addEventListener('change',e=>fetch('/ring?c='+e.target.value.slice(1)).then(r=>r.json()).then(show));
$('br').addEventListener('input',e=>{$('bv').textContent=e.target.value;});
$('br').addEventListener('change',e=>fetch('/ring?b='+e.target.value).then(r=>r.json()).then(show));
function show(d){$('t').textContent=d.temp_c===null?'n/a':d.temp_c+' \\u00b0C';
$('u').textContent='up '+d.uptime_s+' s';
modes.forEach(([m])=>$('m_'+m).className=(m===d.mode?'on':''));
rmodes.forEach(([m])=>$('r_'+m).className=(m===d.ring.mode?'on':''));
if(document.activeElement!==$('c'))$('c').value='#'+d.ring.color;
if(document.activeElement!==$('br')){$('br').value=d.ring.brightness;$('bv').textContent=d.ring.brightness;}}
function poll(){fetch('/api').then(r=>r.json()).then(show).catch(()=>{});}
poll();setInterval(poll,1000);
</script></body></html>"""

BOOT = time.monotonic()


def status():
    return {
        "temp_c": chip_temp(),
        "uptime_s": int(time.monotonic() - BOOT),
        "mode": mode,
        "ring": {
            "mode": ring_mode,
            "color": "%02x%02x%02x" % ring_color,
            "brightness": ring_bright,
        },
    }


def parse_query(path):
    q = {}
    if "?" in path:
        for part in path.split("?", 1)[1].split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                q[k] = v
    return q


def send_all(conn, data):
    view = memoryview(data)
    while len(view):
        sent = conn.send(view)
        view = view[sent:]


def reply(conn, body, ctype):
    if isinstance(body, str):
        body = body.encode()
    head = ("HTTP/1.1 200 OK\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
            "Cache-Control: no-store\r\nConnection: close\r\n\r\n" % (ctype, len(body)))
    send_all(conn, head.encode())
    send_all(conn, body)


buf = bytearray(1024)


def handle(conn):
    conn.setblocking(True)
    conn.settimeout(2)
    n = conn.recv_into(buf)
    line = bytes(buf[:n]).split(b"\r\n", 1)[0].decode()   # "GET /path HTTP/1.1"
    parts = line.split(" ")
    path = parts[1] if len(parts) > 1 else "/"
    if path.startswith("/mode"):
        q = parse_query(path)
        if "m" in q:
            set_mode(q["m"])
        reply(conn, json.dumps(status()), "application/json")
    elif path.startswith("/ring"):
        set_ring(parse_query(path))
        reply(conn, json.dumps(status()), "application/json")
    elif path.startswith("/api"):
        reply(conn, json.dumps(status()), "application/json")
    else:
        reply(conn, PAGE, "text/html; charset=utf-8")


# ---------------------------------------------------------------- start Wi-Fi
try:
    wifi.radio.stop_ap()          # drop any network left over from older code
except Exception:
    pass
wifi.radio.start_ap(ssid=SSID, password=PASSWORD)
ip = str(wifi.radio.ipv4_address_ap)
print("Wi-Fi network:", SSID, " password:", PASSWORD)
print("Open http://%s on a phone joined to that network" % ip)

pool = socketpool.SocketPool(wifi.radio)
server = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
try:
    server.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
except Exception:
    pass
server.bind((ip, 80))
server.listen(2)
server.setblocking(False)

while True:
    update_led()
    update_ring()
    try:
        conn, addr = server.accept()
    except OSError:
        conn = None
    if conn:
        try:
            handle(conn)
        except Exception as e:
            print("request error:", e)
        finally:
            conn.close()
    time.sleep(0.005)
