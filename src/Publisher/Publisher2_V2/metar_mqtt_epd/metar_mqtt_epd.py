"""
metar_mqtt_epd.py
=================

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
import ujson
import network
import time
import binascii
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

my_debug = False
_start1 = True
_start2 = True

TAG = "global(): "

print(TAG+"Preparing ePD...")
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

# --- Initialize Display ---
epd = SSD1680(WIDTH, HEIGHT, spi, dc_pin, rst_pin, cs_pin, busy_pin)

# --- Begin Communication ---
epd.begin(reset=True)

orientation = 180
epd.set_rotation(orientation)  # Landscape mode. Or 0, 90, 270 depending on your desired orientation

epd.clear_buffer()
# epd.display()
time.sleep_ms(100)
epd.display()  # Evt. second pass helps eliminate ghosting
print(TAG+"ePD prepared.")

rtc = machine.RTC()

# from secrets import WIFI_SSID, WIFI_PASSWORD

with open('secrets.json') as f:  # method used by Copilot. This reads and parses in one step
    secrets = ujson.load(f)

# Eventually (if needed)
WIFI_SSID = secrets['wifi']['ssid']
WIFI_PASSWORD = secrets['wifi']['pass']

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
    print(TAG+"Loaded keys:", secrets['mqtt'].keys())
PUBLISHER_ID = secrets['mqtt']['publisher_id1']
api_key = secrets['mqtt']['METAR_TAF_API_KEY'] 
max_metar_fetched = secrets['mqtt']['MAX_METAR_FETCHED'] # 3
version = "&v=2.3"
locale = "&locale=en-US"
station = "&id=LPPT" # Lisbon Airport for example
# station_short = "LPPT" # Lisbon Airport for example
kPath =   kHostname + "?api_key=" + api_key + version + locale + station

topic = ("weather/{:s}/{:s}".format(PUBLISHER_ID, icao_lookup["Lisbon"] )).encode('utf-8')

time_to_fetch_metar = False
# Track last sync time in milliseconds
next_metar_unix_time = 0

sync_interval_ms = 60_000  # Check every minute
uxTime = 0
utc_offset = int(secrets['timezone']['tz_utc_offset'])  # utc offset in hours
timezone = secrets['timezone']['tz'] # example: "Europe/Lisbon"
uxTime_rcvd = 0
metarData = None
metarHeader = None
payloadBuffer = {} # bytes[768] # was: 512

if not my_debug:
    print(TAG+f"PUBLISHER_ID = {PUBLISHER_ID}") #, type(PUBLISHER_ID) = {type(PUBLISHER_ID)}")
    print(TAG+f"broker = {broker}") #, type(broker) = {type(broker)}")
    print(TAG+f"port = {port}") #, type(port) = {type(port)}")

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
nr_metar_fetched = 0
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

def draw_intro_screen():
  # --- Draw Red Text ---
  global epd_text_scale
  epd_text_scale = 2
  draw_text_scaled(epd, 20, 20, "Pimoroni", EPD_RED, scale=epd_text_scale)
  draw_text_scaled(epd, 20, 40, "Pico LiPo 2XL W", EPD_RED, scale=epd_text_scale)
  draw_text_scaled(epd, 20, 60, "+ Lolin 2.13 ePD", EPD_RED, scale=epd_text_scale)
  draw_text_scaled(epd, 20, 80, "Metar + MQTT", EPD_RED, scale=epd_text_scale)
  # --- Push to Display ---
  epd.display()

#def mypublish():
  # seq['v'] = seq['v']+1
  #msg = '{"message":"hello world","sequence":%d}' % (seq['v'])
  #mqtt.publish( topic = topic, msg = msg, qos = 0 )

def add_minutes_to_metar_as_int(metar_str: str="", minutes_to_add: int=35) -> int:
    TAG = "add_minutes_to_metar_as_int(): "
    # Parse METAR time: "281430Z"
    if not isinstance(metar_str, str):
        print(TAG+f"param metar_str needs to be of type str. Received type {type(metar_str)}")
        return 0
    
    if len(metar_str) < 6:
        if not my_debug:
            print(TAG+f"length param minutes_to_add must be 6 characters. Received: {len(metar_str)}")
        return 0  # Not enough characters to safely parse
    le = len(metar_str)
    
    offset = float(utc_offset)
    if my_debug:
        print(TAG+f"float(utc_offset) = float({utc_offset}) = {offset}")
    offset_abs = abs(offset)
    offset_hours = int(offset_abs)
    offset_minutes = int(round((offset_abs - offset_hours) * 60))
    
    day = int(metar_str[0:2])
    hour = int(metar_str[2:4])
    minute = int(metar_str[4:6])
    
    if my_debug:
        print(TAG+f"hour: {hour}, minute: {minute} (derived from param: {metar_str}). Minutes to add: {minutes_to_add}")

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
# print("🧮 Integer time:", result)


def fetchMetar():
    global metarData, metarHeader, uxTime_rcvd, max_metar_fetched, nr_metar_fetched
    TAG = "fetchMetar(): "
    print(TAG+"start to send request")
    
    if nr_metar_fetched+1 > max_metar_fetched:  # base-1
        print(TAG+f"limit of {max_metar_fetched} metars feched reached!")
        return
    
    try:
        if my_debug:
            print(TAG+f"kPath = {kPath[:31]}\n\t{kPath[31:]}")
            
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = urequests.get(kPath, headers=headers)
        #response = urequests.get(kPath)
        nr_metar_fetched += 1
        rawData = response.text
        if not my_debug:
            # print(TAG+f"type(rawData) = {type(rawData)}")
            print(TAG + f"Raw response (first 30 char\'s): \"{rawData[:30]}\"",end='\n')
            #print(TAG + f"Raw response: \"{rawData}\"",end='\n')
            n = rawData.find("observed")
            if n >= 0:
                uxTime_rcvd = int(rawData[n+10:n+20])
                uxTime_rcvd_human = unixToIso8601(uxTime_rcvd, False)
                print(TAG+f"wx observed (unix time): {uxTime_rcvd} = {uxTime_rcvd_human} UTC")
            else:
                print(TAG+"\'observed\' not found in rawData")
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
            # print(TAG+f"data = {data}")
            print(TAG+f"my_status = {my_status}")
            print(TAG+f"my_credits = {my_credits}")
            print(TAG+f"wx observed = {uxTime_rcvd}")
            #print(TAG+f"hd = {metarHeader}")
            print(TAG+f"metar = {metarData}")
        
        n = metarData.find("Z")
        if n >= 0:
            metarDayAndHrStr = metarData[n-6:n]
            if not my_debug:
                print(TAG+f"metarDayAndHour: {metarDayAndHrStr} Z")
        else:
            metarDayAndHrStr = "0"
  
        minutes_to_add = 35
        metarHourNext = add_minutes_to_metar_as_int(metarDayAndHrStr, minutes_to_add)
        metarHourNextStr = str(metarHourNext)
        if len(metarHourNextStr) < 6:
            metarHourNextStr = "0" + metarHourNextStr
        print(TAG+f"metarHourNextStr = {metarHourNextStr}")
        print(TAG+f"🕒 Next METAR hour at: {metarHourNextStr[2:4]}h{metarHourNextStr[4:6]} local")
        
    except OSError as e:
        print(f"OSError: {e}")
        
    except Exception as e:
        print(e)
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
    global fb_red, epd, metarData, epd_text_scale
    TAG = "drawMetarOnEPD(): "
    if not metarData:
        print(TAG+"No metarData to display!")
        return
    if not fb_red:
        print(TAG+"No fb_red FrameBuffer available!")
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
      print(TAG+"No lines to display!")
      return
    if len(lines) > 6:
      print(TAG+"Too many lines to display on ePD!")
      return # Limit to 6 lines for now
    
      
    print(TAG+"Drawing METAR on EPD...")
    epd.clear_buffer()
    # epd.display()
    time.sleep_ms(100)
    
    # --- Clear Buffers to White Background ---
    for i in range(len(epd._buffer_bw)):
        epd._buffer_bw[i] = 0xFF  # White
    for i in range(len(epd._buffer_red)):
        epd._buffer_red[i] = 0x00  # No red yet
    
    # --- Draw Red Text ---
    for i, line in enumerate(lines):
        y_position = 5 + i * 20  # Adjust vertical position for each line
        draw_text_scaled(epd, 5, y_position, line, EPD_RED, scale=epd_text_scale) 
    # draw_text_scaled(epd, 5, 25, metarData, EPD_RED, scale=epd_text_scale)
    
    # --- Push to Display ---
    epd.display()
    print(TAG+"✅ METAR drawn on EPD.")

def composePayload(local_or_utc: bool = False) -> int:
    global payLoad, hd, metar, mqttMsgID, uxTime, metarData, PUBLISHER_ID, uxTime_rcvd
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
        print(TAG+f"PUBLISHER_ID = {PUBLISHER_ID}")
    hd = {"ow": PUBLISHER_ID, # owner
      "de": "Ext",            # description (room, office, Ext for Extern (e.g.: Internet) etc.)
      "dc": "wx",             # device_class
      "sc": "meas",           # state_class
      "vt": "s",              # s = value type (for all values) string
      "t": uxTime_rcvd        # global var uxTime_rcvd  --- was: mqttMsgID
    }

    metar = {"raw": metarData}
    
    # Combine into a parent JSON object
    payLoad = {
        "hd": hd,
        "metar": metar
    }

    # Convert to JSON string 
    written = ujson.dumps(payLoad).encode('utf-8')  # Return the int value written
    if my_debug:
        print(TAG+f"written = {written}")
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
    if le > 0:
        if not my_debug:
            #print(f"contents payLoad: {payLoad}")
            topicLength = len(topic)
            print(TAG+f"Topic length: {topicLength}")   
            print(TAG+f"length written: {le}")
            print(TAG+f"MQTT message ID: {mqttMsgID}")
            print(TAG+f"in IS8601 = {unixToIso8601(mqttMsgID, False)} UTC")  # use UTC
            print(TAG+f"Topic = \"{topic}\"")
            print(TAG+f"msg = {msg[:65]}") # {payLoad}")
            print(f"\t{msg[65:]}")
        if my_debug:
            print(TAG+f"topic type: {type(topic)}")  # should be <class 'bytes'>
            print(TAG+f"msg type: {type(msg)}")      # should be <class 'bytes'>

        try_cnt = 0
        while not mqtt.sock:
            print(TAG+"⚠️ Socket is not connected! Going to connect...")
            mqtt.connect()
            time.sleep(0.1)
            try_cnt += 1
            if try_cnt > 50:
                print(TAG+"⚠️ Unable to mqtt.connect!")
                break
        if try_cnt <= 50:
            if mqtt.sock:
                if my_debug:
                    print(TAG+f"we have a socket: type(mqtt.sock) = {type(mqtt.sock)}")
                mqtt.publish(topic,msg,qos=0)
        else:
            print(TAG+"⚠️ failed to publish mqtt metar message. No mqtt.sock!")
            return ret
    else:
        print(TAG+"⚠️ Failed to compose JSON msg")
        return ret
    
    print(TAG+"✅ MQTT message nr: {:3d} sent".format(msgSentCnt))
    print("-" * 55)
    ret = True

    return ret

def ck_for_next_metar() -> bool:
    global time_to_fetch_metar, next_metar_unix_time, uxTime_rcvd_last
    ret = False
    TAG = "ck_for_next_metar(): "

    if uxTime_rcvd == 0:
        print(TAG+"⚠️ uxTime_rcvd is zero! Need to fetch METAR first!")
        return
    
    next_metar_unix_time = uxTime_rcvd + 1800 + 600 # 40 minutes later
    uxTime_rcvd_last = uxTime_rcvd
    
    if my_debug:
        print(TAG+f"Next METAR Unix time (+30 min) = : {next_metar_unix_time} = {unixToIso8601(next_metar_unix_time, False)} UTC")
    
    # Convert to ISO 8601 in local time
    if my_debug:
        print(TAG+f"next_metar_unix_time (to use to convert to iso_metar_send_local): {next_metar_unix_time}")
    iso_metar_send_local = unixToIso8601(next_metar_unix_time, True)
    
    current_unix = time.mktime(time.localtime())
    if my_debug:
        print("\n"+TAG+f"current_unix (local time): {current_unix} = {unixToIso8601(current_unix, True)}")
    if current_unix >= next_metar_unix_time:
        update_metar = True
    else:
        update_metar = False
        
    if nr_metar_fetched+1 > max_metar_fetched: 
        print(TAG+f"limit of {max_metar_fetched} metars feched reached!")
        time_to_fetch_metar = False
        return time_to_fetch_metar
     
    if not time_to_fetch_metar and update_metar:
        print("🛫 Going to send METAR data message...")
        time_to_fetch_metar = True
    else:
        time_to_fetch_metar = False
    #    print(TAG+"📍 Next METAR will be send at (local time):", iso_metar_send_local)
    return time_to_fetch_metar

def sync_time_fm_ntp():
    global uxTime
    TAG = "sync_time_fm_ntp(): "

    try:
        # grab the current time from the ntp server and update the Pico RTC
        ntptime.settime()
        current_t = rtc.datetime()
        if my_debug:
            print(TAG+f"current (rtc.datetime() = {current_t}")
        current_time = time.localtime()
        yy = current_time[0]
        mo = current_time[1]
        dd = current_time[2]
        hh = current_time[3]
        mm = current_time[4]
        ss = current_time[5]
        if not my_debug:
            print(TAG+f"✅ Time synced: {yy:04d}-{mo:02d}-{dd:02d}T{hh:02d}:{mm:02d}:{ss:02d} UTC") # (local time, timezone {timezone}, UTC offset {utc_offset}h)")
        if my_debug:
            print(TAG+f"time.localtime() = {current_time}")
        uxTime = time.mktime(time.localtime())
        if my_debug:
            print(TAG+"🕒 Unix time:", uxTime)
    
    except OSError:
        print("Unable to contact NTP server")        
    except Exception as e:
        print(TAG+ "⚠️ NTP sync failed:", e)
 
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
        print(TAG+f"offset_seconds = {offset_seconds}")
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
        print(TAG + f"offset_hours {offset_hours}")
        print(TAG + f"offset_minutes {offset_minutes}")
        print(TAG + f"offsetStr {offsetStr}")
        

    # Build ISO 8601 string
    iso_str = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}{offsetStr}"

    if my_debug:
        print(TAG + f"unixTime = {unixTime}")
        print(TAG + f"adjusted_time = {adjusted_time}")
        print(TAG + f"iso_str = {iso_str}")

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
        print(TAG + f"type(utc_offset) = {type(utc_offset)}")

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
        print(TAG + f"iso_str = {iso_str}")

    return iso_str


def setup():
    global mqtt, framebuf, fb_red
    TAG = "setup(): "
    net = network.WLAN(network.STA_IF)
    net.active(False)
    net.active(True)

    if scan_networks:
        print("\nScanning for WiFi networks.")

        results = []
        while not results:
            print("Scanning...")
            results = net.scan()

        padding = max(len(r[0]) for r in results) + 1

        print("\nFound WiFi networks:")
        print(f"{'SSID':{padding}s} {'BSSID':17s}  CH dB Auth")
        for (ssid, bssid, channel, rssi, auth_mode, _) in results:
            # Auth mode is a bitfield,
            # see https:#github.com/georgerobotics/cyw43-driver/blob/v1.1.0/src/cyw43_ll.c#L573-L584
            auth_modes = [mode for b, mode in ((1, "WEP"), (2, "WPA"), (4, "WPA2")) if auth_mode & b] or ["open"]

            bssid = binascii.hexlify(bssid, ":").decode()

            print(f"{ssid:{padding}s} {bssid} {channel:2d} {rssi: 2d} {'/'.join(auth_modes)}")


    print(f"\nConnecting to {WIFI_SSID}.", end='')

    net.connect(WIFI_SSID, WIFI_PASSWORD)

    t_start = time.time()

    while True:
        status = net.status()
        my_status = CONNECTION_STATES.get(status, status)
        #print(f"my_status = {my_status}")
        if my_status == "CONNECTING":
          print(".", end='')

        #print(f"Status: {CONNECTION_STATES.get(status, status)}")

        if status in (network.STAT_GOT_IP, network.STAT_CONNECT_FAIL):
            print()
            break

        if time.time() - t_start > CONNECTION_TIMEOUT:
            print(f"Timed out after {CONNECTION_TIMEOUT} seconds...")
            break

        time.sleep(1.0)
        
    if net.isconnected():
        ip = net.ipconfig("addr4")[0]
        print(f"IP-address: {ip}")
        # print('network config:', net.ifconfig())
        a = net.config('mac')
        print('WiFi MAC-address: {:02x}:{:02x}:{:02x}:{:02x}:{:02x}'.format(a[0],a[1],a[2],a[3],a[4]))
    
    if my_debug:
        print(TAG+f"Local time before synchronization: {str(time.localtime())}")  # result: (2000, 1, 1, 0, 40, 8, 5, 1)
    ntptime.settime()
    if my_debug:
        print(TAG+f"Local time after synchronization: {str(time.localtime())}") # result: (2018, 12, 27, 12, 10, 7, 3, 361)


    # Get local time tuple
    lt = time.localtime()

    # Convert to Unix timestamp
    unix_time = time.mktime(lt)

    print("Unix time:", unix_time)


    if mqtt:
        if my_debug:
            print(TAG+f"type(mqtt) = {type(mqtt)}")
        print(TAG+"trying to mqtt.connect()")
        mqtt.connect()

        if mqtt.sock:
            if my_debug:
                print(TAG+f"✅ we have a mqtt.sock: type(mqtt.sock) = {type(mqtt.sock)}")
        else:
            print(TAG+"⚠️ failed to create mqtt client because failed to create a socket!")
            raise RuntimeError
    else:
        print(TAG+"⚠️ failed to create a MQTTClient object")
        
        
    # --- Clear epd Buffers to White Background ---
    print(TAG+"Clearing ePD buffers...")
    for i in range(len(epd._buffer_bw)):
        epd._buffer_bw[i] = 0xFF  # White
    for i in range(len(epd._buffer_red)):
        epd._buffer_red[i] = 0x00  # No red yet

    # --- Create FrameBuffer for Red Text ---
    print(TAG+"Creating FrameBuffer for red text...")
    if orientation == 0 or orientation == 180:
        fb_red = framebuf.FrameBuffer(epd._buffer_red, WIDTH, HEIGHT, framebuf.MONO_HLSB)  # Portrait orientation
    elif orientation == 90 or orientation == 270:
        fb_red = framebuf.FrameBuffer(epd._buffer_red, WIDTH, HEIGHT, framebuf.MONO_VLSB) # Landscape orientation

    # --- Draw Intro Screen ---
    print(TAG+"Drawing intro screen...")
    draw_intro_screen()
    print(TAG+"Setup complete.")

SYNC_INTERVAL = 15 * 60  # 15 minutes in seconds
    
def main():
    global time_to_fetch_metar, _msg_interval_t, _start1, _start2,  nr_metar_fetched, max_metar_fetched
    TAG = "main(): "
    setup()
    # Timing variables
    _start_t = time.ticks_ms()
    _msg_interval_t = 30 * 60 * 1000  # every 30 minutes (but at 05 and 35, see sync_time_fm_ntp())

    print(TAG+"Starting non-blocking METAR loop...")
    _ntp_start_t = time.ticks_ms()
    _msg_start_t = time.ticks_ms()
    _ntp_interval_t = 15 * 60 * 1000  # every 15 minutes
    _chk_metar_t = 10 * 1000 # every 1 minute
    msg_cnt = 0
    previous_metar_unix_time = 0
    # Loop to sync every 15 minutes
    if not my_debug:
        print(TAG+f"MQTT message send interval: {int(float(_msg_interval_t/1000))} seconds")
    while True:
        now = time.ticks_ms()
        now2 = time.ticks_ms()
        diff_t = time.ticks_diff(now, _ntp_start_t)
        diff_t2 = time.ticks_diff(now2, _msg_start_t)
        if my_debug:
            if _start1 or msg_cnt > 100:
                msg_cnt = 0
                print(TAG+"diff_t = {:>6d}, _ntp_interval_t = {:>6d}".format(diff_t, _ntp_interval_t))
            msg_cnt += 1
        if _start1 or diff_t >= _ntp_interval_t:
            _start1 = False
            _ntp_start_t = now
            sync_time_fm_ntp()
            if not my_debug:
                print(TAG+f"ISO 8601 time: {get_iso8601(True)}") # show local time

        if _start2 or diff_t2 >= _chk_metar_t: #  _msg_interval_t:  #_ck_metar_interval_t:
            _msg_start_t = now2
            ck_for_next_metar()
            if previous_metar_unix_time != next_metar_unix_time:
                previous_metar_unix_time = next_metar_unix_time
                print(TAG+f"📍 next_metar_unix_time = {next_metar_unix_time} = {unixToIso8601(next_metar_unix_time, True)}")
            
        # time_to_fetch_metar: see sync_time_fm_ntp    
        if _start2 or time_to_fetch_metar: # time.ticks_diff(now, _start_t) >= _msg_interval_t:
            time_to_fetch_metar = False
            _start2 = False
            if nr_metar_fetched+1 > max_metar_fetched: 
                print(TAG+f"limit of {max_metar_fetched} metars feched reached!")
            else:
                print(TAG+"Time to fetch METAR!")
                fetchMetar()
                print(TAG+"Time to publish MQTT message!")
                send_msg()
                _msg_start_t = now  # Reset timer
                print(TAG+"Time to draw METAR on ePD!")
                drawMetarOnEPD()
                print(TAG+"Waiting for next METAR update...")

        # Do other non-blocking tasks here
        # Example: check sensors, handle MQTT, blink LED, etc.

        time.sleep(0.1)  # Small delay to prevent CPU hogging
    
if __name__ == '__main__':
    main()