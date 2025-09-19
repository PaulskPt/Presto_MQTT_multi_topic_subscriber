"""
metar_mqtt_epd_udplogger_v2.py
===================================
This is an updated of metar_mqtt_edp.py
Added UDP logging feature.

This example will scan for wireless networks and attempt to connect
to the one specified in secrets.py.

If you're using a Pico LiPo 2 you'll need an RM2 breakout and an 8-pin JST-SH cable.
Grab them here: https:#shop.pimoroni.com/products/rm2-breakout

Don't forget to edit secrets.json and add your SSID and PASSWORD.

Note @PaulskPt 2025-08-24:
The script below revealed:
Pimoroni Pico LiPo 2XL W:
WiFi IP: 192.168._.___
WiFi MAC-address: __:__:__:__:__ .
Note that, because the Pimoroni Pico LiPo 2XL W, unlike the Pimoroni Presto's micropython,
does not have the module umqatt.simple, I searched Github and found this umqtt.simple2 module,
that I downloaded and installed onto the Pico LiPo 2XL W's drive, folder: /lib
This script is the second version of my attempt with this board to get a METAR messages through a GET() to server metar-taf.com 
After a successful reception, this script will send a MQTT Publisher message that can be received by MQTT Subscriber devices,
like my Pimoroni Presto device. To limit the "loss" of credits on metar-taf.com, I limit the number of METAR fetches to 3
(see secrets.json, key MAX_METAR_FETCHED). The script will fetch a METAR message every 30 minutes, at 40 minutes past the
"observed" unixtime in the METAR message. The script will run forever, until a reset or power-off.
Update 2025-09-14
In this version the received METAR data will be displayed on a connected Lolin 2.13 inch 3-Color e-Paper display of
250 x 122 pixels. Note that the clearing of the display buffers and the build-up of the text on this ePD
takes some seconds and delays the execution of this script.
For this notifications of actions regarding the screen are printed to the serial output.

"""
import machine
import network
import time
import binascii
import ujson
#import utime
from lib.umqtt.simple2 import MQTTClient
import os
import sys # See: https:#github.com/dhylands/upy-examples/blob/master/print_exc.py
#import exc # own ERR class to print errors to a log file
import urequests
import socket
import ntptime
# Imports for the EPD display
import framebuf
from lib.LOLIN_SSD1680 import SSD1680, EPD_BLACK, EPD_WHITE, EPD_RED
from lib.fonts import asc2_0806
from lib.udp_logger import UDPLogger

my_debug = False
_start1 = True
_start2 = True

TAG = "global(): "

# ===== UDP preparation =====
# after UDP is activated all print statements will be broadcasted over the LAN
# instead of via serial output
use_udp_logger = True # Set to True to enable UDP logging instead of serial output
UDP_PORT = 5005
BROADCAST_IP = '192.168.1.255'


# Get data from secrets.json
with open('secrets.json') as f:  # method used by Copilot. This reads and parses in one step
    secrets = ujson.load(f)

# Eventually (if needed)
WIFI_SSID = secrets['wifi']['ssid']
WIFI_PASSWORD = secrets['wifi']['pass']

# ===== WiFi network setup =====
net = network.WLAN(network.STA_IF)
#net.active(False)
net.active(True)
net.connect(WIFI_SSID, WIFI_PASSWORD)

# Wait until connected
while not net.isconnected():
    time.sleep(0.2)

ip, subnet, _, _ = net.ifconfig()
time.sleep(0.1)
# Use a helper to calculate broadcast IP from IP and subnet
sys.stdout.write("global(): "+f"ip: {ip}, subnet: {subnet}\n")
    
# ===== UDP Broadcast Redirect =====
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#sock.bind(('192.168.1.146', UDP_PORT))  # Replace with your RPi’s IP
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

# ===== Create an instance of the UDPLogger class =====

udp_logger = UDPLogger(sock, UDP_PORT, BROADCAST_IP, use_udp_logger)

#if use_udp_logger:
#    sys.stdout = my_logger  # Redirect print statements to UDP logger  
#    sys.stderr = my_logger  # Redirect errors to UDP logger
#    udp_logger.write(TAG+"UDP logger activated. All udp_logger.write() output will be sent via UDP broadcast.")


# === Print intro to my_logger ===
udp_logger.write("\nPimoroni")
udp_logger.write("Pico LiPo 2XL W")
udp_logger.write("+ Lolin 2.13 ePD")
udp_logger.write("Metar + MQTT + UDP Logger\n")

# ===== End UDP setup =====

udp_logger.write(TAG+"Preparing ePD...")
# --- SPI and Pin Setup ---
spi = machine.SPI(1, baudrate=2_000_000, phase=0, polarity=0, sck=machine.Pin(10), mosi=machine.Pin(11), miso=machine.Pin(12))

cs_pin   = machine.Pin(32, machine.Pin.OUT)   # Chip Select
dc_pin   = machine.Pin(35, machine.Pin.OUT)   # Data/Command
rst_pin  = machine.Pin(36, machine.Pin.OUT)   # Reset
busy_pin = machine.Pin(31, machine.Pin.IN)    # Busy

