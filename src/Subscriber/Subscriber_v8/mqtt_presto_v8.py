# 2025-06-17 Downloaded from: https://github.com/digitalurban/Presto_MQTT_Display/blob/main/mqtt_presto.py
# by Andy Hudson-Smith going by @digitalurban
# Changes by Paulus Schulinck going by @PaulskPt
# License: MIT.
# Version 4.0  created on 2025-07-31.
# Includes handling mqtt messages with topics:
#         sensors/Feath/ambient,
#         lights/Feath/toggle,
#         lights/Feath/color_inc and
#         lights/Feath/color_dec
#         weather/metar   (added: 2025-07-31)
# Added functions to control the 7 ambient backlight LEDs
# by means of MQTT messages sent by a remote MQTT Publisher device.
# 2025-08-19 Version 6. In msg_split() added code to handle new nested JsonObject "head".
# 2025-08-20 Version 7. Added function redraw, in case the data on the display has to be redrawn, 
# for example after reception of a MQTT message topic DispColor change.
# Then the screen needs to be redrawn in the new display color
# To make this happen I created:
# - object classes for each of the topics (sensor_obj, toggle_obj, amb_obj, disp_obj and metar_obj)
# - these object classes are defined in file mqtt_entities.py
# - Split the received mqtt messes into these sections:
#   - topic name;
#   - topicIdx;
#   - head (dict);
#   - payload (dict);
# - Write the received data as a dict to a messages history file (sd/msg_hist.json)
# - Read the save record from file on SD and use this data to redraw the screen.
#     This redraw'n screen has "RD" in the topleft corner.
#     As soon as the next message of topic "sensors/Feath/ambient" arrives, 
#     the redrawn data will be updated by function draw(),
#     continuing with the new display color.
# - Added a function to check and remove old records from the messages history file on SD. 
#     Current limit is 180 records, however when this limit has been reached, the cleanup will retain 20 records.
# 2025-08-25 Version 8: adapted script to received MQTT messages with topic "weather/PL2XLW/metar",
#   sent by MQTT Publisher Pimoroni PicoLipo 2XL W
#   Example payload: 
#   Payload = {"hd":{"ow":"PL2XLW","de":"Ext","dc":"wx","sc":"meas","vt":"s","ts":1755978381},
#              "metar":{"raw":"METAR LPPT 291930Z 34012KT CAVOK 30/10 Q1014"}}
# Note: for more verbose output from the Broker, on the Broker device. Run the broker as follows:
#        sudo mosquitto -c /etc/mosquitto/mosquitto.conf -v
#
import ujson
import utime
from presto import Presto
from umqtt.simple import MQTTClient
import os
import sys # See: https://github.com/dhylands/upy-examples/blob/master/print_exc.py
import time
import exc # own ERR class to print errors to a log file
from random import randint
# Force reload of the real re module
# sys.modules.pop("re", None)
import re # for extracting the numeral in e.g.: "topic4"
# from mqtt_entities import *
# FIX: Import the required classes explicitly or ensure mqtt_entities.py exists in the same directory.
try:
    sys.path.append('/sd/lib')

    from mqtt_entities import SensorTPAH, LightsToggle, AmbientColors, DisplayColors, Metar
except ImportError:
    # Define dummy classes if mqtt_entities.py is missing, to avoid import errors
    class SensorTPAH:
        pass
    class LightsToggle:
        pass
    class AmbientColors:
        pass
    class DisplayColors:
        pass
    class Metar:
        pass

"""
   deliveryComplete(IMqttDeliveryToken token) is called when the broker successfully gets your message published,
   this isn't called when the client had received your message. 
"""
TAG = "global(): "

full_res = False
# Setup for the Presto display
presto = Presto()

display = presto.display
WIDTH, HEIGHT = display.get_bounds()

BRIGHTNESS = 0.17 # The brightness of the LCD backlight (from 0.0 to 1.0)
display.set_backlight(BRIGHTNESS)

# See: https://doc-tft-espi.readthedocs.io/tft_espi/colors/

# Couple of colours for use later

NAVY = display.create_pen(0, 0, 128)
BLUE = display.create_pen(28, 181, 202)
ORANGE = display.create_pen(255, 180, 0)
LIGHTGREY = display.create_pen(211, 211, 211)
DARKGREY = display.create_pen(128, 128, 128)
MAGENTA = display.create_pen(255, 0, 255)
AQUA = display.create_pen(7, 255, 255)
GREENYELLOW = display.create_pen(180, 255, 0)
PINK = display.create_pen(255, 192, 203)
VIOLET = display.create_pen(180, 46, 226)
WHITE = display.create_pen(255,255,255)

BLACK = display.create_pen(0, 0, 0)
BACKGROUND = display.create_pen(255, 250, 240)

CURRENT_COLOR = ORANGE # Default

# We do a clear and update here to stop the screen showing whatever is in the buffer.
display.set_pen(BLACK)
display.clear()
presto.update()

my_debug = False
wx_test = False # Temporary to test the metar msgs
delete_logs = False
msg_rcvd = False
redraw_done = False
datetime_rcvd = ""
hh_rcvd = 0  # see: split_msg() and ...

mqtt_connected = False # Flag to indicate if the MQTT client is connected   

msg_hist_fn = "msg_hist.json"

# Create objects
sensor_obj = SensorTPAH()
toggle_obj = LightsToggle()
amb_obj    = AmbientColors()
disp_obj   = DisplayColors()
metar_obj  = Metar()

if my_debug:
    print(TAG+f"type(sensor_obj = {type(sensor_obj)})")

topic_rcvd = None
topic_idx = -1
topicIdx_max = 0

payload = None
payloadLst = []
temp = None
pres = None
alti = None
humi = None
td_default = "--:--:--"
datetime_empty = "0000-00-00T00:00:00"
ts = 0 # is a uxTime
publisher_datetime = None
publisher_time = None
publisher_msgID = None

NUM_LEDS = 7  # bl ambient neopixel leds
lights_ON = False # light toggle flag
lights_ON_old = False # remember light toggle flag state
lightsColorIdx = 3 # default ORANGE
lightsColorMin = 0
lightsColorMax = 9

lightsDclrIdx = 3 # default ORANGE
disp_color_idx_default = lightsDclrIdx # Copy
lightsDclrMin = 1
lightsDclrMax = 11
lightsDclrChanged = False

blColorsDict = {0: (20,0,255),   # BLUE
			1: (255, 255, 255),  # WHITE
			2: (255,0,0),        # RED
			3: (245, 165, 4),    # ORANGE
			4: (0,255,0),        # GREEN
			5: (250, 125, 180),  # PINK
			6: (0,255,255),      # CYAN
			7: (255,0,255),      # MAGENTA
			8: (255, 255, 0),    # YELLOW
			9: (75, 75, 75)}     # GREY

blColorNamesDict = { 0: "BLUE",
                    1: "WHITE",
                    2: "RED",
                    3: "ORANGE",
                    4: "GREEN",
                    5: "PINK",
                    6: "CYAN",
                    7: "MAGENTA",
                    8: "YELLOW",
                    9: "GREY"}

dispColorDict = { 1: (  0,   0, 128),  # NAVY
                  2: ( 28, 181, 202),  # BLUE
                  3: (255, 180,   0),  # ORANGE
                  4: (211, 211, 211),  # LIGHTGREY
                  5: (128, 128, 128),  # DARKGREY
                  6: (255,   0, 255),  # MAGENTA
                  7: (  7, 255, 255),  # AQUA
                  8: (180, 255,   0),  # GREENYELLOW
                  9: (255, 192, 203),  # PINK
                  10: (180,  46, 226), # VIOLET
                  11: (255, 255, 255)  # WHITE
}

# The first item is a dummy value
colors_lst = [0, NAVY, BLUE, ORANGE, LIGHTGREY, DARKGREY, MAGENTA, AQUA, GREENYELLOW, PINK, VIOLET, WHITE]

dispColorDict0 = {
                1: NAVY,
                2: BLUE,
                3: ORANGE,
                4: LIGHTGREY,
                5: DARKGREY,
                6: MAGENTA,
                7: AQUA,
                8: GREENYELLOW,
                9: PINK,
                10: VIOLET,
                11: WHITE
}

# sorted on hex value key
dispColorDict2 = {0x1000: 1,  # NAVY          4096 dec
                  0x1084: 5,  # DARKGREY      4228 dec
                  0x19fe: 9,  # PINK          6654 dec
                  0x1ff8: 6,  # MAGENTA       8184 dec
                  0x7cb1: 10, # VIOLET       31921 dec
                  0x9ad6: 4,  # LIGHTGREY    39638 dec
                  0xa0fd: 3,  # ORANGE       41213 dec
                  0xb91d: 2,  # BLUE         47389 dec
                  0xe0b7: 8,  # GREENYELLOW  57527 dec
                  0xff07: 7,  # AQUA         65287 dec
                  0xffff: 11  # WHITE        65535 dec 
}

dispColorNamesDict = {
                  1: "NAVY",
                  2: "BLUE",
                  3: "ORANGE",
                  4: "LIGHTGREY",
                  5: "DARKGREY",
                  6: "MAGENTA",
                  7: "AQUA",
                  8: "GREENYELLOW",
                  9: "PINK",
                  10: "VIOLET",
                  11: "WHITE"
}

err = exc.ERR(10) # create an instance of the ERR class
if err and not my_debug :
    print(TAG+f"error class object created. It is of class: {type(err)}")

def clear_broker_json():
    ret = -1
    fn = "sys_broker.json"
    if my_debug:
        print("clear_broker_json(): entering...")
    try:
        sBroker = {"sys_broker": {}}  # create a clean sBroker
        with open(fn, "w") as fp:
            fp.write(ujson.dumps(sBroker))
        ret = 1
        if not my_debug:
            print(f"file: \"{fn}\" has been reset.")
    except OSError as exc:
        print(f"Error: {exc}")
    
    return ret

# Get the external definitions
# with open('secrets.json') as fp: # method I used, manually reads file content first, then parses it
#    secrets = ujson.loads(fp.read())
clear_broker_json()
time.sleep(1)
with open('sys_broker.json') as f:  # method used by Copilot. This reads and parses in one step
    sBroker = ujson.load(f)

# "$SYS/broker/" keys in sys_broker.json are loaded
# however these keys lack the "$SYS/broker/" prefix
sysBrokerDictModified = False

sys_broker_dict = sBroker.get("sys_broker", {})

if len(sys_broker_dict) > 0:
    if not my_debug:
        print("sys_broker_dict: key, value list = ")
        for k,v in sys_broker_dict.items():
            print(f"/$SYS/broker/{k} : {v}")

with open('secrets.json') as f:  # method used by Copilot. This reads and parses in one step
    secrets = ujson.load(f)

mqtt_config_dict = secrets.get("mqtt", {})
if my_debug:
    print(TAG+f"mqtt_config_dict.items() = {mqtt_config_dict.items()}")

# MQTT setup
use_local_broker = mqtt_config_dict['use_local_broker'] # secrets['mqtt']['use_local_broker']
#print(f"type(use_local_broker) = {type(use_local_broker)}")
if my_debug:
    if use_local_broker:
        print("Using local Broker")
    else:
        print("Using external Broker")

if use_local_broker:
    BROKER = mqtt_config_dict['broker_local'] # secrets['mqtt']['broker_local']  # Use the mosquitto broker app on the RaspberryPi CM5
else:
    BROKER = mqtt_config_dict['broker_external'] # secrets['mqtt']['broker_external']
PORT = int(mqtt_config_dict['port']) # int(secrets['mqtt']['port'])

TOPIC_DICT = {}

# Loop through keys and create globals for keys starting with "topic"

for key, value in mqtt_config_dict.items():
    if key.startswith("topic"):
        tpc_idx = int(key[5:])  # Extracts everything from index 5 onward
        if my_debug:
            print(TAG+f"tpc_idx = {tpc_idx}, key = \'{key}\', value = \'{value}\'")
        #globals()[key] = value  # Dynamically assign global variable
        if tpc_idx >= 0 and tpc_idx not in TOPIC_DICT.keys():
            TOPIC_DICT[tpc_idx] = value
            if not value.startswith("$SYS"):
                topicIdx_max += 1 # global variable
            if my_debug:
                print(TAG+f"key: \'{tpc_idx}\', value: \'{value}\' added to TOPIC_DICT")
        if my_debug:
            print(f"{key} = {value}")
if not my_debug:
    print(f"topicIdx_max = {topicIdx_max}")


uxTime = 0
utc_offset = secrets['timezone']['tz_utc_offset']  # utc offset in hours
timezone = secrets['timezone']['tz'] # example: "Europe/Lisbon"
uxTime_rcvd = 0


CLIENT_ID = bytes(mqtt_config_dict['client_id'],'utf-8') # bytes(secrets['mqtt']['client_id'], 'utf-8')
if 'publisher_id0' in mqtt_config_dict.keys():
    PUBLISHER_ID0 = mqtt_config_dict['publisher_id0'] # secrets['mqtt']['publisher_id0']
else:
    PUBLISHER_ID0 = ""
    print(f"key \'publisher_id0\' not found in mqtt_config_dict.keys(): {mqtt_config_dict.keys()}")
    
if 'publisher_id1' in mqtt_config_dict.keys():
    PUBLISHER_ID1 = mqtt_config_dict['publisher_id1'] # secrets['mqtt']['publisher_id0']
else:
    PUBLISHER_ID1 = ""
    print(f"key \'publisher_id1\' not found in mqtt_config_dict.keys(): {mqtt_config_dict.keys()}")

