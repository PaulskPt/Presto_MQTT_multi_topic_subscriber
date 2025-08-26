"""
This example will scan for wireless networks (depending global variable: scan_networks) and attempt to connect
to the one specified in secrets.json.

This MicroPython script is written for a Pimoroni Pico Lipo 2XL W (PIM776)
Date: 2025-08-26
By: Paulus Schulinck (Github handle: @PaulskPt)
License: MIT

Purposes:
1) Connect via WiFi;
2) at intervals get a NTP unix datetimestamp;
3) at other intervals get a weather message from server metar-taf.com 
   extract the METAR section and the "observed" (unixTime) value;
4) compose and send a MQTT message, topic "weather/PL2XLW/metar" to a MQTT Broker (in this case a local Broker (LAN))

If you're using a Pico LiPo 2 you'll need an RM2 breakout and an 8-pin JST-SH cable.
Grab them here: https:#shop.pimoroni.com/products/rm2-breakout

Don't forget to edit secrets.json and add/fill-in:
- WiFi SSID, 
- WiFi PASSWORD,
- IP-address of your broker_local or broker_external,
- meta-taf.com API KEY,
- tz_utc_offset (examples: "1", "-3.5")
- tz (example: "Europe/Lisbon")

Note @PaulskPt 2025-08-24:
The script below revealed:
Pimoroni Pico Lipo 2XL W:
WiFi IP: 192.168._.___
WiFi MAC-address: __:__:__:__:__
Note that, because the Pimoroni Pico Lipo 2XL W, unlike the Pimoroni Presto's micropython,
does not have the module umqatt.simple, I searched Github and found this umqtt.simple2 module,
that I downloaded and installed onto the Pico Lipo 2XL W's drive, folder: /lib
This script is my first attempt with this board to get a METAR messages through a GET() to server metar-taf.com 
After a successful reception, this script will send a MQTT Publisher message that can be received by MQTT Subscriber devices,
like, in my case: a Pimoroni Presto device.
"""
import ujson
import network
import time
import binascii
#import utime
from lib.umqtt.simple2 import MQTTClient
import os
import sys # See: https:#github.com/dhylands/upy-examples/blob/master/print_exc.py
import exc # own ERR class to print errors to a log file
import urequests
import socket
import ntptime


my_debug = False

TAG = "global(): "

# from secrets import WIFI_SSID, WIFI_PASSWORD

with open('secrets.json') as f:  # method used by Copilot. This reads and parses in one step
    secrets = ujson.load(f)

# Eventually (if needed)
WIFI_SSID = secrets['wifi']['ssid']
WIFI_PASSWORD = secrets['wifi']['pass']

use_broker_local = True

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

kHostname = "https://api.metar-taf.com/metar"
my_status = 0
my_credits = 0
if my_debug:
    print(TAG+"Loaded keys:", secrets['mqtt'].keys())
PUBLISHER_ID = secrets['mqtt']['publisher_id1']
api_key = secrets['mqtt']['METAR_TAF_API_KEY'] 
version = "&v=2.3"
locale = "&locale=en-US"
station = "&id=LPPT" # Lisbon Airport for example
# station_short = "LPPT" # Lisbon Airport for example
# token = secrets['mqtt']['METAR_TAF_TOKEN']
kPath =   kHostname + "?api_key=" + api_key + version + locale + station # + "&token=" + token

topic = ("weather/{:s}/metar".format(PUBLISHER_ID)).encode('utf-8')

uxTime = 0
utc_offset = secrets['timezone']['tz_utc_offset']  # utc offset in hours
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
    mqtt = MQTTClient("testClient", "192.168.1.114", port=1883)
else:
    mqtt = MQTTClient(
        PUBLISHER_ID,
        broker) #  port=port, keepalive=10000, ssl=ssl, ssl_params=ssl_params)

hd = {}
metar = {}
mqttMsgID = 0
mqttMsgID_old = 0
msgGrpID = 0
msgGrpID_old = 0
msgGrpID_max = 999
testUnixTime = 1755979282
timestamp = "2025-08-23T21:01:22+0100" # ISO 8601 e.g., "2025-07-02T13:32:02"
isoBuffer = bytes(26)

CAPACITY = 1024 # Adjust based on your JSON size
# DynamicJsonDocument doc(CAPACITY)
# StaticJsonDocument<CAPACITY> doc
metarStr = ""

#def mypublish():
  # seq['v'] = seq['v']+1
  #msg = '{"message":"hello world","sequence":%d}' % (seq['v'])
  #mqtt.publish( topic = topic, msg = msg, qos = 0 )