# --- Display Dimensions ---
WIDTH  = 250
HEIGHT = 122
fb_red = None
epd_text_scale = 2  # 1, 2 or 3
epd_buffer_cleared = False

# --- Initialize Display ---
epd = SSD1680(WIDTH, HEIGHT, spi, dc_pin, rst_pin, cs_pin, busy_pin)

# --- Begin Communication ---
epd.begin(reset=True)

orientation = 180
epd.set_rotation(orientation)  # Landscape mode. Or 0, 90, 270 depending on your desired orientation

epd.clear_buffer(True)  # fill epd._buffer_bw to White (0xFF)
epd_buffer_cleared = True
# epd.display()
time.sleep_ms(100)
epd.display()  # Evt. second pass helps eliminate ghosting
udp_logger.write(TAG+"ePD prepared.")

rtc = machine.RTC()

# from secrets import WIFI_SSID, WIFI_PASSWORD

use_broker_local = True if secrets['mqtt']["use_local_broker"] else False

if use_broker_local:
  broker = secrets['mqtt']['broker_local'] # "192.168.1.114"
  ssl = False  # or True if you're using TLS
else:
  broker = secrets['mqtt']['broker_external'] #  test.mosquitto.org"
  ssl = False  # or True if you're using TLS

port = int(secrets['mqtt']['port']) # 1883

#KEYFILE = "/certs/newthing.private.der"
#CERTFILE = "/certs/newthing.cert.der"

#key = open(KEYFILE,'rb').read()
#cert = open(CERTFILE,'rb').read()

# SSL certificates.
ssl_params = {} # {'key': key, 'cert': cert}

# Create a table of names for connection states
CONNECTION_STATES = {v : k[5:] for k, v in network.__dict__.items() if k.startswith("STAT_")}
CONNECTION_TIMEOUT = 5

scan_networks = False # see setup()

icao_lookup = {
    "Lisbon": "LPPT",
    "Porto": "LPPR",
    "Faro": "LPFR"
}

kHostname = "https://api.metar-taf.com/metar"
my_status = 0
my_credits = 0
if my_debug:
    udp_logger.write(TAG+"Loaded keys:", secrets['mqtt'].keys())
PUBLISHER_ID = secrets['mqtt']['publisher_id1']
api_key = secrets['mqtt']['METAR_TAF_API_KEY'] 
max_metar_fetched = secrets['mqtt']['MAX_METAR_FETCHED'] # 3
version = "&v=2.3"
locale = "&locale=en-US"
station = "&id=LPPT" # Lisbon Airport for example
# station_short = "LPPT" # Lisbon Airport for example
kPath =   kHostname + "?api_key=" + api_key + version + locale + station

topic = ("weather/{:s}/{:s}".format(PUBLISHER_ID, icao_lookup["Lisbon"] )).encode('utf-8')

sync_interval_ms = 60_000  # Check every minute
uxTime = 0
utc_offset = int(secrets['timezone']['tz_utc_offset'])  # utc offset in hours
timezone = secrets['timezone']['tz'] # example: "Europe/Lisbon"
uxTime_rcvd = 0
metarData = None
metarHeader = None
payloadBuffer = {} # bytes[768] # was: 512

if not my_debug:
    udp_logger.write(TAG+f"PUBLISHER_ID = {PUBLISHER_ID}") #, type(PUBLISHER_ID) = {type(PUBLISHER_ID)}")
    udp_logger.write(TAG+f"broker = {broker}") #, type(broker) = {type(broker)}")
    udp_logger.write(TAG+f"port = {port}") #, type(port) = {type(port)}")

mqtt = None

use_test_client = False

if use_test_client:
    mqtt = MQTTClient("testClient", broker, port=port)
else:
    mqtt = MQTTClient(
        PUBLISHER_ID,
        broker) #  port=port, keepalive=10000, ssl=ssl, ssl_params=ssl_params)

hd = {}
metar = {}
my_status = 0
my_credits = 0
nr_metar_fetched = 0
max_metar_fetched_msg_shown = False
time_to_fetch_metar = False
# Track last sync time in milliseconds
next_metar_unix_time = 0
next_metar_minutes = 40  # minutes past last metar "observed" time to fetch next metar
mqttMsgID = 0
mqttMsgID_old = 0
msgSentCnt = 0
msgSentCnt_old = 0
msgSentCnt_max = 999
testUnixTime = 1755979282
timestamp = "2025-08-23T21:01:22+0100" # ISO 8601 e.g., "2025-07-02T13:32:02"
isoBuffer = bytes(26)

CAPACITY = 1024 # Adjust based on your JSON size
# DynamicJsonDocument doc(CAPACITY)
# StaticJsonDocument<CAPACITY> doc
metarStr = ""
udp_logger.write(TAG+"globals set.")