Publisher_ID = None

display_hrs_config_dict = secrets.get("display", {})
# print(f"display_hrs_config_dict.items() = {display_hrs_config_dict.items()}")
DISPLAY_HOUR_GOTOSLEEP = display_hrs_config_dict['gotosleep']
DISPLAY_HOUR_WAKEUP = display_hrs_config_dict['wakeup']
del display_hrs_config_dict

if not my_debug:
    print(f"BROKER = {BROKER}")
    print(f"PORT = {PORT}") #, type(PORT) = {type(PORT)}")
if my_debug:
    for k,v in TOPIC_DICT.items():
      print(f"TOPIC_DICT[{k}] = {v}")
if not my_debug:
    print(f"CLIENT_ID = {CLIENT_ID}")
    # print(f"PUBLISHER_ID0 = {PUBLISHER_ID0}")
    print(f"PUBLISHER_ID1 = {PUBLISHER_ID1}")

# Test the existance of a logfile
log_fn = None # Note: log_fn is set in the function create_logfile()
log_path = None # "/sd/" + log_fn
log_size_max = 50 * 1024  # 51200 bytes # 50 kB max log file size
log_obj = None
log_exist = False
new_log_fn = None
new_log_path = None
new_log_obj = None
new_log_exist = False

def get_prefix() -> str:
    return "/sd/"

# Note: err_log_fn is used in the function create_err_log_file()
err_log_fn = "err_log.txt"
err_log_path = get_prefix() + err_log_fn
err_log_obj = None
# Note: ref_fn is used in the function create_ref_file()
ref_fn = "mqtt_latest_log_fn.txt"
ref_path = get_prefix() + ref_fn
ref_obj = None

ref_file_checked = False
log_file_checked = False

def clean(): # Clear the screen to Black
    display.set_pen(BLACK)
    display.clear() # clear background
    display.set_pen(CURRENT_COLOR) # set text
    presto.update()

def NP_clear():  # NeoPixels clear (switch off)
    TAG = "NP_clear(): "
    if not my_debug:
        print(TAG+"🌈 ambient neopixels off")
    for i in range(NUM_LEDS):
        presto.set_led_rgb(i, 0, 0, 0)
    time.sleep(0.02)
        
def NP_color():
    global lightsColorIdx, lights_ON, lights_ON_old
    TAG = "NP_color(): "
    r = g = b = 0
    if lightsColorIdx == -1: # Check if color index not is set yet
        lightsColorIdx = 0 # BLUE
    if lightsColorIdx >= lightsColorMin and lightsColorIdx <= lightsColorMax:
      if lightsColorIdx in blColorsDict.keys():
        r = blColorsDict[lightsColorIdx][0]
        g = blColorsDict[lightsColorIdx][1]
        b = blColorsDict[lightsColorIdx][2]
        if not my_debug:
            print(TAG+f"lightsColorIdx: {lightsColorIdx} = color \"{blColorNamesDict[lightsColorIdx]}\"")
            print(TAG+f"🌈 ambient neopixels color set to: r = {r}, g = {g}, b = {b}")
        for n in range(NUM_LEDS):
            presto.set_led_rgb(n, r, g, b)
        time.sleep(0.02)
        lights_ON = True # set the lights_ON flag to True
      else:
          print(f"lightColorIdx: {lightsColorIdx} not in blColorsDict.keys(): {blColorsDict.keys()}")
    else:
      NP_clear()  # Switch off
     
def NP_toggle():
    global lights_ON, lightsColorIdx
    if lights_ON:
        if lightsColorIdx == -1:
            lightsColorIdx = 0 # BLUE
        NP_color()
    else:
        NP_clear()
     
def disp_color_chg(idx) -> int:
    global lightsDclrMax, lightsDclrMin, disp_obj, CURRENT_COLOR
    TAG = "disp_color_chg(): "
    default = ORANGE # These color definitions are of type int
    new_pen_color = default
    if not my_debug:
        print(TAG+f"parameter idx = {idx}")
    if lightsDclrMin <= idx <= lightsDclrMax:  
        if idx in dispColorDict0.keys():
            new_pen_color = dispColorDict0[idx]
            if idx in dispColorNamesDict.keys():
                new_pen_color_name = dispColorNamesDict[idx]
            else:
                print(TAG+f"⚠️ param idx: {idx} not found in dispColorNamesDict.keys()")
                new_pen_color_name = "?"
            disp_obj.disp_color = new_pen_color  # CURRENT_COLOR # Save to the disp_obj
            print(TAG+f"display color (CURRENT_COLOR) changed to {hex(new_pen_color)} = {new_pen_color_name}")
            return new_pen_color
        else:
            print(TAG+f"⚠️ param idx: {idx} not found in dispColorDict0.keys()")
            return default
    else:
        print(TAG+f"⚠️ display color index {lightsDclrIdx} out of range!")
        
    return default

def do_line(nr:int = 5):
    if nr <= 0:
        return
    if nr < 5 or nr > 5:
        ln = '-' * nr
    else:
        ln = "----------" * 5
    print(ln)

def create_err_log_file():
    global err_log_fn, err_log_path, err_log_obj
    TAG = "create_err_log_file(): "
    try:
        if not ck_log(err_log_fn):
            # If the error log file does not exist, create it
            # err_log_fn = "err_log.txt"
            if err_log_obj:
                err_log_obj.close()
            with open(err_log_path, 'w') as ref_obj:
                err_log_obj.write('--- Error log file created on: {} ---\n'.format(get_iso_timestamp()))
                print(TAG+f"Error log file: \"{err_log_fn}\" created")
            if err_log_obj:
                err_log_obj.close() 
    except OSError as e:
        print(TAG+f"⚠️ OSError: {e}")

def create_ref_file():
    global ref_path, ref_obj, ref_fn
    TAG = "create_ref_file(): "
    try:
        if ref_obj:
            ref_obj.close()
        with open(ref_path, 'w') as ref_obj:
            ref_obj.write('--- Reference file created on: {} ---\n'.format(get_iso_timestamp()))
            print(TAG+f"reference file: \"{ref_fn}\" created")
    except OSError as e:
        print(TAG+f"⚠️ OSError: {e}")
        
def ref_file_exists() -> bool:
    global ref_path, ref_obj, ref_fn
    ret = False
    TAG = "ref_file_exists(): "
    try:
        if ref_obj:
            ref_obj.close()
        with open(ref_path, 'r') as ref_obj:
            ret = True
        if ref_obj:
            ref_obj.close()
    except OSError as e:
        print(TAG+f"Reference file not found or unable to open. Error: {e}")
    return ret

def clear_ref_file():
    global ref_path, ref_obj, ref_fn
    TAG = "clear_ref_file(): "
    txt1 = "reference file: "
    try:
        ref_exist = ref_file_exists() # Check if the reference file exists
        if ref_exist:
            if my_debug:
                print(TAG+txt1+f"\"{ref_fn}\" exists, making it empty")
            # If the reference file exists, make it empty
            # Note: This will overwrite the existing file, so be careful!
            if ref_obj:
                ref_obj.close()
            with open(ref_path, 'w') as ref_obj:
                pass  # Create an empty reference file
            ref_obj.close()
            ref_size = os.stat(ref_path)[6]  # File size in bytes
            if ref_size == 0:
                print(TAG+txt1+f"\"{ref_fn}\" is empty")
            else:
                print(TAG+txt1+f"\"{ref_fn}\" is not empty, size: {ref_size} bytes")
        else:
            if my_debug:
                print(TAG+txt1+f"\"{ref_fn}\" does not exist, creating it")
            create_ref_file()    
    except OSError as e:
        print(TAG+f"OSError: {e}")

def get_active_log_filename() -> str:
    global ref_path, ref_obj, ref_fn, ref_file_checked, log_fn, log_path, log_exist
    TAG = "get_active_log_filename(): "
    txt1 = "Active log "
    txt2 = "reference file"
    txt3 = "in the directory:"
    ret = ""
    active_log_fn = None
    active_log_path = None
    active_log_exist = False
    active_log_size = 0
    try:
        if ref_obj:
            ref_obj.close()
        with open(ref_path, 'r') as ref_obj:
            active_log_fn = ref_obj.readline().strip()  # Read the first line and remove trailing newline
        if ref_obj:
            ref_obj.close()
        ref_file_checked = True
        
        if active_log_fn:
            if my_debug:
              print(TAG + txt1 + f"filename read from " + txt2 + f": \"{active_log_fn}\"")
            # Check if the log file exists in the specified directory
            if active_log_fn in os.listdir(get_prefix()):
                active_log_path = get_prefix() + active_log_fn
                if my_debug:
                  print(TAG + txt1 + f"file: \"{active_log_fn}\" exists in " + txt3 + f"\"{get_prefix()}\"")
                active_log_size = os.stat(active_log_path)[6]  # File size in bytes
                if my_debug:
                  print(TAG + txt1 + f"Active log file: \"{active_log_fn}\" exists in " + txt3 + f"\"{get_prefix()}\"")
                  print(TAG+f"Active log file size: {active_log_size} bytes")
                # Set the log path and log exist flag
                active_log_path = get_prefix() + active_log_fn
                active_log_exist = True
                #ret = active_log_fn  # Return the active log filename
            else:
                print(TAG + txt1 + f"file: \"{active_log_fn}\" does not exist " + txt3 + f"\"{get_prefix()}\"")
                # If the log file does not exist, we can create a new one
                active_log_exist = False
                active_log_path = None
                active_log_fn = None
                clear_ref_file()

            ret = active_log_fn
            log_fn = active_log_fn
            log_path = active_log_path 
            log_exist = active_log_exist
        else:
            print(TAG + txt1 + "filename not found in the " + txt2)
    except OSError as e:
        print(TAG+f"⚠️ Error reading the " + txt2 + ": {e}")
    
    return ret

def pr_ref() -> int:
    global ref_path, ref_obj
    ret = 0
    TAG = "pr_ref(): "
    try:
        if ref_obj:
            ref_obj.close()
        
        if ref_path:
            if my_debug:
              print(TAG+f"Contents of ref file: \"{ref_path}\":")
            f_cnt = 0
            with open(ref_path, 'r') as ref_obj:
                for line in ref_obj:
                    f_cnt += 1
                    #f_cnt_str = "0" + str(f_cnt) if f_cnt < 10 else str(f_cnt)
                    #print(f"   {f_cnt_str}) {line.strip()}") 
                    if my_debug:
                      print("{:s} {:02d}) {:s}".format(TAG, f_cnt, line.strip())) # Remove trailing newline for cleaner output
                if my_debug:
                  do_line()
            ret = f_cnt  # Return the number of lines printed
    except OSError as e:
        print(TAG+f"⚠️ Reference file not found or unable to open. Error: {e}")
    return ret

# Function to get current datetime as an ISO string
def get_iso_timestamp() -> str:
    t = time.localtime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(*t[:6])

def new_logname() -> str:
    fn = "mqtt_log_{}.txt".format(get_iso_timestamp())
    # Replace ":" with "" for compatibility with MS Windows file systems
    return fn.replace(":", "")

def ck_log(fn) -> bool:
    if isinstance(fn, str) and len(fn) > 0:
        if fn in os.listdir(get_prefix()):
            return True
    return False

# Create a new log file and add its filename to the ref file
def create_logfile():
    global log_fn, log_path, log_obj, log_exist, ref_path, ref_obj, new_log_fn, new_log_path, new_log_obj
    TAG = "create_logfile(): "
    
    new_log_fn = new_logname()
    if not my_debug:
        print(f"new_logname() = {new_log_fn}")
    
    new_log_path = get_prefix() + new_log_fn
    try:
        if log_obj:
            log_obj.close()
        with open(new_log_path, 'w') as log_obj:
            log_obj.write('---Log created on: {}---\n'.format(get_iso_timestamp()))
        print(TAG+f"created new log file: \"{new_log_fn}\"")
        # Check existance of the new log file
        if ck_log(new_log_fn):
            print(TAG+f"check: new log file: \"{new_log_fn}\" exists")
        else:
            print(TAG+f"⚠️ check: new log file: \"{new_log_fn}\" not found!")
        # Make empty the ref file
        if ref_obj:
            ref_obj.close()
        with open(ref_path, 'w') as ref_obj: # Make empty the ref file
            pass
        if ref_obj:
            ref_obj.close()
        # Add the filename of the new logfile to the ref file
        with open(ref_path, "w") as ref_obj:
            ref_obj.write(new_log_fn)
            print(TAG+f"added to ref file: \"{ref_fn}\" the new active log filename \"{new_log_fn}\"")
            pr_ref()  # Print the contents of the ref file
    except OSError as e:
        print(TAG+f"⚠️ OSError: {e}")
    """
    if new_log_fn is not None:
        log_fn = new_log_fn # Update the global log_fn variable
    if new_log_path is not None:
        log_path = new_log_path # Update the global log_path variable
    """