def fetchMetar():
    global metarData, metarHeader, uxTime_rcvd
    TAG = "fetchMetar(): "
    print(TAG+"start to send request")
    try:
        if my_debug:
            print(TAG+f"kPath = {kPath[:31]}\n\t{kPath[31:]}")
            
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = urequests.get(kPath, headers=headers)
        #response = urequests.get(kPath)
        rawData = response.text
        if not my_debug:
            # print(TAG+f"type(rawData) = {type(rawData)}")
            print(TAG + f"Raw response (first 30 char\'s): \"{rawData[:30]}\"",end='\n')
            n = rawData.find("observed")
            if n >= 0:
                uxTime_rcvd = int(rawData[n+10:n+20])
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
        
    except OSError as e:
        print(f"OSError: {e}")
        
    except Exception as e:
        print(e)
        raise RuntimeError


def composePayload(local_or_utc: bool = False) -> int:
    global payLoad, hd, metar, mqttMsgID, uxTime, metarData, PUBLISHER_ID, uxTime_rcvd
    TAG = "composePayload(): "
    
    offset = float(utc_offset)
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
    global msgGrpID, payLoad, topic
    TAG = "send_msg(): "
  
    ret = False
    do_reset = False

    # FILL IN HERE THE METAR DATA

    msgGrpID += 1
    if msgGrpID > msgGrpID_max:
        msgGrpID = 1

    msg = composePayload()
    le = len(msg) # len(payLoad)
    if le > 0:
        if not my_debug:
            #print(f"contents payLoad: {payLoad}")
            topicLength = len(topic)
            print(TAG+f"Topic length: {topicLength}")   
            print(TAG+f"length written: {le}")
            print(TAG+f"MQTT message ID: {mqttMsgID}")
            print(TAG+f"in IS8601 = {unixToIso8601(mqttMsgID, False)}")  # use UTC
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
        print("⚠️ Failed to compose JSON msg")
  
    print("MQTT message group: {:3d} sent".format(msgGrpID))
    print("-" * 55)
    ret = True

    return ret

def sync_time_fm_ntp():
    global uxTime
    TAG = "sync_time_fm_ntp(): "

    try:
        ntptime.settime()
        time_synced = time.localtime()
        uxTime = time.mktime(time.localtime())
        if not my_debug:
            print(TAG+"✅ Time synced:", time_synced)
            print(TAG+"🕒 Unix time:", uxTime)
    except Exception as e:
        print("⚠️ NTP sync failed:", e)

"""
def unixToIso8601(unix_time) -> str:
    TAG = "unixToIso8601(): "
    # Example Unix timestamp
    #unix_time = 1724680440  # Replace this with your actual timestamp

    if isinstance(unix_time, str):
        unix_time = int(unix_time)
    
    # Convert to local time tuple
    time_tuple = time.localtime(unix_time)

    # Format as ISO 8601 string
    iso8601 = "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(
        time_tuple[0], time_tuple[1], time_tuple[2],
        time_tuple[3], time_tuple[4], time_tuple[5]
    )
    if not my_debug:
        print(TAG+f"ISO 8601: {iso8601}")
    
    return iso8601
"""  
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
    global mqtt
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

SYNC_INTERVAL = 15 * 60  # 15 minutes in seconds
    
def main():
    TAG = "main(): "
    setup()
    # Timing variables
    _start_t = time.ticks_ms()
    _msg_interval_t = 60000  # milliseconds
    _start1 = True
    _start2 = True
    print(TAG+"Starting non-blocking METAR loop...")
    _ntp_start_t = time.ticks_ms()
    _ntp_interval_t = 15 * 60 * 1000

    # Loop to sync every 15 minutes
    if not my_debug:
        print(TAG+f"MQTT message send interval: {int(float(_msg_interval_t/1000))} seconds")
    while True:
        now = time.ticks_ms()
        if _start1 or time.ticks_diff(now, _ntp_start_t) >= _ntp_interval_t:
            _start1 = False
            _ntp_start_t = now
            sync_time_fm_ntp()
            if not my_debug:
                print(TAG+f"ISO 8601 time: {get_iso8601(True)}") # show local time
    
        if _start2 or time.ticks_diff(now, _start_t) >= _msg_interval_t:
            _start2 = False
            print(TAG+"Time to fetch METAR!")
            fetchMetar()
            print(TAG+"Time to publish MQTT message!")
            send_msg()
            _start_t = now  # Reset timer

        # Do other non-blocking tasks here
        # Example: check sensors, handle MQTT, blink LED, etc.

        time.sleep(0.1)  # Small delay to prevent CPU hogging
    

if __name__ == '__main__':
    main()