def calc_broadcast(ip, subnet):
    TAG = "calc_broadcast(): "
    print(TAG+f"ip: {ip}, subnet: {subnet}")
    ip_parts = list(map(int, ip.split('.')))
    subnet_parts = list(map(int, subnet.split('.')))
    broadcast_parts = [(ip_parts[i] | (~subnet_parts[i] & 0xFF)) for i in range(4)]
    return '.'.join(map(str, broadcast_parts))

def draw_char_scaled(epd, x, y, char, color, scale=1):
    index = ord(char)
    if index < 32 or index > 126:
        index = 32  # fallback to space
    glyph = asc2_0806[index - 32]
    for col in range(6):
        byte = glyph[col]
        for row in range(8):
            if byte & (1 << row):
                px = x + col * scale
                py = y + row * scale
                for dx in range(scale):
                    for dy in range(scale):
                        epd.draw_pixel(px + dx, py + dy, color)

def draw_text_scaled(epd, x, y, text, color, scale=1):
    for i, c in enumerate(text):
        draw_char_scaled(epd, x + i * 6 * scale, y, c, color, scale)

def set_edp_text_scale(new_scale: int = 2):
    global epd_text_scale
    TAG = "set_epd_text_scale(): "
    if isinstance(new_scale, int):
        if new_scale >= 1 and new_scale <= 6:
            if epd_text_scale != new_scale:
                epd_text_scale = new_scale
                print(TAG+f"new scale: {epd_text_scale}")
                

def draw_intro_screen():
    # --- Draw Red Text ---
    global epd_text_scale, epd_buffer_cleared
    TAG = "draw_intro_screen(): "
    if not epd_buffer_cleared:
        print(TAG+ "going to clear the epd buffers")
        epd.clear_buffer(True) # clear epd._buffer_bw to 0xFF (White)
        epd_buffer_cleared = True
    set_edp_text_scale(2)
    x = 20
    y = 10
    draw_text_scaled(epd, x, y,    "Pimoroni",         EPD_RED, scale=epd_text_scale)
    draw_text_scaled(epd, x, y+20, "Pico LiPo 2XL W",  EPD_RED, scale=epd_text_scale)
    draw_text_scaled(epd, x, y+40, "+ Lolin 2.13 ePD", EPD_RED, scale=epd_text_scale)
    draw_text_scaled(epd, x, y+60, "Metar + MQTT",     EPD_RED, scale=epd_text_scale)
    draw_text_scaled(epd, x, y+80, "+ UDP Logger",     EPD_RED, scale=epd_text_scale)
    # --- Push to Display ---
    epd.display()
  
def draw_max_fetches_screen():
    # --- Draw Red Text ---
    global epd_text_scale, max_metar_fetched, epd_buffer_cleared
    TAG = "draw_max_fetches_screen(): "
    if not epd_buffer_cleared:
        print(TAG+ "going to clear the epd buffers")
        epd.clear_buffer(True) # clear epd._buffer_bw to 0xFF (White)
        epd_buffer_cleared = True
    set_edp_text_scale(2)
    t0 = f"Limit of {str(max_metar_fetched)} metars"
    draw_text_scaled(epd, 20,  80, t0,                 EPD_RED, scale=epd_text_scale)
    draw_text_scaled(epd, 20, 100, "fetched reached!", EPD_RED, scale=epd_text_scale)
    # --- Push to Display ---
    epd.display()

#def mypublish():
  # seq['v'] = seq['v']+1
  #msg = '{"message":"hello world","sequence":%d}' % (seq['v'])
  #mqtt.publish( topic = topic, msg = msg, qos = 0 )