# Function to close a log file that is too long
# Then create a new log file
# Add the new log filename in the ref file
def rotate_log_if_needed(show: bool = False):
    global log_path, log_fn, log_size_max, log_obj, log_exist, ref_path, ref_fn, ref_obj, new_log_fn, new_log_path, new_log_obj
    TAG = "rotate_log_if_needed(): "
    if new_log_fn is not None: # new_log_fn could have be created in the part MAIN
        if ck_log(new_log_fn):
            log_fn = new_log_fn # Update the global log_fn variable
            current_log = new_log_fn # copy the current log filename
            current_log_path = new_log_path # copy the current log path
            log_exist = True
    elif log_exist and log_fn is not None:
        current_log = log_fn # copy the current log filename
        current_log_path = get_prefix() + current_log # copy the current log path
    if current_log:
        if my_debug:
            print(TAG+f"current log filename = \"{current_log}\"")
        if ck_log(current_log):
            log_size = os.stat(current_log_path)[6]  # File size in bytes
            if my_debug or show:
                print(TAG+f"size of \"{current_log}\" is: {log_size} bytes. Max size is: {log_size_max} bytes.")
            if log_size > log_size_max:
                if my_debug:
                    print(TAG+f"Log file: \"{current_log}\" is too long, creating a new log file")
                create_logfile()
                if my_debug:
                    print(TAG+f"Current log file: \"{current_log}\" is closed")
                    print(TAG+f"Log rotated to new log file: \"{log_path}\"")  # log_fn, log_path changed in create_logfile()
            else:
                if my_debug:
                  print(TAG+"rotate log file not needed yet")
        else:
            print(TAG+f"⚠️ log_file: \"{log_fn}\" not found in listdir(\"{get_prefix()}\")")
            print(TAG+"creating a new log file")
            create_logfile() # log_fn, log_path changed in create_logfile()
    else:
        # log_fn is None
        print(TAG+"creating a new log file")
        create_logfile() # log_fn, log_path changed in create_logfile()
   
    if log_fn is None:
        print(TAG+"⚠️ Log rotation failed:")

#------------------ MAIN START HERE ------------------
# The main function is not used in this script
# but the code is structured to allow for easy integration into a larger system.
TAG = "main(): "
my_list = None 
try:
    # Note: os.listdir('/sd') and os.listdir('/sd/') have the same result! 
    # Check the existance of a reference file
    # in which we save the file name of the latest log file created
    if ref_file_exists():
        # Reference file exists;   
        # File exists; open for appending
        active_log_fn = None
        active_log_path = None
        active_log_exist = False
        ref_exist = True
        ref_size = os.stat(ref_path)[6]  # File size in bytes
        if my_debug:
            print(TAG+f"ref file: \"{ref_fn}\" exists. Size: {ref_size} bytes")
        if ref_size > 0:
            nr_log_files = pr_ref()
            if my_debug:
              print(TAG+f"Number of log files listed in reference file: {nr_log_files}")
            if nr_log_files > 0:
                # read the log filename from the reference file
                active_log_fn = get_active_log_filename()  # Get the active log filename from the reference file
                # print(TAG+f"Active log filename extracted from reference file: \"{log_fn}\"")
                if active_log_fn is None:
                    # No log filename found in the reference file
                    print(TAG+f"⚠️ No active log filename found in the reference file: \"{ref_fn}\"")
                else:
                    # Check if the active log file exists
                    if ck_log(active_log_fn):
                        active_log_path = get_prefix() + log_fn
                        active_log_exist = True
               
                # If the active log file exists, we can use it
                # Otherwise, we create a new log file
                if active_log_exist:
                    if my_debug:
                      print(TAG+f"⚠️ Active log file: \"{active_log_fn}\" does exist in the directory: \"{get_prefix()}\"")
                    active_log_path = get_prefix() + active_log_fn
                    active_log_size = os.stat(active_log_path)[6]  # File size in bytes 
                    log_fn = active_log_fn  # Update the global log_fn variable
                    log_path = active_log_path  # Update the global log_path variable
                else:
                    print(TAG+f"⚠️ Active log file: \"{active_log_fn}\" does not exist in the directory: \"{get_prefix()}\"")
                    print(TAG+f"creating a new log file")
                
                    active_log_exist = False
                    active_log_path = None
                    create_logfile()
        else:
            # There is no last log filename in the ref file.
            # Create a new log file and add to the ref file
            if log_fn and ck_log(log_fn):
                pass  # The log file exists, so we do not need to create a new one
            else:
                log_fn = new_logname() # "mqtt_log_{}.txt".format(get_iso_timestamp())
                log_path = get_prefix() + log_fn
            try:
                if ref_obj:
                    ref_obj.close()
                with open(ref_path, 'w') as ref_obj:
                    ref_obj.write(log_fn) # Add the log filename to the ref file
            except OSError as e:
                print(TAG+f"⚠️ OSError: {e}")
    else:
        # ref_fn does not exist; create and write header
        # First:  create a new log filename
        # Second: add the log filename to the ref file
        log_fn = new_logname() # "mqtt_log_{}.txt".format(get_iso_timestamp())
        log_path = get_prefix() + log_fn
        try:
            if ref_obj:
                ref_obj.close()
            with open(ref_path, 'w') as ref_obj:
                ref_obj.write('--- Reference file created on: {} ---\n'.format(get_iso_timestamp()))
                ref_obj.write(log_fn) # And add the log filename to the ref file
            ref_exist = True
            if not my_debug:
                print(TAG+f"reference file: \"{ref_path}\" created")
                print(TAG+f"current log filename: \"{log_fn}\" added to ref file")
        except OSError as e:
            print(TAG+f"⚠️ OSError: {e}")
        # rotate_log_if_needed() # create a new log file and add it to th ref file
except OSError as e:
    print(TAG+f"⚠️ OSError occurred: {e}")
    
def timestamp():
    t = time.localtime()
    tStr = "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(
        t[0], t[1], t[2], t[3], t[4], t[5])
    if my_debug:
        print(f"timestamp(): tStr = {tStr}")
    return tStr
 
# Add data to log file
def add_to_log(txt:str = ""):
    global log_exist, log_path, log_fn, log_obj, log_size_max
    TAG = "add_to_log(): "
    param_type = type(txt)
    if isinstance(txt, str):
        if len(txt) > 0:
            size = os.stat(log_path)[6]  # File size in bytes
            if size >= log_size_max:
                rotate_log_if_needed() # check if we need to create a new log file
            
            if log_obj:
                log_obj.close()
            if ck_log(log_fn):
                try:
                    ts = timestamp()
                    with open(log_path, 'a') as log_obj:  # 'a' for append mode
                        log_obj.write('\n '+ ts + " " + txt)  # Add received msg to file /sd/mqtt_log.txt
                    if my_debug:
                        print(TAG+f"data: \"{txt}\" appended successfully to the log file.")
                except OSError as e:
                    print(TAG+f"⚠️ add_to_log(): error while trying to open or write to the log file: {e}")
            else:
                print(TAG+f"⚠️ log file: \"{log_path}\" does not exist. Unable to add: \"{txt}\"")
    else:
        print(TAG+f"⚠️ parameter txt needs to be of type str, received a type: {param_type}")

if my_list:
    my_list = None # Clear memory

client = None
# Initialize the default message
payload_txt = "Waiting for Messages..."
last_update_time = time.time()
MESSAGE_DISPLAY_DURATION = 20  # Duration to display each message in seconds

# WiFi setup

# Eventually (if needed)
ssid = secrets['wifi']['ssid']
#password = secrets['wifi']['password']

print(TAG+"Connecting to WiFi...")
wifi = presto.connect()  # Ensure this is configured for your network
print(TAG+"WiFi connected.")
wifi_connected = True
add_to_log("WiFi connected to: {}".format(ssid))

msg_drawn = False

# List log files starting with "mqtt_log"
def list_logfiles():
    TAG = "list_logfiles(): "
    err_log_present = False
    if err_log_fn:
        err_log_present = ck_log(err_log_fn)
    list_log_prefix = 'mqtt_log'
    list_log_path = ""

    try:
        files = os.listdir(get_prefix())
        log_files = [f for f in files if f.startswith(list_log_prefix) and f.endswith('.txt')]
        files = None  # Clear memory
        # do_line()
        cnt = 0
        if my_debug:
          print(TAG+"MQTT log files:")
        if err_log_present:
            cnt +=1
            log_size = os.stat(err_log_path)[6]
            if my_debug:
              print("{:2d}) {}, size {} bytes".format(cnt, err_log_fn, log_size), end='\n')
        for fname in log_files:
            #if fname.beginswith(list_log_prefix) and fname.endswith('.txt'):
            cnt += 1
            #print(TAG+f"fname = \"{fname}\"")
            #if ck_log(fname):
            list_log_path = get_prefix() + fname
            log_size = os.stat(list_log_path)[6]
            if my_debug:
              print("{:2d}) {}, size {} bytes".format(cnt, fname, log_size), end='\n')
        if my_debug:
          do_line(51)
          if cnt == 0:
              print(TAG+"⚠️ No log files found starting with \"{}\"".format(list_log_prefix))
          else:
              print(TAG+"Total number of log files found: {}".format(cnt))
          do_line(51)
    except OSError as e:
        print(TAG+"⚠️ Error accessing directory:", e)

def del_logfiles():
    global ref_fn, ref_path, ref_obj, log_fn
    TAG = "del_logfiles(): "
    
    log_dir = get_prefix()
    t = time.localtime()
    # year, month, day = t[0], t[1], t[2]
    # Or even more compactly:
    yy, mo, dd, *_ = time.localtime()

    print(TAG+f"log_dir = {log_dir}")
    log_pfx = "mqtt_log_" + str(yy) + "-" + "0" + str(mo) if mo < 10 else str(mo)  # + "-" + "0" + str(dd) if dd < 10 else str(dd)  # Change to desired year-month-day
    print(TAG+f"log_pfx = {log_pfx}")
    deleted_files = []

    try:
        files = os.listdir(log_dir)
        for fname in files:
            if fname.startswith(log_pfx) and fname.endswith('.txt'):
                if my_debug:
                    print(TAG+f"fname = \"{fname}\", log_fn = \"{log_fn}\"")
                if fname in log_fn:
                    print(TAG+f"We\'re not deleting the current logfile: \"{log_fn}\"")
                    continue
                full_path = '{}/{}'.format(log_dir, fname)
                try:
                    os.remove(full_path)
                    deleted_files.append(fname)
                except OSError as e:
                    print(TAG+f"⚠️ Failed to delete: {fname}, error: {e}")

        if len(deleted_files) > 0:
            print(TAG+"Deleted files:")
            for f in deleted_files:
                print("  ✔", f)
            
            if ref_obj:
                ref_obj.close()
            with open(ref_path, 'w') as ref_obj:  # Make empty the ref file
                pass
            ref_size = os.stat(ref_path)[6]  # File size in bytes
            if my_debug:
                print(TAG+f"check ref file: \"{ref_fn}\" after making empty. Size: {ref_size} bytes")
        else:
            print(TAG+f"⚠️ no logfile(s) found starting with \"{log_pfx}\" and ending with \".txt\"")
    
    except OSError as e:
        print(TAG+f"⚠️ Could not list directory: {log_dir} for deletion. Error: {e}")
        
def save_broker_dict() -> int:
    global sBroker, sysBrokerDictModified
    ret = -1
    fn = "sys_broker.json"
    if not sysBrokerDictModified:
        return 1
    try:
        sBroker["sys_broker"] = sys_broker_dict  # Update the wrapper dict
        with open(fn, "w") as fp:
            fp.write(ujson.dumps(sBroker))
        ret = 1
    except OSError as exc:
        print(f"⚠️ Error: {exc}")
        
    if ret == 1:
        if not my_debug:
            print(f"sys_broker_dict written to file: \"{fn}\"")
        sysBrokerDictModified = False # reset flag
    return ret

def broker_topic_in_db() -> int:
    global sBroker, sys_broker_dict, topic_rcvd, payload, sysBrokerDictModified
    TAG = "broker_topic_in_db(): "
    ret = -1
    if topic_rcvd.startswith("$SYS"):
        if payload:
            # "$SYS/broker/"
            short_key = topic_rcvd[len("$SYS/broker/"):]
            if "retained messages/count" == short_key: # correct this faulty topic (containing a space)
                faulty_key = short_key
                short_key = "messages/retained/count"
                if not my_debug:
                    print(TAG+f"changing faulty key: {faulty_key} into: {short_key}")
            if short_key in sys_broker_dict.keys():
                ret = 1
                sysBrokerDictModified = True
                old_value = sys_broker_dict[short_key]
                if my_debug:
                    print(TAG+f"topic_rcvd = \"{topic_rcvd}\", key = \"{short_key}\", old value = {old_value}")
                sys_broker_dict[short_key] = payload
                new_value = sys_broker_dict[short_key]
                if my_debug:
                    print(TAG+f"topic_rcvd = \"{topic_rcvd}\", key = \"{short_key}\", value updated to: {new_value}")
            else:
                sys_broker_dict[short_key] = payload
                sysBrokerDictModified = True
                ret = 1
        else:
            print(TAG+f"msg topic: \"{topic_rcvd}\", payload empty? : {payload}")
            
        if sysBrokerDictModified:
            if my_debug:
                print(TAG+f"topic_rcvd = \"{topic_rcvd}\", short_key \"{short_key}\", added to: sys_broker_dict")
    return ret 

def topic_in_lst() -> int:
    if topic_rcvd.startswith("$SYS"):
        return 1  # Accept all topic_rcvd starting with '$SYS'
    TAG = "topic_in_lst(): "
    ret = -1
    topic_idx = 0
    le = len (TOPIC_DICT)
    if my_debug:
        print(TAG+f"TOPIC_DICT = {TOPIC_DICT.items()}")
    if le > 0:
        for k,v in TOPIC_DICT.items():
            if my_debug:
                print(TAG+f"v = {v}, topic_rcvd = {topic_rcvd}")
            if v == topic_rcvd:
                ret = k
                break
    if my_debug:
        print(TAG+f"topic received: \"{topic_rcvd}\" ", end='')
    if ret < 0:
        if my_debug:
            print(" not ", end='')
    if my_debug:
        print("found in TOPIC_DICT")
        print(TAG+f"return value = {ret}")
    return ret


# MQTT callback function
def mqtt_callback(topic: str, msg: bytes):
    global topic_rcvd, msg_rcvd, payload, last_update_time, topic_idx, redraw_done, sensor_obj, \
        toggle_obj, amb_obj, disp_obj, metar_obj, lightsDclrChanged, ts, wx_test
    TAG = "mqtt_callback(): "
    wx = False # only for weather topic
    payload = {}
    payloadStr = ""
    head = {}
    raw_msg = None
    wx = False
    use_localTime = True
    n = -1

    try:
        if wx_test:
            msg = "{\"hd\":{\"ow\":\"PL2XLW\",\"de\":\"Ext\",\"dc\":\"wx\",\"sc\":\"meas\",\"vt\":\"s\",\"t\":1755981697},\"metar\":{\"raw\":\"METAR LPPT 291930Z 34012KT CAVOK 30/10 Q1014\"}}".encode('utf-8')
            if not my_debug:
                print(TAG+f"type(msg) = {type(msg)}")
            topic = TOPIC_DICT[6] # "weather/PL2XLW/metar"
        
        if my_debug:
            print(TAG+"MQTT msg: ", repr(msg))
            print(TAG+f"topic = {topic}, type(topic) = {type(topic)}")
        
        if isinstance(topic, bytes):
            topic_rcvd = topic.decode("utf-8")
        elif isinstance(topic, str):
            topic_rcvd = topic # same
        if my_debug:
            print(TAG+f"topic_rcvd = {topic_rcvd}")
        n =  topic_in_lst()
        if n < 0:
            if not my_debug:
                print(TAG+f"⚠️ topic received {topic_rcvd} not subscribed to. Skipping...")
            return
        else:
            topic_idx = n
            if my_debug:
                print(TAG+f"topic_idx set to: {topic_idx}")
      
        if my_debug:
            print(TAG+f"type(msg): {type(msg)}")

        if isinstance(msg, bytes):
            if wx_test:
                payload = ujson.loads('{"hd":{"ow":"PL2XLW","de":"Ext","dc":"wx","sc":"meas","vt":"s","t":1755981697}, \
                    "metar":{"raw":"METAR LPPT 261030Z 33010KT 290V360 9999 FEW025 24/15 Q1015"}}')
            else:
                msg_decd = msg.decode("utf-8")
                payload = ujson.loads(msg_decd)
            if my_debug:
                print(TAG+f"payload: {payload}")
            if isinstance(payload, dict):
                head = payload.get("hd")
            if my_debug:
                print(TAG+f"head: {head}")
      
        if my_debug:
            print(TAG+f"type(payload): {type(payload)}")
            #print(TAG+"MQTT payload: ", repr(payload))
      
        if topic_rcvd.startswith("sensors"):
            pass
        elif topic_rcvd.startswith("lights"):
            pass
        elif topic_rcvd.startswith("weather"):
            wx = True
            if isinstance(payload, str):
                payloadStr = payload
            elif isinstance(payload, bytes):
                payloadStr = payload.decode("utf-8")
        elif topic_rcvd.startswith("$SYS"):
            if my_debug:
                print(TAG+f"$SYS msg, type(payload): {type(payload)}")
            if isinstance(payload, int):
                payloadStr = str(payload)
            if broker_topic_in_db():
                if not my_debug:
                    print(TAG+f"$SYS topic_rcvd: \"{topic_rcvd}\", payloadStr: \"{payloadStr}\"")
                return
        else:
            payload = None
            print(TAG+f"Incomplete message \"{msg}\" received, skipping.")
            return

        if len(head) > 0:
            ts = head.get("t", datetime_empty) # get the uxTime
        else:
            ts = datetime_empty
        if wx:
            use_localTime = False
        if not my_debug:
            print("\n"+TAG+f"Received a mqtt message on topic: \"{topic_rcvd}\", timestamp: {ts} = ", end='')
            print(f"{unixToIso8601(ts, use_localTime)}") # all types of messages, convert ts to local time
            #if wx:
            #    print(f"{unixToIso8601(ts, use_localTime)}")
            #else:
            #    print(f"{convert_to_dtStr(ts)}")
        if my_debug:
            print(f"msg: {msg}")
        if len(msg) > 0:
            print(TAG+f"length of received mqtt message: {len(msg)}")
            # ------------------ MESSAGE RECEIVE FLAG ----------------------------+
            msg_rcvd = True #                                                     |
            # --------------------------------------------------------------------+
            # If a new message received, switch off an eventually active lightsDclrChanged flag
            if topic_rcvd.startswith("lights") and (topic_rcvd.endswith("dclr_dec") or topic_rcvd.endswith("dclr_inc")):
                print(TAG+f"display color change message received")
                lightsDclrChanged = True
                disp_obj.disp_color_changed = lightsDclrChanged  # update the flag in the disp_obj
            else:
                lightsDclrChanged = False
                disp_obj.disp_color_changed = lightsDclrChanged  # update the flag in the disp_obj
        if my_debug:
            if wx_test:
                raw_msg = payload
            else:
                raw_msg = msg.decode('utf-8')
            print(TAG+f"Decoded raw_msg length: {len(raw_msg)}")
            if isinstance(raw_msg, dict):
                print(TAG+f"raw_msg keys: {raw_msg.keys()}")
            print(TAG+f"raw_msg: {raw_msg}") # may reveal the broken JSON
    except ValueError as e:
        print(TAG+f"⚠️ ValueError while decoding JSon msg: {e}")
        raise RuntimeError
    except Exception as e:
        print(TAG+"⚠️ Unhandled exception:", str(e))
        raise RuntimeError

def uxMinimum(yr1970: bool = True):
    if yr1970:
        return  0   #  = 1970-01-01, 1970 0:00:00 UTC
    else:
        return -2208988800 # = 1900-01-01 00:00:00 UTC

def uxMaximum():
    return 2147483647 # 2038-01-19 03:14:07 UTC (maximum value for a signed integer 32-bit number)

def convert_to_dtStr(uxTime) -> str:
    # print(f"convert_to_dtStr(): type(uxTimeS) = {type(uxTime)}")
    if not isinstance(uxTime, int):
        return datetime_empty
    if uxTime <= uxMinimum() or uxTime >= uxMaximum():  # max for 32-bit
        return datetime_empty
    # Convert to local time tuple
    t = time.gmtime(uxTime) # do not use time.localtime(uxTime) because we end up in Lisbon time +1 = Amsterdam time
    # Format as ISO 8601 string: YYYY-MM-DDTHH:MM:SS
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(
            t[0], t[1], t[2], t[3], t[4], t[5])


def unixToIso8601(unixTime, local: bool=False) -> str:

    global utc_offset  # Assumed to be a string like "-3.5"
    TAG = "get_iso8601(): "

    # Convert offset to float
    if local:
        offset = float(utc_offset)
    else:
        offset = 0  # UTC (GMT) time
    if my_debug:
        print(TAG + f"type(utc_offset) = {type(utc_offset)}")

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

# Called from redraw()
def format_sensor_value(payload, key):
    svDict = {"t":"TEMPERATURE", "p":"PRESSURE", "a":"ALTITUDE", "h":"HUMIDITY"}
    unit = payload[key]["u"]
    value = round(float(payload[key]["v"]), 2)
    return f"{svDict[key]}: {value} {unit}"

def save_to_obj(topIdx: int = 0, topic: str = "", payload: dict = {}) -> bool:
    global sensor_obj, toggle_obj, amb_obj, disp_obj, metar_obj
    TAG = "save_to_obj(): "
    ret = False
    # Copy doc to respective class object
    if topIdx < 0 or topIdx >= topicIdx_max:
        print(TAG+f"⚠️ param topicIdx out of range. Exiting...")
        return ret
    #if len(topic) == 0:
    #    print(TAG+f"⚠️ param topic is empty. Exiting...")
    #    return ret
    
    if not isinstance(payload, dict):
        print(TAG+f"⚠️ param payload is not a dict. Exiting...")
        return ret
    else:
        if len(payload) > 0:
            head = payload.get("hd")
    
    if topIdx == 0:
        obj = sensor_obj
        pl =  payload.get("reads")
    elif topIdx == 1:
        obj = toggle_obj
        pl = payload.get("toggle")
    elif topIdx in (2,3):
        obj = amb_obj
        if topIdx == 2:
            pl = payload.get("colorInc")
        elif topIdx == 3:
            pl = payload.get("colorDecc")
    elif topIdx in (4,5):
        obj = disp_obj
        if topIdx == 4:
            pl = payload.get("dclrInc")
        elif topIdx == 5:
             pl = payload.get("dclrDec")
    elif topIdx == 6:
        obj = metar_obj
        pl = payload.get("metar")
        if my_debug:
            print(TAG+f"payload.get(\'metar\') = {pl}")

    if my_debug:
        print(TAG+f"type(obj) = {type(obj)}")
        
    obj.head = head
    obj.topic = topic
    obj.topicIdx = topIdx
    obj.payload = pl
    
    return True

def pr_obj(topIdx: int = 0):
    global sensor_obj, toggle_obj, amb_obj, disp_obj, metar_obj
    TAG = "pr_obj(): "
    obj = None
    t = ""
    # Copy doc to respective class object
    if topIdx < 0 or topIdx >= topicIdx_max:
        print(TAG+f"⚠️ param topIdx out of range. Exiting...")
        return False
    
    if topIdx == 0:
        obj = sensor_obj
        t = "sensor"
  
    elif topIdx == 1:
        obj = toggle_obj
        t = "toggle"

    elif topIdx in (2,3):
        obj = amb_obj
        t = "amb"
 
    elif topIdx in (4,5):
        obj = disp_obj
        t = "disp"

    elif topIdx == 6:
        obj = metar_obj
        t = "metar"

    print(TAG+f"type({t}_obj)    = {type(obj)}")
    print(TAG+f"{t}_obj.topicIdx = {obj.topicIdx}")
    print(TAG+f"{t}_obj.topic    = {obj.topic}")
    print(TAG+f"{t}_obj.head     = {obj.head}") 
    print(TAG+f"{t}_obj.payload  = {obj.payload}")
    

def get_disp_color_index(color: int=0) -> int:
    global disp_color_idx_default
    TAG = "get_disp_color_index(): "
    color2 = 0
    dispColorIdx = 0
    if color == 0:
        color2 = disp_obj.disp_color_index
    else:
        color2 = color
    if color2 in dispColorDict2.keys():
        dispColoIdx = dispColorDict2[CURRENT_COLOR]
    
    if my_debug:
        print(TAG+f"param color = {color}, return value = {dispColoIdx}")
    return dispColorIdx