def add_minutes_to_metar_as_int(metar_str: str="", minutes_to_add: int=next_metar_minutes) -> int:
    TAG = "add_minutes_to_metar_as_int(): "
    # Parse METAR time: "281430Z"
    if not isinstance(metar_str, str):
        udp_logger.write(TAG+f"param metar_str needs to be of type str. Received type {type(metar_str)}")
        return 0
    
    if len(metar_str) < 6:
        if not my_debug:
            udp_logger.write(TAG+f"length param minutes_to_add must be 6 characters. Received: {len(metar_str)}")
        return 0  # Not enough characters to safely parse
    le = len(metar_str)
    
    offset = float(utc_offset)
    if my_debug:
        udp_logger.write(TAG+f"float(utc_offset) = float({utc_offset}) = {offset}")
    offset_abs = abs(offset)
    offset_hours = int(offset_abs)
    offset_minutes = int(round((offset_abs - offset_hours) * 60))
    
    day = int(metar_str[0:2])
    hour = int(metar_str[2:4])
    minute = int(metar_str[4:6])
    
    if my_debug:
        udp_logger.write(TAG+f"hour: {hour}, minute: {minute} (derived from param: {metar_str}). Minutes to add: {minutes_to_add}")

    # Apply offset and minutes
    total_minutes = hour * 60 + minute + minutes_to_add + offset_hours * 60 + offset_minutes
    new_day = day + (total_minutes // (24 * 60))
    new_hour = (total_minutes // 60) % 24
    new_minute = total_minutes % 60

    # Return as DDHHMM integer
    return new_day * 10000 + new_hour * 100 + new_minute

# Example usage
# metar = "281430Z"
# result = add_minutes_to_metar_as_int(metar, 35)
# udp_logger.write("🧮 Integer time:", result)

def fetchMetar():
    global metarData, metarHeader, uxTime_rcvd, max_metar_fetched, nr_metar_fetched, my_status, my_credits
    TAG = "fetchMetar(): "
    udp_logger.write(TAG+"start to send request")
    
    if nr_metar_fetched+1 > max_metar_fetched:  # base-1
        if not max_metar_fetched_msg_shown:  # only show once
            max_metar_fetched_msg_shown = True
            draw_max_fetches_screen()
            udp_logger.write(TAG+f"limit of {max_metar_fetched} metars feched reached!")
        return
    
    try:
        if my_debug:
            udp_logger.write(TAG+f"kPath = {kPath[:31]}\n\t{kPath[31:]}")
            
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = urequests.get(kPath, headers=headers)
        #response = urequests.get(kPath)
        nr_metar_fetched += 1
        rawData = response.text
        if not my_debug:
            # udp_logger.write(TAG+f"type(rawData) = {type(rawData)}")
            udp_logger.write(TAG + f"Raw response (first 30 char\'s): \"{rawData[:30]}\"") # ,end='\n')
            # udp_logger.write(TAG + f"Raw response: \"{rawData}\"") # ,end='\n')
            n = rawData.find("observed")
            if n >= 0:
                uxTime_rcvd = int(rawData[n+10:n+20])
                uxTime_rcvd_human = unixToIso8601(uxTime_rcvd, False)
                udp_logger.write(TAG+f"wx observed (unix time): {uxTime_rcvd} = {uxTime_rcvd_human} UTC")
            else:
                udp_logger.write(TAG+"\'observed\' not found in rawData")
        # Decode the JSON content
        data = response.json()
        # Always close the response to free up resources
        response.close()
        # Now you can access nested fields
        my_status = data["status"]
        my_credits = data["credits"]
        metarData = data["metar"]["raw"]
        #metarHeader = data["hd"]
        
        if not my_debug:
            # udp_logger.write(TAG+f"data = {data}")
            udp_logger.write(TAG+f"my_status = {my_status}")
            udp_logger.write(TAG+f"my_credits = {my_credits}")
            udp_logger.write(TAG+f"wx observed = {uxTime_rcvd}")
            #udp_logger.write(TAG+f"hd = {metarHeader}")
            udp_logger.write(TAG+f"metar = \"{metarData}\"")
        
        n = metarData.find("Z")
        if n >= 0:
            metarDayAndHrStr = metarData[n-6:n]
            if not my_debug:
                udp_logger.write(TAG+f"metarDayAndHour: {metarDayAndHrStr} Z")
        else:
            metarDayAndHrStr = "0"
  
        minutes_to_add = next_metar_minutes
        metarHourNext = add_minutes_to_metar_as_int(metarDayAndHrStr, minutes_to_add)
        metarHourNextStr = str(metarHourNext)
        if len(metarHourNextStr) < 6:
            metarHourNextStr = "0" + metarHourNextStr
        udp_logger.write(TAG+f"metarHourNextStr = {metarHourNextStr}")
        udp_logger.write(TAG+f"🕒 Next METAR hour at: {metarHourNextStr[2:4]}h{metarHourNextStr[4:6]} local")
        
    except OSError as e:
        udp_logger.write(f"OSError: {e}")
        
    except Exception as e:
        udp_logger.write(e)
        sys.stderr.write("General exception in fetchMetar()\n") # See: https:#github.com/dhylands/upy-examples/blob/master/print_exc.py
        sys.stderr.write("Exception details:\n")
        sys.print_exception(e, sys.stderr)
        raise RuntimeError

def splitMetarforEPD(max_chars_per_line=20):
    global metarData
    if not metarData:
        return []

    words = metarData.strip().split()
    lines = []
    current_line = ""

    for word in words:
        # Predict length if we add this word
        projected_length = len(current_line) + len(word) + (1 if current_line else 0)
        if projected_length <= max_chars_per_line:
            current_line += (" " if current_line else "") + word
        else:
            lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines

def drawMetarOnEPD():
    global fb_red, epd, metarData, epd_text_scale, my_status, my_credits
    TAG = "drawMetarOnEPD(): "
    if not metarData:
        udp_logger.write(TAG+"No metarData to display!")
        return
    if not fb_red:
        udp_logger.write(TAG+"No fb_red FrameBuffer available!")
        return
    
    if epd_text_scale < 1:  
      epd_text_scale = 1
    if epd_text_scale > 3:  
      epd_text_scale = 3
      
    if epd_text_scale == 1:
      max_chars_per_line = 40
    elif epd_text_scale == 2:
      max_chars_per_line = 20
    else: # epd_text_scale == 3
      max_chars_per_line = 10
      
    lines = splitMetarforEPD(max_chars_per_line) # 20 characters max per line at epd_text_scale=2
    if not lines:
      udp_logger.write(TAG+"No lines to display!")
      return
    if len(lines) > 6:
      udp_logger.write(TAG+"Too many lines to display on ePD!")
      return # Limit to 6 lines for now
    
      
    udp_logger.write(TAG+"Drawing METAR on EPD...")
    # --- Clear Buffers to White Background ---
    epd.clear_buffer(True) # clear epd_buffer_bw to 0xFF (White)
    # epd.display()
    time.sleep_ms(100)
    set_edp_text_scale(2)
    
    # --- Draw Red Text ---
    for i, line in enumerate(lines):
        y_position = 5 + i * 20  # Adjust vertical position for each line
        draw_text_scaled(epd, 5, y_position, line, EPD_RED, scale=epd_text_scale) 
    # draw_text_scaled(epd, 5, 25, metarData, EPD_RED, scale=epd_text_scale)
    
    t0 = f"Status:  {"Active" if my_status == 1 else "Inactive"}"
    t1 = f"Credits: {my_credits}"
    draw_text_scaled(epd, 5,  80, t0, EPD_RED, scale=epd_text_scale) 
    draw_text_scaled(epd, 5, 100, t1, EPD_RED, scale=epd_text_scale) 
    
    # --- Push to Display ---
    epd.display()
    udp_logger.write(TAG+"✅ METAR drawn on EPD.")

def composePayload(local_or_utc: bool = False) -> int:
    global payLoad, hd, acc, metar, mqttMsgID, uxTime, metarData, PUBLISHER_ID, uxTime_rcvd, my_status, my_credits
    TAG = "composePayload(): "
    
    offset = float(utc_offset)

    if not local_or_utc:
        offset = 0

    # Apply offset in seconds
    offset_seconds = int(offset * 3600)
    
    if local_or_utc:
        mqttMsgID = uxTime + offset_seconds # = getUnixTime() # Important! Used in composePayload() and in send_msg()
    else:
        mqttMsgID = uxTime # use UTC
  
    # Root fields

    # Define nested objects
    if not my_debug:
        udp_logger.write(TAG+f"PUBLISHER_ID = {PUBLISHER_ID}")
    hd = {"ow": PUBLISHER_ID, # owner
      "de": "Ext",            # description (room, office, Ext for Extern (e.g.: Internet) etc.)
      "dc": "wx",             # device_class
      "sc": "meas",           # state_class
      "vt": "s",              # s = value type (for all values) string
      "t": uxTime_rcvd        # global var uxTime_rcvd  --- was: mqttMsgID
    }

    metar = {"raw": metarData}
    
    acc = {"st" : my_status, "cr": my_credits} # acc = account information
    
    # Combine into a parent JSON object
    payLoad = {
        "hd": hd,
        "acc" : acc,
        "metar": metar
    }

    # Convert to JSON string 
    written = ujson.dumps(payLoad).encode('utf-8')  # Return the int value written
    if my_debug:
        udp_logger.write(TAG+f"written = {written}")
    return written

def send_msg() -> bool:
    global msgSentCnt, payLoad, topic
    TAG = "send_msg(): "
  
    ret = False
    do_reset = False

    # FILL IN HERE THE METAR DATA

    msgSentCnt += 1
    if msgSentCnt > msgSentCnt_max:
        msgSentCnt = 1

    msg = composePayload()
    le = len(msg) # len(payLoad)
    msgStr = msg.decode('utf-8') # decode to str to prepare a split at "hd"
    n = msgStr.find("hd")
    
    if le > 0:
        if not my_debug:
            #udp_logger.write(f"contents payLoad: {payLoad}")
            topicLength = len(topic)
            udp_logger.write(TAG+f"Topic length: {topicLength}")   
            udp_logger.write(TAG+f"length written: {le}")
            udp_logger.write(TAG+f"MQTT message ID: {mqttMsgID}")
            udp_logger.write(TAG+f"in IS8601 = {unixToIso8601(mqttMsgID, False)} UTC")  # use UTC
            udp_logger.write(TAG+f"Topic = \"{topic}\"")
            if n >= 2:
                udp_logger.write(TAG+f"msg = {msg[:n-2]}") # {payLoad}")  -- do the split at "hd"
                udp_logger.write(f"\t{msg[n-2:]}")  
            else:
                udp_logger.write(TAG+f"msg = {msg[:65]}") # {payLoad}") # no "hd" found, so just split at 65 char's
                udp_logger.write(f"\t{msg[65:]}")
        if my_debug:
            udp_logger.write(TAG+f"topic type: {type(topic)}")  # should be <class 'bytes'>
            udp_logger.write(TAG+f"msg type: {type(msg)}")      # should be <class 'bytes'>

        try_cnt = 0
        while not mqtt.sock:
            udp_logger.write(TAG+"⚠️ Socket is not connected! Going to connect...")
            mqtt.connect()
            time.sleep(0.1)
            try_cnt += 1
            if try_cnt > 50:
                udp_logger.write(TAG+"⚠️ Unable to mqtt.connect!")
                break
        if try_cnt <= 50:
            if mqtt.sock:
                if my_debug:
                    udp_logger.write(TAG+f"we have a socket: type(mqtt.sock) = {type(mqtt.sock)}")
                mqtt.publish(topic,msg,qos=0)
        else:
            udp_logger.write(TAG+"⚠️ failed to publish mqtt metar message. No mqtt.sock!")
            return ret
    else:
        udp_logger.write(TAG+"⚠️ Failed to compose JSON msg")
        return ret
    
    udp_logger.write(TAG+"✅ MQTT message nr: {:3d} sent".format(msgSentCnt))
    udp_logger.write("-" * 55)
    ret = True

    return ret

def ck_for_next_metar() -> bool:
    global time_to_fetch_metar, next_metar_unix_time, uxTime_rcvd_last, max_metar_fetched_msg_shown
    ret = False
    TAG = "ck_for_next_metar(): "

    if uxTime_rcvd == 0:
        udp_logger.write(TAG+"⚠️ uxTime_rcvd is zero! Need to fetch METAR first!")
        return
    
    next_metar_unix_time = uxTime_rcvd + 1800 + 600 # 40 minutes later
    uxTime_rcvd_last = uxTime_rcvd
    
    if my_debug:
        udp_logger.write(TAG+f"Next METAR Unix time (+30 min) = : {next_metar_unix_time} = {unixToIso8601(next_metar_unix_time, False)} UTC")
    
    # Convert to ISO 8601 in local time
    if my_debug:
        udp_logger.write(TAG+f"next_metar_unix_time (to use to convert to iso_metar_send_local): {next_metar_unix_time}")
    iso_metar_send_local = unixToIso8601(next_metar_unix_time, True)
    
    current_unix = time.mktime(time.localtime())
    if my_debug:
        udp_logger.write("\n"+TAG+f"current_unix (local time): {current_unix} = {unixToIso8601(current_unix, True)}")
    if current_unix >= next_metar_unix_time:
        update_metar = True
    else:
        update_metar = False
        
    if nr_metar_fetched+1 > max_metar_fetched: 
        if not max_metar_fetched_msg_shown:
            udp_logger.write(TAG+f"limit of {max_metar_fetched} metars feched reached!")
            draw_max_fetches_screen()
            max_metar_fetched_msg_shown = True
        time_to_fetch_metar = False
        return time_to_fetch_metar
     
    if not time_to_fetch_metar and update_metar:
        udp_logger.write("🛫 Going to send METAR data message...")
        time_to_fetch_metar = True
    else:
        time_to_fetch_metar = False
    #    udp_logger.write(TAG+"📍 Next METAR will be send at (local time):", iso_metar_send_local)
    return time_to_fetch_metar

def sync_time_fm_ntp():
    global uxTime
    TAG = "sync_time_fm_ntp(): "

    try:
        # grab the current time from the ntp server and update the Pico RTC
        ntptime.settime()
        current_t = rtc.datetime()
        if my_debug:
            udp_logger.write(TAG+f"current (rtc.datetime() = {current_t}")
        current_time = time.localtime()
        yy = current_time[0]
        mo = current_time[1]
        dd = current_time[2]
        hh = current_time[3]
        mm = current_time[4]
        ss = current_time[5]
        if not my_debug:
            udp_logger.write(TAG+f"✅ Time synced: {yy:04d}-{mo:02d}-{dd:02d}T{hh:02d}:{mm:02d}:{ss:02d} UTC") # (local time, timezone {timezone}, UTC offset {utc_offset}h)")
        if my_debug:
            udp_logger.write(TAG+f"time.localtime() = {current_time}")
        uxTime = time.mktime(time.localtime())
        if my_debug:
            udp_logger.write(TAG+"🕒 Unix time:", uxTime)
    
    except OSError:
        udp_logger.write("Unable to contact NTP server")        
    except Exception as e:
        udp_logger.write(TAG+ "⚠️ NTP sync failed:", e)
 
# parameter local_or_utc default False = use UTC
def unixToIso8601(unixTime, local_or_utc: bool =False) -> str:

    global utc_offset  # Assumed to be a string like "-3.5"
    TAG = "unixToIso8601(): "

    # Convert offset to float
    
    offset = float(utc_offset)

    if not local_or_utc:
        offset = 0

    # Apply offset in seconds
    offset_seconds = int(offset * 3600)
    if my_debug:
        udp_logger.write(TAG+f"offset_seconds = {offset_seconds}")
    adjusted_time = unixTime + offset_seconds

    # Convert to time tuple
    local_t = time.localtime(adjusted_time)
    year, month, day, hour, minute, second = local_t[0:6]

    # Format offset string
    sign = "+" if offset >= 0 else "-"
    offset_abs = abs(offset)
    offset_hours = int(offset_abs)
    offset_minutes = int(round((offset_abs - offset_hours) * 60))
    offsetStr = f"{sign}{offset_hours:02d}:{offset_minutes:02d}"
    if my_debug:
        udp_logger.write(TAG + f"offset_hours {offset_hours}")
        udp_logger.write(TAG + f"offset_minutes {offset_minutes}")
        udp_logger.write(TAG + f"offsetStr {offsetStr}")
        

    # Build ISO 8601 string
    iso_str = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}{offsetStr}"

    if my_debug:
        udp_logger.write(TAG + f"unixTime = {unixTime}")
        udp_logger.write(TAG + f"adjusted_time = {adjusted_time}")
        udp_logger.write(TAG + f"iso_str = {iso_str}")

    return iso_str

# Get iso8601 from time.localtime()
# Default treat as UTC (GMT)
def get_iso8601(use_localtime: bool=False):
    import time

    global utc_offset
    TAG = "get_iso8601(): "

    # Get UTC time
    t = time.localtime()
    year, month, day, hour, minute, second = t[0:6]

    # Convert offset to float
    offset = float(utc_offset)
    if my_debug:
        udp_logger.write(TAG + f"type(utc_offset) = {type(utc_offset)}")

    if not use_localtime:
        # use UTC (GMT)
        offset = 0
    
    # Apply offset in seconds
    offset_seconds = int(offset * 3600)
    adjusted_time = time.mktime(t) + offset_seconds
    local_t = time.localtime(adjusted_time)

    # Extract adjusted time components
    year, month, day, hour, minute, second = local_t[0:6]

    # Format offset string
    sign = "+" if offset >= 0 else "-"
    offset_abs = abs(offset)
    offset_hours = int(offset_abs)
    offset_minutes = int(round((offset_abs - offset_hours) * 60))
    offsetStr = f"{sign}{offset_hours:02d}:{offset_minutes:02d}"

    # Build ISO 8601 string
    iso_str = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}{offsetStr}"
    if my_debug:
        udp_logger.write(TAG + f"iso_str = {iso_str}")

    return iso_str