def split_msg():
    global topic_rcvd, payload, payloadLst, Publisher_ID, Publisher_ID0, Publisher_ID1, lightsColorIdx, lights_ON, lights_ON_old, lightsColorMax, \
        lightsColorMin, lightsDclrIdx, lightsDclrMax, lightsDclrMin, lightsDclrChanged, CURRENT_COLOR, datetime_rcvd, hh_rcvd, \
        sensor_obj, toggle_obj, amb_obj, disp_obj, metar_obj
    
    TAG = "split_msg(): "
    topic_found = False
    wx = None
    
    try:
        topicIdx = -1
        for k,v in TOPIC_DICT.items():
            if topic_rcvd == v:
                topicIdx = k
                break
        if topicIdx >= 0:
            if my_debug:
                print(TAG+f"Topic rcvd: \'{topic_rcvd}\' found in TOPIC_DICT: \'{TOPIC_DICT[topicIdx]}\', topicIdx = {topicIdx}")
            topic_found = True
        else:
            print(TAG+f"⚠️ topic rcvd: \'{topic_rcvd}\' not in TOPIC_DICT: \'{TOPIC_DICT.items()}\'")
        
        if not topic_found:
            return 
      
        owner = None
        device_class = None
        uxTime = None
        head = {}
                
        # Step 1. Check if payload is not None
        if payload is None:
            print(TAG+"⚠️ payload is None, skipping further processing.")
            return
        
        if my_debug:
            print(TAG+f"type global param payload = {type(payload)}")
        
        # Step 1.1 Check is payload is of type dictionary
        if isinstance(payload, dict):
            # Step 1.2: Check if the payload dictionary is empty
            le = len(payload)
            if le > 0:
                if my_debug:
                    print(TAG+f"len(payload) = {len(payload)}")
                    print(TAG+f"payload.items() = {payload.items()}")
                # Step 1.3 Get the header nested JSon object      
                head = payload.get("hd", {})
                if not isinstance(head, dict):
                    print(TAG+f"⚠️ head is of type: {type(head)}. Exiting...")
                    return
                if my_debug:
                  print(TAG+f"type(head) = {type(head)}, len(head) = {len(head)}")
                  print(TAG+f"head = {head}")
            else:
                print(TAG+"⚠️ Received an empty payload, skipping further processing.")
                return
        # When payload is an integer
        elif isinstance(payload, int):  # This happens with $SYS topic messages
            if not my_debug:
                print(TAG+f"payload = {payload}") # . Line 1359")
        
        payloadLst = []
        datetime = datetime_empty
        
        if topicIdx == 6:
            wx = payload.get("metar", "?")
            if not my_debug:
                print(TAG+f"wx = {wx}") #. Line 1367")
        #if topic_rcvd == TOPIC_DICT[6] # "weather/PL2XLW/metar":
        #    pass
        #else:
        if not isinstance(head, dict):
            print(TAG+f"⚠️ head is of type: {type(head)}. Exiting...")
            return
        else:
            # Step 2: Pull shared metadata 
            for key, value in head.items():
                if my_debug:
                    print(TAG+f"{key}: {value}")
                
                if key == "ow" :
                    owner = value # was: payload.get("ow", "?")
                    if owner == "unknown":
                        Publisher_ID = PUBLISHER_ID0  # if "unknown" we use the definition from secret.json
                    else:
                        Publisher_ID = owner  # use the owner from the payload
                        # Step 2: Pull shared metadata
                
                    lbl_k = key
                    lbl_v = value
                    output = {lbl_k: lbl_v}
                    payloadLst.append(output)
                
                if key == "de":  # description     
                    description = value # payload.get("de", "unknown")
                    lbl_k = key
                    lbl_v = value # Example: "PC-Lab" or "Lab"
                    output = {lbl_k: lbl_v}
                    payloadLst.append(output)
                
                if key == "dc":  # device class
                    lbl_k = key
                    device_class = value # payload.get("dc", "unknown")
                    if device_class == "BME280":
                        lbl_v = device_class
                    elif device_class == "home":
                        lbl_v = device_class
                    elif device_class == "colr":
                        lbl_v = "color"
                    elif device_class == "dclr":
                        lbl_v = "dcolor"
                    elif device_class == "wx":
                        lbl_v = "weather"
                    else:
                        lbl_v = device_class
                    output = {lbl_k: lbl_v}
                    payloadLst.append(output)
                
                if key == "sc":
                    lbl_k = key
                    state_class = value # payload.get("sc", "unknown") # == "measure":
                    if state_class == "meas":
                        state_class = "measurement"
                    elif state_class == "inc":
                        state_class = "incr"
                    elif state_class == "dec":
                        state_class = "decr"
                    elif state_class == "ligh":
                        state_class = "lights"
                    else:
                        state_class = "unknown"
            
                    lbl_v = state_class
                    output = {lbl_k: lbl_v}
                    payloadLst.append(output)
                
                if key == "vt":
                    lbl_k = key
                    vt = value # payload.get("vt") # "vt" stands for value term
                    if vt == "f":
                        lbl_v = "float"
                    elif vt == "i":
                        lbl_v = "int"
                    elif vt == "s":
                        lbl_v = "str"
                    elif vt == "b":
                        lbl_v = "bool"
                    output = {lbl_k: lbl_v}
                    payloadLst.append(output)
                
                if key == "t":
                    uxTime = value # payload.get("t", "unknown")
                
                    if uxTime <= uxMinimum() or uxTime >= uxMaximum(): # max for 32-bit
                        uxTimeStr = "invalid"
                    else:
                        uxTimeStr = str(uxTime)
                    
                    if my_debug:
                        print(TAG+f"uxTime = {uxTime}")
                    if uxTime == 0:
                        datetime = datetime_empty  # Default to 0 if unknown
                    else: 
                        #datetime = convert_to_dtStr(uxTime)
                        datetime = unixToIso8601(uxTime, True) # convert to local time
                        datetime_rcvd = datetime # make a global copy
                        if my_debug:
                            print(TAG+f"datetime = {datetime}")
                        n = datetime.find("T")
                        if n >= 0:
                            timeStr = datetime[n+1:]
                            if my_debug:
                                print(TAG+f"timeStr = {timeStr}")
                            hh_rcvd = int(timeStr[:2]) # make a global copy
                            if my_debug:
                                print(TAG+f"hh_rcvd = {hh_rcvd}")
                                
                    lbl_k = key
                    lbl_v = uxTimeStr
                    output = {lbl_k: lbl_v}
                    payloadLst.append(output)
                    
                    if my_debug:
                        print(TAG+f"Received msg from: {owner}, timestamp: {uxTime}") # was: "timestamp"

                if my_debug:
                    print(TAG+f"owner: {owner} [{device_class}], timestamp: {uxTime}")
          
        if topicIdx == 0: # sensors/Feath/ambient
            # Step 3: Extract and flatten "reads"
            readings = payload.get("reads", {})
            if readings is not None:
              if isinstance(readings, dict):
                # sensor_obj.payload = readings # Store payload <<<=== moved to end of this function
                for key, data in readings.items():
                    label = key # key.upper()
                    value = data.get("v", "??")
                    unit = data.get("u", "")
                    
                    # min_val = data.get("mn", "?")
                    # max_val = data.get("mx", "?")
    
                    lbl_k = None
                    lbl_v = None
                    
                    if label == "t":
                        t1 = "Temperature: "
                        lbl_k = "temp"
                        if vt == "f":
                            lbl_v = t1 + "{:4.1f} °C".format(value) # + str(value) + " °C"
                        elif vt == "i":
                            lbl_v = t1 + str(value) + " °C"
                        elif vt == "s":
                            lbl_v = t1 + value + " °C"
                    elif label == "p":
                        t1 = "Pressure: "
                        lbl_k = "pres"
                        if vt == "f":
                            lbl_v = t1 + "{:6.1f} {:s}".format(value, unit)
                        elif vt == "i":
                            lbl_v = t1 + str(value) + unit
                        elif vt == "s":
                            lbl_v = t1 + value + unit
                    elif label == "a":
                        t1 = "Altitude: "
                        lbl_k = "alti"
                        if vt == "f":
                            lbl_v = t1 + "{:5.1f} {:s}".format(value, unit)
                        elif vt == "i":
                            lbl_v = t1 + str(value) + unit
                        elif vt == "s":
                            lbl_v = t1 + value + unit
                    elif label == "h":
                        t1 = "Humidity: "
                        lbl_k = "humi"
                        if vt == "f":
                            lbl_v = t1 + "{:5.1f} {:s}".format(value, unit)
                        elif vt == "i":
                            lbl_v = t1 + str(value) + unit
                        elif vt == "s":
                            lbl_v = t1 + value + unit
                    output = {lbl_k: lbl_v}
                    payloadLst.append(output)
                
                if not my_debug:
                    print(TAG+"header fields:")
                    print(TAG+f"owner:        {owner}")
                    print(TAG+f"description:  {description}")
                    print(TAG+f"device_class: {device_class}")
                    print(TAG+f"state_class:  {state_class}")
                    print(TAG+f"msgID:        {uxTime}")
                    #print(TAG+f"in ISO8601:   {convert_to_dtStr(uxTime)}") # show in Local time
                    print(TAG+f"in ISO8601:   {unixToIso8601(uxTime, True)}") # show in Local time
                if my_debug:
                    print(TAG+"Reads fields")
                    print(f"payloadLst: {payloadLst}")
                if my_debug:
                    # Copy the contents of payloadLst to a temperary dict: t_db
                    t_db = {}
                    for r in payloadLst:
                        # print(TAG+f"payloadLst[r] = {r}")
                        for k,v in r.items():
                            t_db[k] = v  # Add a key and value to the temporary dict
                    if len(t_db) > 0:
                        # print(TAG+f"t_db.items() = {t_db.items()}")
                        # print(TAG+f"t_db.values() = {t_db.values()}")
                        for k,v in t_db.items():
                            print(TAG+f"t_db[{k}] = {v}") # print the contents of the temporary dict
                
                    
        elif topicIdx == 1: # lights/Feath/toggle:
            """ 
            Example output of code below:
            split_msg(): toggle payload.keys() = dict_keys(['u', 'mx', 'mn', 'v'])
            split_msg(): toggle payload.items() = dict_items([('u', 'i'), ('mx', 0), ('mn', 1), ('v', 0)])
            split_msg():  key =  u, data =  i
            split_msg():  key = mx, data =  0
            split_msg():  key = mn, data =  1
            split_msg():  key =  v, data =  0
            """
            toggle_mx_val = None
            toggle_mn_val = None
            unit = None
            value = None
            toggle = payload.get("toggle", {})  # "toggle":{"v":0,"u":"i","mn":1,"mx":0}
            if toggle:
              if isinstance(toggle, dict):
                # toggle_obj.payload = toggle # Store payload  <<<=== moved to end of this function
              
                if my_debug:
                    print(TAG+f"toggle payload.keys() = {toggle.keys()}")
                    print(TAG+f"toggle payload.items() = {toggle.items()}")
                
                for key, data in toggle.items():
                    if my_debug:
                        if isinstance(data, int):
                            print("{:s} key = {:>2s}, data = {:>2d}".format(TAG, key, data))
                        elif isinstance(data, str):
                            print("{:s} key = {:>2s}, data = {:>2s}".format(TAG, key, data))
                    if key == "u": # unit of measurement
                        unit = data
                    elif key == "mx":
                        toggle_mx_val = data
                    elif key == "mn":
                        toggle_mn_val = data
                    if key == "v": # value
                        if unit == "i":
                            value = data
                        elif unit == "s":
                            value = int(data)
                        lights_ON = True if value == 1 else False # set the global lights_ON flag
                        toggle_obj.lights_toggle = value # set the object
                        if lights_ON != lights_ON_old:  # Only change if value differs from last received value
                            print(TAG+f"toggling ambient light neopixel leds {'on' if lights_ON == True else 'off'}")
                            #lights_ON_old = lights_ON
                            if lights_ON:
                                NP_color()  # Switch bl leds off
                            else:
                                NP_clear()  # Switch bl leds on and set color of lightsColorIdx
                        else:
                            print(TAG+f"not toggling ambient light neopixel leds. lights_ON = {lights_ON}, lights_ON_old = {lights_ON_old}")
        elif topicIdx in (2, 3):  # lights/Feath/color_inc or color_dec
            if not lights_ON:
                return
            if isinstance(payload, dict):
                colorData = payload.get("colorInc") if topicIdx == 2 else payload.get("colorDec")
                if isinstance(colorData, dict):
                    # amb_obj.payload = colorData # Store payload <<<=== moved to the end of this function  
                    if my_debug:
                        print(TAG + f"colorData payload.items() = {colorData.items()}")
                  
                    for key, data in colorData.items():
                        if my_debug:
                            if isinstance(data, int):
                                print(TAG + "key = {:>2s}, data = {:>2d}".format(key, data))
                            elif isinstance(data, str):
                                print(TAG + "key = {:>2s}, data = {:>2s}".format(key, data))

                        if key == "u":  # unit of measurement
                            unit = data
                        elif key == "mx":
                            lightsColorMax = data
                        elif key == "mn":
                            lightsColorMin = data
                        elif key == "v":  # value
                            if unit == "i":
                                value = data
                            elif unit == "s":
                                value = int(data)

                            if my_debug:
                                print(TAG + f"value = {value}, lightsColorMin = {lightsColorMin}, lightsColorMax = {lightsColorMax}")
                          
                            if lightsColorMin <= value <= lightsColorMax:
                                lightsColorIdx = value
                                # Save new lightsColorIdx in amb_obj
                              
                                if my_debug:
                                    print(TAG + f"lightsColorIdx set to: {lightsColorIdx}")
                                NP_color()
                            else:
                                lightsColorIdx = lightsColorMin+1 # not black!
                            amb_obj.amb_color_current = lightsColorIdx
        elif topicIdx in (4, 5):  # lights/Feath/dclr_inc or dclr_dec
            #if not lights_ON:
            #    return
            if isinstance(payload, dict):
                dColorData = payload.get("dclrInc") if topicIdx == 4 else payload.get("dclrDec")
                # print(TAG + f"type(dColorData) = {type(dColorData)}")
                if isinstance(dColorData, dict):
                    # disp_obj.payload = dColorData # Store payload <<<=== moved to the end of this function
                    if not my_debug:
                        print(TAG + f"dColorData payload.items() = {dColorData.items()}")
                
                    for key, data in dColorData.items():
                        if my_debug:
                            if isinstance(data, int):
                                print(TAG + "key = {:>2s}, data = {:>2d}".format(key, data))
                            elif isinstance(data, str):
                                print(TAG + "key = {:>2s}, data = {:>2s}".format(key, data))

                        if key == "u":  # unit of measurement
                            unit = data
                        elif key == "mx":
                            lightsDclrMax = data
                        elif key == "mn":
                            lightsDclrMin = data
                        elif key == "v":  # value
                            if unit == "i":
                                value = data
                            elif unit == "s":
                                value = int(data)

                            if not my_debug:
                                print(TAG + f"value = {value}, lightsDclrMin = {lightsDclrMin}, lightsDclrMax = {lightsDclrMax}")
                            if lightsDclrMin <= value <= lightsDclrMax:
                                lightsDclrIdx = value
                                if not lightsDclrChanged: # Can be set in mqtt_callback()
                                    lightsDclrChanged = True
                                if lightsDclrIdx == -1:
                                    print(TAG+f"⚠️ lightsDClrIdx = {lightsDclrIdx}. Unacceptable. Going to change to 2 (BLUE)")
                                    lightsDclrIdx = 2 # BLUE
                                if not my_debug:
                                    print(TAG+f"going to call disp_color_chg() with new color index: {lightsDclrIdx}")
                                CURRENT_COLOR_IDX = get_disp_color_idx()
                                if not my_debug:
                                    print(TAG+f"CURRENT_COLOR_IDX (from get_disp_color_idx() = {hex(CURRENT_COLOR_IDX)})")
                                if lightsDclrIdx != CURRENT_COLOR_IDX:
                                    CURRENT_COLOR = disp_color_chg(lightsDclrIdx)
                                else:
                                    CURRENT_COLOR = disp_color_chg(CURRENT_COLOR_IDX)
                                # Save the the new CURRENT_COLOR in the disp.obj
                                # disp_obj.disp_color = CURRENT_COLOR  # Moved to function () disp_color_chg()
                                if not my_debug:
                                    print(TAG + f"lightsDclrIdx set to: {lightsDclrIdx}")
                                    current_color_to_name(TAG)
                                    print(TAG+f"CURRENT_COLOR changed to: {hex(CURRENT_COLOR)} = {dispColorNamesDict[lightsDclrIdx]}")
                                    # dispColorDict2[lightsDclrIdx]
                else:
                    print(TAG+f"⚠️ not handling: type(dColorData) = {type(dColorData)}")
        elif topic_idx == 6:
            metarData = payload.get("metar")
            for key, data in metarData.items():
                if my_debug:
                    if isinstance(data, str):
                        print(TAG + "key = {:s}, data = {:s}".format(key, data))
                lbl_k = key
                if key == "raw":
                    lbl_v = data
                    break # "metar" has only one key: "raw"
            output = {lbl_k: lbl_v}
            payloadLst.append(output)
            if my_debug:
                print(TAG+"metar fields:")
                print(f"payloadLst: {payloadLst}")
                
        # Copy payload to respective class object
        if payload is not None:
            if isinstance(payload, dict):
                # Add new key, topicIdx pair to mqtt messages history dict
                if my_debug:
                    pr_obj(topicIdx)
                
                if len(payload) > 0:
                    try:
                        # Save to object (for example sensor_obj)
                        if my_debug:
                            print(TAG+f"payload = {payload}")
                        save_to_obj(topicIdx, topic_rcvd, payload)
                        if clean_file_if_too_large():
                            print(TAG+f"✅ Cleanup messages history file successful")
                        else:
                            print(TAG+f"🧹 Not needed to cleanup messages history file")
                        
                        if prep_and_save_record_to_sd(topicIdx, uxTime):
                            print(TAG+"✅ record saved to file on SD")
                        else:
                            print(TAG+f"⚠️ Failed to save record onto SD")
                        # And check the save
                        if my_debug:
                            # Search the file on SD-card for the latest record for this topicIdx
                            # record = find_record_by_topicIdx(topicIdx) # alternative method
                            record = find_latest_by_topic(topicIdx)
                            if isinstance(record, dict):
                                if len(record) > 0:
                                    print(TAG+f"✅ Last record read from SD: {record}")
                    except ValueError as e:
                        print(TAG+f"ValueError: {e}")
                        raise RuntimeError
                    except Exception as e:
                        print(TAG+f"error: {e}")
                        raise RuntimeError
            else:
                print(TAG+f"type(head) = {type(head)}")
                print(TAG+f"type(payload) = {type(payload)}")
        else:
            print(TAG+f"payload is {type(payload)}")
    
    except ValueError as e:
        print(TAG+f"ValueError: {e}")
        raise RuntimeError
    except AttributeError as e:
        print(TAG+f"AttibuteError: {e}")
        raise RuntimeError
    except Exception as e:
        print(TAG+f"Other Exception error: {e}")
        raise RuntimeError
    
def get_payload_member(key):
    global payloadLst, topic_idx
    TAG = "get_payload_member(): "
    if isinstance(payloadLst, list):
        if len(payloadLst) > 0:
            for entry in payloadLst:
                if my_debug:
                    print(TAG+f"entry: {entry}, payloadLst: {payloadLst}")
                if key in entry:
                    if my_debug:
                        print(TAG+f"key \'{key}\' found in entry {entry}")
                    return entry[key]
                else:
                    if my_debug:
                        print(TAG+f"⚠️ key \'{key}\' not found in entry {entry}")
                        
    return ""  # if key not found

def current_color_to_name(tg):
    TAG = "current_color_to_name(): "
    if tg is None:
        tg = ""
    if my_debug:
        print(TAG+f"CURRENT_COLOR = {CURRENT_COLOR} dec = {hex(CURRENT_COLOR)} hex")
        print(TAG+f"dispColorDict2.keys() = {dispColorDict2.keys()}")
    if CURRENT_COLOR in dispColorDict2.keys():
        dispColorDict2_value = dispColorDict2[CURRENT_COLOR]
        if my_debug:
          print(TAG+"called from: "+tg)
          print(TAG+f"lightsDclrIdx = {lightsDclrIdx}")
          print(TAG+f"dispColorDict2_value = {dispColorDict2_value}")
        if dispColorDict2_value in dispColorNamesDict.keys():
            dispColorNamesDict_value = dispColorNamesDict[dispColorDict2_value]
            if my_debug:
              print(TAG+f"CURRENT_COLOR = {dispColorNamesDict_value}")
        else:
            print(TAG+f"⚠️ index: {dispColorDict2_value} not found in: {dispColorNamesDict.keys()}")
    else:
        print(TAG+f"⚠️ CURRENT_COLOUR: {CURRENT_COLOR} not found in: {dispColorDict2.keys()}")


# 🔍 2. Find Latest Record by TopicIdx
def find_latest_by_topic(topic_idx: int = 0) -> dict:
    TAG = "find_latest_by_topic(): "
    file_path = get_prefix() + msg_hist_fn
    latest_record = None  # Start with None for clarity

    try:
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue  # Skip empty lines
                try:
                    record = ujson.loads(line)
                    if record.get("topicIdx") == topic_idx:
                        if (latest_record is None) or (record["t"] > latest_record["t"]):
                            latest_record = record
                except Exception as parse_err:
                    print(TAG + f"⚠️ Parse error: {parse_err}")
    except Exception as read_error:
        print(TAG + f"⚠️ Error reading from SD: {read_error}")

    return latest_record or {}

# 🧹 3. Clean File if Record Count > 180 but leave only 20
def clean_file_if_too_large(max_records: int = 180, retain_records: int = 20) -> bool:
    TAG = "clear_file_if_too_large(): "
    file_path = get_prefix() + msg_hist_fn
    ret = False
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()

        total_records = len(lines)
        print(TAG + f"received msg records on file: {total_records}")
        
        if total_records >= max_records:
            # Parse each line into a dict
            records = [ujson.loads(line) for line in lines]

            # Keep only the latest `retain_records` entries
            records = records[-retain_records:]

            # Write back as JSON lines
            with open(file_path, "w") as f:
                for record in records:
                    f.write(ujson.dumps(record) + "\n")

            print(TAG + f"✅ File cleaned. Retained last {retain_records} records.")
            ret = True
    except Exception as e:
        print(TAG + f"⚠️ Error cleaning file: {e}")
    return ret


# 📁 1. Write a Record to SD File
def prep_and_save_record_to_sd(topIdx: int = 0, uxTime: int = 0) -> bool:
    global sensor_obj, toggle_obj, amb_obj, disp_obj, metar_obj
    TAG = "prep_and_save_record_to_sd(): "
    ret = False
    obj = None
    topic = None
    topicIdx = None
    head = None
    payload = None
    dtStr = ""
    # rcvd_iso = ""
    # yy = mm = dd = hh = mi = ss = 0
    record = {}
    json_str = ""
    file_path = ""
    f = None
    
    if topIdx < 0 or topIdx >= topicIdx_max:
        print(TAG+"⚠️ topicIdx is out of range. Exiting...")
        return ret
    
    if topIdx == 0:
        obj = sensor_obj
    elif topIdx == 1:
        obj = toggle_obj
    elif topIdx in (2,3):
        obj = amb_obj
    elif topIdx in (4,5):
        obj = disp_obj
    elif topIdx == 6:
        obj = metar_obj
    
    topic    = obj.topic
    topicIdx = obj.topicIdx
    head     = obj.head
    payload  = obj.payload
    
    if head is None:
        print(TAG+f"⚠️ head is None! Exiting...")
        return ret
    if not isinstance(head, dict):
        print(TAG+f"⚠️ head is not a dict! Exiting...")
        return ret
        
    if uxTime > 0:
        dtStr = convert_to_dtStr(uxTime)
    if my_debug:
        print(TAG+f"dtStr = {dtStr}")
    
    record = {
        "topic": topic,
        "topicIdx": topicIdx,
        "t": uxTime,
        "rcvd": dtStr,
        "hd": head,
        "payload": payload
    }

    json_str = ujson.dumps(record)
    file_path = get_prefix() + msg_hist_fn # "msg_hist.json"
    if not my_debug:
        print(TAG+f"Attempting to write to file: \'{file_path}\'")

    try:
        with open(file_path, "a") as f:
            f.write(json_str + "\n")
            ret = True
    except OSError as e:
        print(TAG+f"⚠️ Failed to write to SD: {e}")
        # Optional: log to fallback memory, blink LED, or retry later
    except Exception as e:
        print(TAG+f"⚠️ Error: {e}")
    return ret

def get_disp_color_idx(color: int = ORANGE) -> int:
    global disp_color_idx_default
    TAG = "get_disp_color_idx(): "
    pen_colorIdx = disp_color_idx_default
    if color == 0:
        return pen_colorIdx # 
    else:
        if color in dispColorDict2.keys():
            pen_colorIdx = dispColorDict2[color]
            if not my_debug:
                print(TAG+f"pen_colorIdx set to: {pen_colorIdx}")
    return pen_colorIdx

def set_disp_color(hh: int = 0, time_draw: str = "--:--:--"):
    global td_default, CURRENT_COLOR
    TAG = "set_disp_color(): "
    # if hh == 0 and time_draw == td_default, we are obviously in a boot/reset phase
    # for this we set the color to ORANGE.
    # When the first MQTT message arrive, the right time will be set
    # and the text (display) color will be set accordingly
    # Example of situation after a first MQTT message has been received:
    # set_disp_color(): hh = 14, time_draw = '14:46:52', td_default = '--:--:--'
    if  (hh >= DISPLAY_HOUR_WAKEUP and hh < DISPLAY_HOUR_GOTOSLEEP) or \
        (hh == 0 and time_draw == td_default):
        if my_debug:
            print(TAG+f"hh = {hh}, time_draw = \'{time_draw}\', td_default = \'{td_default}\'")
        if CURRENT_COLOR is None:
            CURRENT_COLOR = ORANGE
        else:
            CURRENT_COLOR = disp_obj.disp_color
        display.set_pen(CURRENT_COLOR)
        disp_obj.disp_color = CURRENT_COLOR
        disp_obj.disp_color_changed = True
        if not my_debug:
            current_color_to_name(TAG)
    else:
        CURRENT_COLOR = NAVY
        display.set_pen(CURRENT_COLOR)
        disp_obj.disp_color = CURRENT_COLOR
        disp_obj.disp_color_changed = True