def setup():
    global mqtt, framebuf, fb_red, ip, subnet, net, udp_logger, use_udp_logger
    TAG = "setup(): "
    
    if scan_networks:
        udp_logger.write("\nScanning for WiFi networks.")

        results = []
        while not results:
            udp_logger.write("Scanning...")
            results = net.scan()

        padding = max(len(r[0]) for r in results) + 1

        udp_logger.write("\nFound WiFi networks:")
        udp_logger.write(f"{'SSID':{padding}s} {'BSSID':17s}  CH dB Auth")
        for (ssid, bssid, channel, rssi, auth_mode, _) in results:
            # Auth mode is a bitfield,
            # see https:#github.com/georgerobotics/cyw43-driver/blob/v1.1.0/src/cyw43_ll.c#L573-L584
            auth_modes = [mode for b, mode in ((1, "WEP"), (2, "WPA"), (4, "WPA2")) if auth_mode & b] or ["open"]

            bssid = binascii.hexlify(bssid, ":").decode()

            udp_logger.write(f"{ssid:{padding}s} {bssid} {channel:2d} {rssi: 2d} {'/'.join(auth_modes)}")

    sys.stdout.write(f"WiFi active: {net.active()}, connected: {net.isconnected()}\n")
    
    #t0 = TAG + "Connecting to {}".format(WIFI_SSID)
    #udp_logger.write(t0) # TAG+f"Connecting to {WIFI_SSID}")
    t_start = time.time()
    
    broadcast_ip = calc_broadcast(ip, subnet)
    udp_logger.write(TAG+f"Broadcast IP address: {broadcast_ip}")
    
    if net.isconnected():
        udp_logger.write(TAG+"[" + str(t_start) + "] Connected to Vodafone-8D96F1")
        ip_fm_addr4 = net.ipconfig("addr4")[0]
        udp_logger.write(TAG+f"IP-address: {ip_fm_addr4}")
        # udp_logger.write('network config:', net.ifconfig())
        a = net.config('mac')
        udp_logger.write(TAG+'WiFi MAC-address: {:02x}:{:02x}:{:02x}:{:02x}:{:02x}'.format(a[0],a[1],a[2],a[3],a[4]))
    
    if my_debug:
        udp_logger.write(TAG+f"Local time before synchronization: {str(time.localtime())}")  # result: (2000, 1, 1, 0, 40, 8, 5, 1)
    ntptime.settime()
    if my_debug:
        udp_logger.write(TAG+f"Local time after synchronization: {str(time.localtime())}") # result: (2018, 12, 27, 12, 10, 7, 3, 361)


    if my_debug:
        udp_logger.write(f"type(udp_logger) = {type(udp_logger)}")
        udp_logger.write(f"type(socket) = {type(socket)}")

    # Get local time tuple
    lt = time.localtime()

    # Convert to Unix timestamp
    unix_time = time.mktime(lt)
    udp_logger.write(TAG+f"Unix time: {unix_time}")
    # udp_logger.write("\n")

    if mqtt:
        if my_debug:
            udp_logger.write(TAG+f"type(mqtt) = {type(mqtt)}")
        udp_logger.write(TAG+"trying to mqtt.connect()")
        mqtt.connect()

        if mqtt.sock:
            if not my_debug:
                udp_logger.write(TAG+"✅ mqtt.connect() successful")
            if my_debug:
                udp_logger.write(TAG+f"✅ we have a mqtt.sock: type(mqtt.sock) = {type(mqtt.sock)}")
        else:
            udp_logger.write(TAG+"⚠️ failed to create mqtt client because failed to create a socket!")
            raise RuntimeError
    else:
        udp_logger.write(TAG+"⚠️ failed to create a MQTTClient object")
        
        
    # --- Clear epd Buffers to White Background ---
    # udp_logger.write(TAG+"Clearing ePD buffers...")
    # Note the buffers are created ()

    # --- Create FrameBuffer for Red Text ---
    udp_logger.write(TAG+"Creating FrameBuffer for red text...")
    if orientation == 0 or orientation == 180:
        fb_red = framebuf.FrameBuffer(epd._buffer_red, WIDTH, HEIGHT, framebuf.MONO_HLSB)  # Portrait orientation
    elif orientation == 90 or orientation == 270:
        fb_red = framebuf.FrameBuffer(epd._buffer_red, WIDTH, HEIGHT, framebuf.MONO_VLSB) # Landscape orientation

    # --- Draw Intro Screen ---
    udp_logger.write(TAG+"Drawing intro screen...")
    draw_intro_screen()
    udp_logger.write(TAG+"Setup complete.")
    time.sleep(5) # Give user time to read the intro screen