# Function to redraw the screen with already received and displayed data,
# however a display color change command could have been received,
# so we want to redraw the screen in the new display color
def redraw() -> bool:
    global payload_txt, payloadLst, msg_drawn, Publisher_ID, publisher_time, publisher_msgID, topic_idx, \
        lights_ON, lights_ON_old, CURRENT_COLOR, lightsDclrChanged, lightsColorIdx, lightsDclrIdx, \
        lightsDclrMax, lightsDclrMin, td_default, redraw_done
    TAG = "redraw(): "
    ret = False
    x = 10
    y = 25
    line_space = 30
    margin = 10
    hdg = "MQTT " # pub : "
    latest_uxTime = 0
    latest_topicIdx = -1
    record = {}
    
    latest_topicIdx = 0 # force to topic 0

    record = find_latest_by_topic(latest_topicIdx) # force topic 0     was: (topIdx_found)

    if isinstance(record, dict):
        latest_uxTime = record["t"]
        if my_debug:
            print(TAG+f"✅ latest record on topic: {latest_topicIdx}, record: {record}")
    else:
        print(TAG+f"⚠️ record is not of type dict but of type: {type(record)}. Exiting...")
        return ret
    
    if latest_uxTime > 0:
        dtStr = record["rcvd"]
        #dtStr = convert_to_dtStr(latest_uxTime)
        if isinstance(dtStr, str):
            if len(dtStr) > 0:
                n = dtStr.find("T")
                if n >= 0:
                    time_draw = dtStr[n+1:]
                else:
                    time_draw = td_default
            else:
                time_draw = td_default
        else:
            time_draw = td_default # Also used for setting the day or night text colour
        if not my_debug:
            print(TAG+f"time from latest mqtt msg with uxTime: {latest_uxTime} = {time_draw}")
    else:
        print(TAG+f"⚠️ latest_uxTime: {latest_uxTime}. Exiting...")
        return ret
    
    if latest_topicIdx == -1:
        print(TAG+f"⚠️ latest_topicIdx: {latest_topicIdx}. Exiting...")
        return ret
        
    topIdx = latest_topicIdx 

    if topIdx == 0:
        if not isinstance(record, dict):
            print(TAG+f"⚠️ record is not a dict. Exiting...")
            return ret
        else:
            dtStr_rcvd = record["rcvd"]
            
            head = record["hd"]
            if not isinstance(head, dict):
                print(TAG+f"⚠️ head is not a dictionary. Exiting ...")
                return ret
    
            payload = record["payload"]    
            if not isinstance(payload, dict):
                print(TAG+f"⚠️ payload is not a dictionary. Exiting ...")
                return ret

            # using var names "top" and "topIdx" to keep local,
            # to not mix with global variables "topic" and "topicIdx"
            top = record["topic"]
            topIdx = record["topicIdx"]
            
            ow_draw = head["ow"] # Feath
            sc = head["sc"]      # measurement
            dc_draw = head["dc"] # BME280
            de_draw = head["de"] # Lab
            vt = head["vt"]      # float
            uxTime = head["t"]   # 1755776794
            
            temp_draw = format_sensor_value(payload, "t")  # Temperature: 31.1 °C
            pres_draw = format_sensor_value(payload, "p")  # Pressure: 1004.1 mB
            alti_draw = format_sensor_value(payload, "a")   # Altitude: 101.1 m
            humi_draw = format_sensor_value(payload, "h")   # Humidity:  49.7
            
            print(TAG+f"Topic = \'{top}\', topicIdx = {topIdx}")
            
        display.set_font("font14_outline")  # was ("bitmap8")
        # As soon as I changed line 36 into: presto = Presto(full_res=True), the interpreter gave the error: "set_layer: layer out of range!"
        if not full_res:
            display.set_layer(1)
            # Clear the screen with a black background
        
        # Get the changed color value from the disp_obj
        # Assuming that the display text color already has been set
        # at moment of boot/reset and by receiving a first MQTT message of topicIdx = 0
        CURR_COLOR = disp_obj.disp_color
        if my_debug:
            print(TAG+f"CURR_COLOR fm disp_obj.disp_color = {CURR_COLOR}")
        if CURR_COLOR in dispColorDict2.keys():
            if my_debug:
                print(TAG+f"CURR_COLOR found in dispColorDict2.keys()")
            pen_colorIdx = dispColorDict2[CURR_COLOR]
            if my_debug:
                print(TAG+f"pen_colorIdx = {pen_colorIdx}")
            if pen_colorIdx in dispColorNamesDict.keys():
                if my_debug:
                    print(TAG+f"pen_colorIdx found in dispColorNamesDict.keys()")
                pen_color_name = dispColorNamesDict[pen_colorIdx]
                if my_debug:
                    print(TAG+f"pen_color_name (new) = {pen_color_name}")
        else:
            pen_color_name = ""
        
        if my_debug:
            print(TAG+f"CURR_COLOR = {CURR_COLOR} = {hex(CURR_COLOR)} hex, color: {pen_color_name}")
        
        display.set_pen(BLACK)
        display.clear() # clear background
        display.set_pen(CURR_COLOR) # set text
        presto.update()
        
        my_scale = 2
        y = 25 # restart y position
        display.text("RD", WIDTH-40, y, WIDTH, scale = my_scale) # Indicate that this is a Redraw'n screen
        display.text(hdg + " " + time_draw, x, y, WIDTH, scale = my_scale)
        y += line_space
        display.text(ow_draw + " " + de_draw + " " + dc_draw, x, y, WIDTH, scale = my_scale)
        y += line_space
        display.text("msgID: " + time_draw, x, y, WIDTH, scale = my_scale)
        y += line_space
        if my_debug:
            print(TAG+f"topic_idx: {topIdx} = topic: \"{top}\"") # TOPIC_DICT[topIdx]}\"")
        display.text(temp_draw, x, y, WIDTH, scale = my_scale)
        y += line_space
        display.text(pres_draw, x, y, WIDTH, scale = my_scale)
        y += line_space
        display.text(alti_draw, x, y, WIDTH, scale = my_scale)
        y += line_space
        display.text(humi_draw, x, y, WIDTH, scale = my_scale)
        
        presto.update()
        
        if not my_debug:
            print(TAG+f"{temp_draw}")
            print(TAG+f"{pres_draw}")
            print(TAG+f"{alti_draw}")
            print(TAG+f"{humi_draw}")
        ret = True

        if not my_debug:
            do_line()
        
        utime.sleep(3)
        redraw_done = True
        
    return ret

def draw(mode:int = 1):
    global payload_txt, payloadLst, msg_drawn, Publisher_ID, publisher_time, publisher_msgID, topic_idx, \
        lights_ON, lights_ON_old, disp_obj, CURRENT_COLOR, lightsDclrChanged, lightsColorIdx, lightsDclrIdx, \
        lightsDclrMax, lightsDclrMin, td_default
    TAG = "draw(): "
 
    if isinstance(datetime_rcvd, str):
        if len(datetime_rcvd) > 0:
            n = datetime_rcvd.find("T")
            if n >= 0:
                time_draw = datetime_rcvd[n+1:]
            else:
                time_draw = td_default
        else:
            time_draw = td_default
    else:
        time_draw = td_default # Also used for setting the day or night text colour
    if my_debug:
        print(TAG+f"time derived from datetime_rcvd = {time_draw}")
    
    if hh_rcvd is not None:
        if isinstance(hh_rcvd, int):
            time_draw_hh = hh_rcvd
        elif isinstance(hh_rcvd, str):
            time_draw_hh = int(hh_rcvd)
        else:
            time_draw_hh = 0    
    else:
        time_draw_hh = 0
    #if not msg_rcvd:
    #    print("draw(): no message received. Exiting this function...")
    #    return
    
    display.set_font("font14_outline")  # was ("bitmap8")
    # As soon as I changed line 36 into: presto = Presto(full_res=True), the interpreter gave the error: "set_layer: layer out of range!"
    if not full_res:
        display.set_layer(1)

    # Clear the screen with a black background
    #display.set_pen(BLACK)  # Black background
    #display.clear()
    if not lightsDclrChanged:
        clean()

    # Display the message
    # See: https://doc-tft-espi.readthedocs.io/tft_espi/colors/
    # NOTE: NAVY gives less brightness than ORANGE
    if my_debug:
        print(TAG+f"topic_idx = {topic_idx}")

    hh = time_draw_hh
    
    if my_debug:
        print(TAG+f"hh = {hh}")
    
    CURRENT_COLOR = disp_obj.disp_color # get the current display color
    set_disp_color(hh, time_draw)
    presto.update() # to activate the new display text color
    
    x = 10
    y = 25
    line_space = 30
    margin = 10
    
    hdg = "MQTT " # pub : "
    display.text(hdg, x, y, WIDTH)
    if not lightsDclrChanged:
        if wifi_connected:
            display.text("Wi-Fi OK", 10, 120, WIDTH) # scale=2)
        if mqtt_connected:
            display.text("MQTT OK",  10, 140, WIDTH) # scale=2)
    #display.text("hh = " + str(hh),  10, 160, WIDTH) # scale=2)
    #display.text(hdg + Publisher_ID, 10, 25, WIDTH)
    if my_debug:
        print(TAG+f"msg_rcvd = {msg_rcvd}, lightsDclrChanged = {lightsDclrChanged}")
    if msg_rcvd or lightsDclrChanged:
        if not lightsDclrChanged:
            clean()
        if my_debug:
            print(TAG+f"type(hh_rcvd) = {type(hh_rcvd)}, hh_received = {hh_rcvd}")
        if  hh_rcvd is not None:
            if isinstance(datetime_rcvd, int):
                time_draw_hh = hh_rcvd
        else:

            time_draw = get_payload_member("t")
            if my_debug:
                print(TAG+f"time_draw = {time_draw}")
            if time_draw != td_default: # "--:--:--"
                if my_debug:
                    print(TAG+f"type(time_draw) = {type(time_draw)}, time_draw = \'{time_draw}\'")
                if isinstance(time_draw, str):
                    if len(time_draw) >= 3:
                        time_draw_hh = int(time_draw[:2])
                    else:
                        time_draw_hh = 0
                else:
                    time_draw_hh = 0
            else:
                time_draw_hh = 0
    
        hh = time_draw_hh
        
        if my_debug:
            print(TAG+f"datetime_rcvd = {datetime_rcvd}, datetime_empty = {datetime_empty}")
            print(TAG+f"hh = {hh}, DISPLAY_HOUR_WAKEUP = {DISPLAY_HOUR_WAKEUP}, DISPLAY_HOUR_GOTOSLEEP = {DISPLAY_HOUR_GOTOSLEEP}")

        display.text(hdg, 10, 25, WIDTH)
        set_disp_color(hh, time_draw)
        
    y += line_space
    
    if mode == 0:
        # Word wrapping logic
        words = payload_txt.split()  # Split the message into words
        current_line = ""  # Start with an empty line
        
        for word in words:
            test_line = current_line + (word + " ")
            line_width = display.measure_text(test_line)

            if line_width > WIDTH - margin:
                display.text(current_line.strip(), x, y, WIDTH)
                y += line_space
                current_line = word + " "  # Start a new line with the current word
            else:
                current_line = test_line

        if current_line:
            display.text(current_line.strip(), x, y, WIDTH)
        
        y += line_space
            
    elif mode == 1: # do the PaulskPt method
        try:
            #                                             Examples:
            # Read the "doc" members
            #if topic_idx != 6:
            ow_draw = get_payload_member("ow")        # → "Feather" or "UnoR4W" (or use the global var PUBLISHER_ID)
            de_draw = get_payload_member("de")        # → "Lab"
            dc_draw = get_payload_member("dc")        # → "BME280", "home", "colr", "colr"
            # sc_draw = get_payload_member("sc");     # → "meas", "ligh", "inc", "dec"
            timestamp_draw = get_payload_member("t")  # → "1748945128" = Tue Jun 03 2025 10:05:28 GMT+0000
            
            if topic_idx == 0:
                temp_draw = get_payload_member("temp")    # → "Temperature: 30.3 °C"
                pres_draw = get_payload_member("pres")    # → "Pressure: 1002.1 rHa"
                alti_draw = get_payload_member("alti")    # → "Altitude: 93.3m"
                humi_draw = get_payload_member("humi")    # → "Humidity: 42.2 %rH"
            elif topic_idx == 1:
                toggle_draw1 = "lights_ON = {:s},".format("Yes" if lights_ON else "No") #  get_payload_member("v")
                toggle_draw2 = "lights_ON_old = {:s}".format("Yes" if lights_ON_old else "No")
                if lights_ON != lights_ON_old:
                    lights_ON_old = lights_ON
                if not my_debug:
                    print(TAG+f"toggle_draw1 = {toggle_draw1}")
                    print(TAG+f"toggle_draw2 = {toggle_draw2}")
            elif topic_idx in (2,3):
                print(TAG+f"topic_idx = {topic_idx}, lighstColorIdx = {lightsColorIdx}")
                if lightsColorIdx == -1:
                    lightsColorIdx = 0  # change to BLUE
                color_txt1_draw = "lightsColorIdx = {:d}".format(lightsColorIdx)
                if lightsColorIdx in blColorNamesDict.keys():
                    color_txt2_draw = blColorNamesDict[lightsColorIdx]
                else:
                    color_txt2_draw = ""
                if topic_idx == 2:
                    t2 = "inc"
                elif topic_idx == 3:
                    t2 = "dec"
                if not my_debug:
                    print(TAG+f"color_txt1_draw = \"{color_txt1_draw}\"")
                    print(TAG+f"color_txt2_draw = \"{color_txt2_draw}\"")
            elif topic_idx == (4,5):
                dclr_txt1_draw = "lightsDclrIdx = {:d}".format(lightsDclrIdx)
                print(TAG+f"topic_idx = {topic_idx}, lighstDclrIdx = {lightsDclrIdx}")
                if lightsDclrIdx in dispColorNamesDict.keys():
                    dclr_txt2_draw = dispColorNamesDict[lightsDclrIdx]
                else:
                    print(TAG+f"lightsDclrIdx: {lightsColorIdx} not found in dispColorNamesDict")
                    dclr_txt2_draw = ""
                if topic_idx == 4:
                    t2 = "inc"
                elif topic_idx == 5:
                    t2 = "dec"
                if not my_debug:
                    print(TAG+f"dclr_txt1_draw = \"{dclr_txt1_draw}\"")
                    print(TAG+f"dclr_txt2_draw = \"{dclr_txt2_draw}\"")
            elif topic_idx == 6:
                if my_debug:
                    print(TAG+"we passed here. line 1938. topic_idx = 6 (metar)")
                wx_metar_txt_draw = get_payload_member("raw")  # msg['metar']['raw']
                if not my_debug:
                    print(TAG+f"wx_metar_txt_draw = \"{wx_metar_txt_draw}\"")
                    
            else:
                return # No valid topic_idx
            
            my_scale = 2
            y = 25 # restart y position
            
            if not lightsDclrChanged:
                clean()
            
            display.set_pen(CURRENT_COLOR)
            display.text(hdg + " " + time_draw, x, y, WIDTH, scale = my_scale)
            y += line_space
            if topic_idx == 6:
                display.text(TOPIC_DICT[topic_idx], x, y, WIDTH, scale = my_scale)        
            else:
                display.text(ow_draw + " " + de_draw + " " + dc_draw, x, y, WIDTH, scale = my_scale)
            y += line_space
            display.text("msgID: " + timestamp_draw, x, y, WIDTH, scale = my_scale)
            if topic_idx != 6:
                y += line_space  # no more line space below msgID for METAR topic
            if my_debug:
                print(TAG+f"topic_idx: {topic_idx} = topic: \"{TOPIC_DICT[topic_idx]}\"")
            if topic_idx == 0: # sensors/Feath/ambient
                display.text(temp_draw, x, y, WIDTH, scale = my_scale)
                y += line_space
                display.text(pres_draw, x, y, WIDTH, scale = my_scale)
                y += line_space
                display.text(alti_draw, x, y, WIDTH, scale = my_scale)
                y += line_space
                display.text(humi_draw, x, y, WIDTH, scale = my_scale)
                if not my_debug:
                    print(TAG+f"{temp_draw}")
                    print(TAG+f"{pres_draw}")
                    print(TAG+f"{alti_draw}")
                    print(TAG+f"{humi_draw}")
            elif topic_idx == 1: # lights/Feath/toggle
                display.text(toggle_draw1, x, y, WIDTH, scale = my_scale)
                y += line_space + 5
                display.text(toggle_draw2, x, y, WIDTH, scale = my_scale)
                y += line_space
                if my_debug:
                    print(TAG+f"{toggle_draw1}")
                    print(TAG+f"{toggle_draw2}")
            elif topic_idx in (2,3): # lights/Feath/color_inc or lights/Feath/color_dec
                display.text(color_txt1_draw, x, y, WIDTH, scale = my_scale) 
                y += line_space + 5
                display.text(color_txt2_draw, x, y, WIDTH, scale = my_scale)
                y += line_space
                if not my_debug:
                    print(TAG+f"{color_txt1_draw}")
                    print(TAG+f"{color_txt2_draw}")
                if not lights_ON:
                    display.text("Remote: press Btn B!", x, y, WIDTH, scale = my_scale)
            elif topic_idx in (4,5): # lights/Feath/dclr_inc or lights/Feath/dclr_dec
                display.text(dclr_txt1_draw, x, y, WIDTH, scale = my_scale) 
                y += line_space + 5
                display.text(dclr_txt2_draw, x, y, WIDTH, scale = my_scale)
                y += line_space
                if not my_debug:
                    print(TAG+f"{dclr_txt1_draw}")
                    print(TAG+f"{dclr_txt2_draw}")
                #if not lights_ON:
                #    display.text("Remote: press Btn B!", x, y, WIDTH, scale = my_scale)
            elif topic_idx == 6:
                y += line_space #  + 5
                # payload: '{"metar": {"raw": "METAR LPPT 310100Z 33007KT CAVOK 27/11 Q1015"}}'
                n1 = wx_metar_txt_draw.find("Z")
                n2 = wx_metar_txt_draw.find("Q")
                t1 = ""
                t2 = ""
                t3 = ""
                if n1 >= 0:
                    # Split the payload (metar raw)
                    t1 = wx_metar_txt_draw[:n1+1]
                if n2 >= 0:
                    t2 = wx_metar_txt_draw[n1+2:n2]  # skip the space after 'Z'
                    t3 = wx_metar_txt_draw[n2:]
                
                if n1 >= 0 and n2 >= 0:
                    display.text(t1, x, y, WIDTH, scale = my_scale)
                    y += line_space + 5
                    display.text(t2, x, y, WIDTH, scale = my_scale)
                    y += line_space + 5
                    display.text(t3, x, y, WIDTH, scale = my_scale)
                    if not my_debug:
                        print(TAG+f"{t1}")
                        print(TAG+f"{t2}")
                        print(TAG+f"{t3}")
                elif n1 >= 0 and n2 < 0:
                    display.text(t1, x, y, WIDTH, scale = my_scale)
                    if not my_debug:
                        print(TAG+f"{t1}")
                    y += line_space + 5
                else:
                    display.text(wx_metar_txt_draw, x, y, WIDTH, scale = my_scale)
                    if not my_debug:
                        print(TAG+f"{wx_metar_txt_draw}")
                y += line_space
        except Exception as e:
            print(TAG+f"error: {e}")
            raise
    
    presto.update()
    
    msg_drawn = True
    
    if not my_debug:
        do_line()