SYNC_INTERVAL = 15 * 60  # 15 minutes in seconds
    
def go_epd():
    global time_to_fetch_metar, _msg_interval_t, _start1, _start2,  nr_metar_fetched, max_metar_fetched, max_metar_fetched_msg_shown
    TAG = "main(): "
    setup()
    # Timing variables
    _start_t = time.ticks_ms()
    _msg_interval_t = 30 * 60 * 1000  # every 30 minutes (but at 05 and 35, see sync_time_fm_ntp())

    _start1 = True  # For NTP sync
    
    udp_logger.write(TAG+"Starting non-blocking METAR loop...")
    _ntp_start_t = time.ticks_ms()
    _msg_start_t = time.ticks_ms()
    _ntp_interval_t = 15 * 60 * 1000  # every 15 minutes
    _chk_metar_t = 10 * 1000 # every 1 minute
    msg_cnt = 0
    previous_metar_unix_time = 0
    # Loop to sync every 15 minutes
    if not my_debug:
        udp_logger.write(TAG+f"MQTT message send interval: {int(float(_msg_interval_t/1000))} seconds")
    while True:
        now = time.ticks_ms()
        now2 = time.ticks_ms()
        diff_t = time.ticks_diff(now, _ntp_start_t)
        diff_t2 = time.ticks_diff(now2, _msg_start_t)
        if my_debug:
            if _start1 or msg_cnt > 100:
                msg_cnt = 0
                udp_logger.write(TAG+"diff_t = {:>6d}, _ntp_interval_t = {:>6d}".format(diff_t, _ntp_interval_t))
            msg_cnt += 1
        if _start1 or diff_t >= _ntp_interval_t:
            _start1 = False
            _ntp_start_t = now
            sync_time_fm_ntp()
            if not my_debug:
                udp_logger.write(TAG+f"ISO 8601 time: {get_iso8601(True)}") # show local time

        if _start2 or diff_t2 >= _chk_metar_t: #  _msg_interval_t:  #_ck_metar_interval_t:
            _msg_start_t = now2
            ck_for_next_metar()
            if previous_metar_unix_time != next_metar_unix_time:
                previous_metar_unix_time = next_metar_unix_time
                udp_logger.write(TAG+f"📍 next_metar_unix_time = {next_metar_unix_time} = {unixToIso8601(next_metar_unix_time, True)}")
            
        # time_to_fetch_metar: see sync_time_fm_ntp    
        if _start2 or time_to_fetch_metar: # time.ticks_diff(now, _start_t) >= _msg_interval_t:
            time_to_fetch_metar = False
            _start2 = False
            if nr_metar_fetched+1 > max_metar_fetched:
                if not max_metar_fetched_msg_shown:
                    udp_logger.write(TAG+f"limit of {max_metar_fetched} metars feched reached!")
                    draw_max_fetches_screen()
                    max_metar_fetched_msg_shown = True
            else:
                udp_logger.write(TAG+"Time to fetch METAR!")
                fetchMetar()
                udp_logger.write(TAG+"Time to publish MQTT message!")
                send_msg()
                _msg_start_t = now  # Reset timer
                udp_logger.write(TAG+"Time to draw METAR on ePD!")
                drawMetarOnEPD()
                udp_logger.write(TAG+"Waiting for next METAR update...")

        # Do other non-blocking tasks here
        # Example: check sensors, handle MQTT, blink LED, etc.

        time.sleep(0.1)  # Small delay to prevent CPU hogging
    
if __name__ == '__main__':
    go_epd()