def print_file_contents(tag, file_path, file_label):
    try:
        file_size = os.stat(file_path)[6]
        if file_size > 0:
            print(f"Size of {file_label}: {file_size}.")
            print(f"Contents of {file_label}: \"{file_path}\"")
            with open(file_path, 'r') as file_obj:
                for i, line in enumerate(file_obj, start=1):
                    print(f"{tag} {i:02d}) {line.strip()}")
            do_line()
        else:
            print(tag + f"{file_label} \"{file_path}\" is empty")
    except OSError as e:
        print(tag + f"⚠️ {file_label} not found or unable to open. Error: {e}")
        
def pr_log():
    global log_path, log_obj, log_size_max
    TAG = "pr_log(): "
    sys_broker_path = "/sys_broker.json" # get_prefix() + "sys_broker.json"

    # Print sys_broker.json contents
    print_file_contents(TAG, sys_broker_path, "sys_broker json file")

    # Close log object if open
    if log_obj:
        log_obj.close()

    # Print log file contents
    print_file_contents(TAG, log_path, "log file")


def cleanup():
    global ref_exist, ref_obj, ref_path, log_exist, log_obj, log_path, lightsDclrChanged
    if ref_obj: # and ref_path is not None and ref_exist:
        ref_obj.close()
    if log_obj: # and log_path is not None and log_exist:
        log_obj.close()
    #display.set_pen(ORANGE)

# Reset the redraw flags (see loop() part)
def clean_rd():
    global lightsDclrChanged, redraw_done
    lightsDclrChanged = False
    redraw_done = False

def setup():
    global client, CLIENT_ID, BROKER, PORT, TOPIC0, TOPIC1, TOPIC2, TOPIC3, msg_drawn, mqtt_connected, lights_ON, lights_ON_old, \
        CURRENT_COLOR, disp_obj
    # MQTT client setup
    TAG = "setup(): "

    if not ck_log(err_log_fn):  # Check if the error log file exists
        print(TAG+f"Error log file: \"{err_log_fn}\" does not exist, creating it")
        create_err_log_file()
    
    
    # print(TAG+"Switching ambient light neopixel leds off")
    lights_ON = False
    toggle_obj.lights_toggle = False
    
    lights_ON_old = False
    NP_clear()
    
    disp_obj.disp_color = CURRENT_COLOR # Save to the disp_obj
    disp_obj.disp_color_index = get_disp_color_idx(CURRENT_COLOR)
    if not my_debug:
        print(TAG+f"disp_obj.disp_color_index = {disp_obj.disp_color_index}")
    
    if not my_debug:
        print(TAG+f"Display hours wakeup: {DISPLAY_HOUR_WAKEUP}, gotosleep: {DISPLAY_HOUR_GOTOSLEEP}")
    
    #rx_bfr=1024  # ← Increase to 1024 or higher
    #print(TAG+f"Connecting to MQTT broker at {BROKER} on port {PORT}") # , recv_buffer {rx_bfr}")
    print(TAG+f"Connecting to MQTT {"local" if use_local_broker else "external"} broker on port {PORT}") # , recv_buffer {rx_bfr}")
    
    client = MQTTClient(CLIENT_ID, BROKER, port=PORT) #, recv_buffer=rx_bfr)
    
    client.set_callback(mqtt_callback)
    #display.clear()
    clean()
    if delete_logs:
        del_logfiles() # for test
    else:
        print(TAG+f"Not deleting log files, flag: \"delete_logs\" = {"True" if delete_logs else "False"}")
    try:
        client.connect()
        mqtt_connected = True
        print(TAG+f"Successfully connected to MQTT broker.") # at {BROKER}.")
        add_to_log("Connected to MQTT broker: {}".format(BROKER))
        for k,v in TOPIC_DICT.items():
            client.subscribe(v)
            if my_debug:
                print(TAG+f"Subscribed to topic: \'{v}\'")
            add_to_log("Subscribed to topic: \'{}\'".format(v))
        msg_drawn = False
        # As soon as I changed line 36 into: presto = Presto(full_res=True), the interpreter gave the error: "set_layer: layer out of range!"
        if not full_res:
            display.set_layer(0)
        #display.set_pen(display.create_pen(0, 0, 0))  # Black background
        #display.clear()
        #presto.update()
        clean()
        
    except Exception as e:
        if e.args[0] == 113: # EHOSTUNREACH
            t = f"⚠️ Failed to reach the host with address: {BROKER} and port: {PORT}"
            print(TAG+f"{t}")
            add_to_log(t)
            mqtt_connected = False
        else:
            print(TAG+f"Failed to connect to MQTT broker: {e}")
            mqtt_connected = False
    except KeyboardInterrupt as e:
        print(TAG+f"⚠️ KeyboardInterrupt. Exiting...\n")
        add_to_log("Session interrupted by user — logging and exiting.")
        cleanup()
        pr_ref()
        pr_log()
        raise

# -------------Here begins the "loop()" part: ---------------------------
# def main():
# global client, msg_rcvd, last_update_time, publisher_msgID
# for compatibility with the Presto "system" the line "def main()" and below it the "globals" line have been removed
rotate_log_if_needed() # check if we need to create a new log file
list_logfiles()
setup()
draw(0) # Ensure the default message "Waiting for Messages..." is displayed
TAG = "loop(): "
start_t = time.time()
current_t = start_t
elapsed_t = 0
interval_t = 5 * 60  # Interval to check for call rotate_log_if_needed() in seconds (300 seconds = 5 minutes)

save_broker_dict_interval_t = 15 * 60 # 15 minutes
save_broker_dict_start_t = 0
save_broker_dict_curr_t = 0
save_broker_dict_elapsed_t = 0

msg_rx_timeout_interval_t = 3 * 60 # 3 minutes
msg_rx_timeout_start_t = start_t # same as start_t
msg_rx_timeout_curr_t = 0
msg_rx_timeout_elapsed_t = 0
msg_rx_timeout = False
last_triggered = -1
show_size = True  # Show the size of the current log file
while True:
    try:
        current_t = time.time()
        elapsed_t = current_t - start_t
        
        save_broker_dict_elapsed_t = save_broker_dict_curr_t - save_broker_dict_start_t
        if save_broker_dict_elapsed_t >= save_broker_dict_interval_t:
            save_broker_dict_start_t = save_broker_dict_curr_t
            save_broker_dict()
            
        if my_debug:
            if elapsed_t % 10 == 0 and (elapsed_t != last_triggered or last_triggered == -1):
                last_triggered = elapsed_t
                print(TAG+f"elapsed_t = {elapsed_t:.2f} seconds")
                # print(TAG+f"current_t = {current_t}, start_t = {start_t}, elapsed_t = {elapsed_t:.2f} seconds")
        if elapsed_t >= interval_t:
            start_t = current_t  # Reset the start time
            # Check if we need to create a new log file
            # and show the size of the current log file
            rotate_log_if_needed(show=show_size)
            show_size = not show_size  # Toggle the display of the log file size  
        
        # Wait for MQTT messages (non-blocking check)
        while True:
   
            msg_rx_timeout_current_t = time.time()
            client.check_msg()
            # print(TAG+"we passed the client.check_msg(). Line 2687")
            if msg_rcvd:
                msg_rx_timeout_start_t = msg_rx_timeout_current_t # update the start time
                break
            if lightsDclrChanged:
                break
            msg_rx_timeout_elapsed_t = msg_rx_timeout_current_t - msg_rx_timeout_start_t
            if msg_rx_timeout_elapsed_t >= msg_rx_timeout_interval_t:
                msg_rx_timeout_start_t = msg_rx_timeout_current_t
                msg_rx_timeout = True
                break
        
        if msg_rx_timeout:
            msg_rx_timeout = False # reset flag
            print(TAG+"⚠️ msg rx timedout!")
            continue # loop

        # Refresh the display periodically

        if msg_rcvd:
            split_msg()
            if lightsDclrChanged and not redraw_done:
                redraw()
       
            if not my_debug:
                if publisher_msgID:
                    print(TAG+f"MQTT message received from: {publisher_msgID}")
                else:
                    print(TAG+f"MQTT message received")

            if not redraw_done: # do not call draw when redraw was called
                draw(1) # Display the new message in mode "PaulskPt"
            clean_rd() 
            # msg_rcvd = False
        elif time.time() - last_update_time > MESSAGE_DISPLAY_DURATION:
            # clean_rd()
            draw(1)  # Refresh the screen with the current message
            last_update_time = time.time()
        if msg_rcvd:
            # Cleanup
            if my_debug:
                print(TAG+"Cleaning up:")
            cleanup()
            msg_rcvd = False # reset this flag
    
    except OSError as e:
        print(TAG+f"OSError occurred (Lost connection with MQTT Broker? {e})")
        raise RuntimeError
    except Exception as e:
        if e.args[0] == 103:
            print(TAG+f"⚠️ Error ECONNABORTED") # = Software caused connection abort
            # add_to_log(e)
            err.log(e) # print exception to the err.log
            print(TAG+f"Reconnecting to MQTT broker...")
            setup()
            #cleanup()
            #raise RuntimeError
        elif e.args[0] == 104: # ECONNRESET
            print(TAG+f"⚠️ Error ECONNRESET") # = Software caused connection abort
            # sys.print_exception(e)
            #add_to_log(e)
            err.log(e) # print exception to the err.log
            print(TAG+f"Reconnecting to MQTT broker...")
            setup()
        else:
            print(TAG+f"⚠️ Error: {repr(e)}")
            print(TAG+f"Error: {e}")
            #err_txt = f"Error while waiting for MQTT messages:"
            #if my_debug:
            #    print(TAG+f"{err_txt} {e}")
            #else:
            #    print(TAG+f"{err_txt} {e.__class__.__name__}: {e}")
            err.log(e) # print exception to the err.log
            cleanup()        
            raise RuntimeError
    except KeyboardInterrupt as e:
        print(TAG+f"⚠️ KeyboardInterrupt: exiting...\n")
        # sys.print_exception(e)
        # err.log(e)
        add_to_log("Session interrupted by user — logging and exiting.")
        save_broker_dict()
        cleanup()
        pr_ref()
        pr_log()
        raise

# for compatibility with the Presto "system" the next two lines have been commented out
# if __name__ == '__main__':
#   main()
