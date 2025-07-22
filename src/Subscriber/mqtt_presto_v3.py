# 2025-06-17 Downloaded from: https://github.com/digitalurban/Presto_MQTT_Display/blob/main/mqtt_presto.py
# by Andy Hudson-Smith going by @digitalurban
# Changes by Paulus Schulinck going by @PaulskPt
# Version 3.0  created on 2026-07-19.
# Includes handling mqtt messages with topics:
#         sensors/Feath/ambient,
#         lights/Feath/toggle,
#         lights/Feath/color_inc and
#         lights/Feath/color_dec
# Added functions to control the 7 ambient backlight LEDs
# by means of MQTT messages sent by a remote MQTT Publisher device.
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


# Couple of colours for use later
BLACK = display.create_pen(0, 0, 0)
NAVY = display.create_pen(0, 0, 128)
ORANGE = display.create_pen(255, 180, 0)
LIGHTGREY = display.create_pen(211, 211, 211)
DARKGREY = display.create_pen(128, 128, 128)
BACKGROUND = display.create_pen(255, 250, 240)

# We do a clear and update here to stop the screen showing whatever is in the buffer.
display.set_pen(BLACK)
display.clear()
presto.update()

my_debug = False
delete_logs = False
msg_rcvd = False
mqtt_connected = False # Flag to indicate if the MQTT client is connected   

_M_ID = 0
_VAL = 1
_TM = 2

topic_rcvd = None
topic_idx = -1

payload = None
payloadLst = []
temp = None
pres = None
alti = None
humi = None
datetime_empty = "0000-00-00T00:00:00"
publisher_datetime = None
publisher_time = None
publisher_msgID = None

NUM_LEDS = 7  # bl ambient neopixel leds
lights_ON = False # light toggle flag
lights_ON_old = False # remember light toggle flag state
lightsColorIdx = -1
lightsColorMin = 0
lightsColorMax = 9

blColorsDict = {0: (20,0,255),       # BLUE
			1: (255, 255, 255),  # WHITE
			2: (255,0,0),       # RED
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
   
err = exc.ERR(10) # create an instance of the ERR class
if err and not my_debug :
    print(TAG+f"error class object created. It is of class: {type(err)}")

# Get the external definitions
with open('secrets.json') as fp:
    secrets = ujson.loads(fp.read())

# MQTT setup
use_local_broker = secrets['mqtt']['use_local_broker']
#print(f"type(use_local_broker) = {type(use_local_broker)}")
if use_local_broker:
    print("Using local Broker")
else:
    print("Using external Broker")

if use_local_broker:
    BROKER = secrets['mqtt']['broker_local']  # Use the mosquitto broker app on the RaspberryPi CM5
else:
    BROKER = secrets['mqtt']['broker_external']
PORT = int(secrets['mqtt']['port'])

TOPIC_LST = []
for i in range(4):
    topicStr = "topic" + str(i)
    #TOPIC_LST.append(bytes(secrets['mqtt'][topicStr], 'utf-8')) 
    TOPIC_LST.append(secrets['mqtt'][topicStr]) 

CLIENT_ID = bytes(secrets['mqtt']['client_id'], 'utf-8')
PUBLISHER_ID = secrets['mqtt']['publisher_id']

if my_debug:
    print(f"BROKER = {BROKER}")
    print(f"PORT = {PORT}, type(PORT) = {type(PORT)}")
    for i in range(len(TOPIC_LST)):
      print(f"TOPIC_LST[{i}] = {TOPIC_LST[i]}")
    print(f"CLIENT_ID = {CLIENT_ID}")
    print(f"PUBLISHER_ID = {PUBLISHER_ID}")

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

def get_prefix():
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
    display.clear()
    presto.update()

def NP_clear():  # NeoPixels clear (switch off)
    TAG = "NP_clear(): "
    if not my_debug:
        print(TAG+"🌈 ambient neopixels off")
    for i in range(NUM_LEDS):
        presto.set_led_rgb(i, 0, 0, 0)
    time.sleep(0.02)
        
def NP_color():
    global lightsColorIdx
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
        print(TAG+f"OSError: {e}")

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
        print(TAG+f"OSError: {e}")
        
def ref_file_exists():
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

def get_active_log_filename():
    global ref_path, ref_obj, ref_fn, ref_file_checked, log_fn, log_path, log_exist
    TAG = "get_active_log_filename(): "
    txt1 = "Active log "
    txt2 = "reference file"
    txt3 = "in the directory:"
    ret = None
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
        print(TAG+f"Error reading the " + txt2 + ": {e}")
    
    return ret

def pr_ref():
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
        print(TAG+f"Reference file not found or unable to open. Error: {e}")
    return ret

# Function to get current datetime as an ISO string
def get_iso_timestamp():
    t = time.localtime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(*t[:6])

def new_logname():
    fn = "mqtt_log_{}.txt".format(get_iso_timestamp())
    # Replace ":" with "" for compatibility with MS Windows file systems
    return fn.replace(":", "")

def ck_log(fn):
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
            print(TAG+f"check: new log file: \"{new_log_fn}\" not found!")
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
        print(TAG+f"OSError: {e}")
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
            print(TAG+f"log_file: \"{log_fn}\" not found in listdir(\"{get_prefix()}\")")
            print(TAG+"creating a new log file")
            create_logfile() # log_fn, log_path changed in create_logfile()
    else:
        # log_fn is None
        print(TAG+"creating a new log file")
        create_logfile() # log_fn, log_path changed in create_logfile()
   
    if log_fn is None:
        print(TAG+"Log rotation failed:")

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
                    print(TAG+f"No active log filename found in the reference file: \"{ref_fn}\"")
                else:
                    # Check if the active log file exists
                    if ck_log(active_log_fn):
                        active_log_path = get_prefix() + log_fn
                        active_log_exist = True
               
                # If the active log file exists, we can use it
                # Otherwise, we create a new log file
                if active_log_exist:
                    if my_debug:
                      print(TAG+f"Active log file: \"{active_log_fn}\" does exist in the directory: \"{get_prefix()}\"")
                    active_log_path = get_prefix() + active_log_fn
                    active_log_size = os.stat(active_log_path)[6]  # File size in bytes 
                    log_fn = active_log_fn  # Update the global log_fn variable
                    log_path = active_log_path  # Update the global log_path variable
                else:
                    print(TAG+f"Active log file: \"{active_log_fn}\" does not exist in the directory: \"{get_prefix()}\"")
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
                print(TAG+f"OSError: {e}")
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
            print(TAG+f"OSError: {e}")
        # rotate_log_if_needed() # create a new log file and add it to th ref file
except OSError as e:
    print(TAG+f"OSError occurred: {e}")
    
def timestamp():
    t = time.localtime()
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(
        t[0], t[1], t[2], t[3], t[4], t[5])
    
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
                    print(TAG+f"add_to_log(): error while trying to open or write to the log file: {e}")
            else:
                print(TAG+f"log file: \"{log_path}\" does not exist. Unable to add: \"{txt}\"")
    else:
        print(TAG+f"parameter txt needs to be of type str, received a type: {param_type}")

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
              print(TAG+"No log files found starting with \"{}\"".format(list_log_prefix))
          else:
              print(TAG+"Total number of log files found: {}".format(cnt))
          do_line(51)
    except OSError as e:
        print(TAG+"Error accessing directory:", e)

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
                    print(TAG+f"Failed to delete: {fname}, error: {e}")

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
            print(TAG+f"no logfile(s) found starting with \"{log_pfx}\" and ending with \".txt\"")
    
    except OSError as e:
        print(TAG+f"Could not list directory: {log_dir} for deletion. Error: {e}")

def topic_in_lst():
    ret = -1
    topic_idx = 0
    le = len (TOPIC_LST)
    if le > 0:
        for i in range(le):
            if TOPIC_LST[i] == topic_rcvd:
                ret = i
                break
    if ret < 0:
        if not my_debug:
            print(f"topic received: {topic_rcvd} not in TOPIC_LST")
    return ret
# MQTT callback function
def mqtt_callback(topic, msg):
    global topic_rcvd, msg_rcvd, payload, last_update_time, topic_idx
    TAG = "mqtt_callback(): "
    if not my_debug:
        raw_msg = msg.decode('utf-8')
        print(TAG+f"Decoded raw_msg length: {len(raw_msg)}")
        print(TAG+f"raw_msg: {raw_msg}") # may reveal the broken JSON
    try:
        if my_debug:
            print(TAG+f"type(topic) = {type(topic)}")
        if isinstance(topic, bytes):
            topic_rcvd = topic.decode("utf-8")
        elif isinstance(topic, str):
            topic_rcvd = topic # same
        n =  topic_in_lst()
        if n < 0:
            if not my_debug:
                print(TAG+f"topic received {topic_rcvd} not subscribed to. Skipping...")
            return
        else:
            topic_idx = n
        if msg.endswith(b'}'):
            payload = ujson.loads(msg)
            last_update_time = time.time()  # Update the last update time
            if my_debug:
                print(TAG+f"type(payload) = {type(payload)}")
        else:
            payload = None
            print(TAG+"Incomplete message received, skipping.")
            return

        ts = payload.get("ts", datetime_empty)
        #print(TAG+f"Received a mqtt message on topic: \"{topic.decode('utf-8')}\", timestamp: {ts}")
        print(TAG+f"Received a mqtt message on topic: \"{topic_rcvd}\", timestamp: {ts}")
        if my_debug:
            print(f"msg: {msg}")
        if len(msg) > 0:
            msg_rcvd = True
    except Exception as e:
        print(TAG+"Unhandled exception:", str(e))

def convert_to_unix(dt):
    # dt: '2025-06-01T02:21:01'
    if dt == "unknown":
        return 0
    date_part, time_part = dt.split('T')
    year, month, day = map(int, date_part.split('-'))
    hour, minute, second = map(int, time_part.split(':'))

    # Adjust UTC+1 (subtract 1 hour)
    hour -= 1
    if hour < 0:
        hour += 24
        day -= 1  # Note: no month/year wraparound yet, keep simple

    tup = (year, month, day, hour, minute, second, 0, 0)  # No weekday or yearday
    timestamp = utime.mktime(tup)
    if my_debug:
        print(f"[DEBUG] Unix timestamp = {timestamp}")
    return timestamp

def uxMinimum(yr1970: bool = True):
    if yr1970:
        return  0   #  = 1970-01-01, 1970 0:00:00 UTC
    else:
        return -2208988800 # = 1900-01-01 00:00:00 UTC

def uxMaximum():
    return 2147483647 # 2038-01-19 03:14:07 UTC (maximum value for a signed integer 32-bit number)

def convert_to_dtStr(uxTime):
    # print(f"convert_to_dtStr(): type(uxTimeS) = {type(uxTime)}")
    if not isinstance(uxTime, int):
        return datetime_empty
    if uxTime <= uxMinimum() or uxTime >= uxMaximum():  # max for 32-bit
        return datetime_empty
    # Convert to local time tuple
    t = time.localtime(uxTime)
    # Format as ISO 8601 string: YYYY-MM-DDTHH:MM:SS
    return "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}".format(
            t[0], t[1], t[2], t[3], t[4], t[5])

def split_msg():
    global topic_rcvd, payload, payloadLst, Publisher_ID, lightsColorIdx, lights_ON, lights_ON_old, lightsColorMax, lightsColorMin
    TAG = "split_msg(): "
    topic_found = False
    
    try:
        topicIdx = -1
        for i in range(len(TOPIC_LST)):
            if topic_rcvd == TOPIC_LST[i]:
                topicIdx = i
                break
        if topicIdx >= 0:
            if my_debug:
                print(TAG+f"Topic rcvd: {topic_rcvd} found in TOPIC_LST: {TOPIC_LST[topicIdx]}")
            topic_found = True
        else:
            print(TAG+f"topic rcvd: {topic_rcvd} not in TOPIC_LST: {TOPIC_LST}")
        
        if not topic_found:
            return 
        
        doc = payload.get("doc", {})
        payloadLst = []
        datetime = datetime_empty
        # Step 1: Decode from bytes and parse JSON
        #decoded = ujson.loads(msg)
        if payload is None:
            print(TAG+"payload is None, skipping further processing.")
            return
        # Step 1.1: Check if the payload is empty
        if not payload:
            print(TAG+"Received an empty payload, skipping further processing.")
            return
        
        # Step 2: Pull shared metadata
        owner = payload.get("ow", "?")
        if owner == "unknown":
            Publisher_ID = PUBLISHER_ID  # if "unknown" we use the definition from secret.json
        elif owner == "Feath":
            Publisher_ID = "Feather"
        else:
            Publisher_ID = owner  # use the owner from the payload
            # Step 2: Pull shared metadata
        
        lbl_k = "ow"
        lbl_v = owner
        output = {lbl_k: lbl_v}
        payloadLst.append(output)
        
        description = payload.get("de", "unknown")
        lbl_k = "de"
        lbl_v = description
        output = {lbl_k: lbl_v}
        payloadLst.append(output)
        
        lbl_k = "dc"
        device_class = payload.get("dc", "unknown")
        if device_class == "BME280":
            lbl_v = device_class
        elif device_class == "home":
            lbl_v = device_class
        elif device_class == "colr":
            lbl_v = "color"
        else:
            lbl_v = device_class
        output = {lbl_k: lbl_v}
        payloadLst.append(output)
        
        lbl_k = "sc"
        state_class = payload.get("sc", "unknown") # == "measure":
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
        
        lbl_k = "vt"
        vt = payload.get("vt") # "vt" stands for value term
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
        
        uxTime = payload.get("ts", "unknown")
        
        if uxTime <= uxMinimum() or uxTime >= uxMaximum(): # max for 32-bit
            uxTimeStr = "invalid"
        else:
            uxTimeStr = str(uxTime)
        
        if my_debug:
            print(TAG+f"uxTime = {uxTime}")
        if uxTime == 0:
            datetime = datetime_empty  # Default to 0 if unknown
        else: 
            datetime = convert_to_dtStr(uxTime)
            if my_debug:
                print(TAG+f"datetime = {datetime}")
        
        lbl_k = "tm"
        if datetime == "unknown" or datetime == datetime_empty:
            lbl_v = "--:--:--"
        else:
            time = datetime[-8:]
            lbl_v = time
        output = {lbl_k: lbl_v}
        payloadLst.append(output)
        
        lbl_k = "ts"
        lbl_v = uxTimeStr
        output = {lbl_k: lbl_v}
        payloadLst.append(output)
            
        if my_debug:
            ts = payload.get("ts", datetime_empty)
            print(TAG+f"Received msg from: {owner}, timestamp: {uxTime}") # was: "timestamp"

        # ✅ Make sure this matches your payload
        default_state_class = payload.get("sc", "unknown")  # 🆕 pulled from top-level
        if my_debug:
          print(TAG+f"owner: {owner} [{device_class}], timestamp: {uxTime}")
        
        
        if topicIdx == 0: # sensors/Feath/ambient
            # Step 3: Extract and flatten "reads"
            readings = payload.get("reads", {})

            for key, data in readings.items():
                label = key.upper()
                value = data.get("v", "??")
                unit = data.get("u", "")
                
                # min_val = data.get("mn", "?")
                # max_val = data.get("mx", "?")
                # sc = data.get("state_class", state_class)
                
                lbl_k = None
                lbl_v = None
                
                if label == "T":
                    t1 = "Temperature: "
                    lbl_k = "temp"
                    if vt == "f":
                        lbl_v = t1 + "{:4.1f} °C".format(value) # + str(value) + " °C"
                    elif vt == "i":
                        lbl_v = t1 + str(value) + " °C"
                    elif vt == "s":
                        lbl_v = t1 + value + " °C"
                elif label == "P":
                    t1 = "Pressure: "
                    lbl_k = "pres"
                    if vt == "f":
                        lbl_v = t1 + "{:6.1f} {:s}".format(value, unit)
                    elif vt == "i":
                        lbl_v = t1 + str(value) + unit
                    elif vt == "s":
                        lbl_v = t1 + value + unit
                elif label == "A":
                    t1 = "Altitude: "
                    lbl_k = "alti"
                    if vt == "f":
                        lbl_v = t1 + "{:5.1f} {:s}".format(value, unit)
                    elif vt == "i":
                        lbl_v = t1 + str(value) + unit
                    elif vt == "s":
                        lbl_v = t1 + value + unit
                    
                elif label == "H":
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
            
            if my_debug:
                print(TAG+"Root fields:")
                print(TAG+f"owner:        {owner}")
                print(TAG+f"device_class: {device_class}")
                print(TAG+f"state_class:  {state_class}")
                print(TAG+f"msgID:        {uxTime}")
                print(TAG+"Reads fields")
                print(f"payloadLst: {payloadLst}")
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
            if my_debug:
                print(TAG+f"toggle payload.keys() = {toggle.keys()}")
                print(TAG+f"toggle payload.items() = {toggle.items()}")
            for key, data in toggle.items():
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
                if lights_ON != lights_ON_old:  # Only change if value differs from last received value
                    print(TAG+f"Toggling ambient light neopixel leds {'on' if lights_ON == True else 'off'}")
                    #lights_ON_old = lights_ON
                    if not lights_ON:
                      NP_clear()  # Switch bl leds off
                    else:
                      NP_color()  # Switch bl leds on and set color of lightsColorIdx
                else:
                    print(TAG+f"Not toggling ambient light neopixel leds. lights_ON = {lights_ON}, lights_ON_old = {lights_ON_old}")
        elif topicIdx == 2: # lights/Feath/color_inc
            colorInc = payload.get("colorInc")
            if my_debug:
                print(TAG+f"colorInc payload.items() = {colorInc.items()}")
            for key, data in colorInc.items():
              if my_debug:
                  if isinstance(data, int):
                    print(TAG+"key = {:>2s}, data = {:>2d}".format(key, data))
                  elif isinstance(data, str):
                    print(TAG+"key = {:>2s}, data = {:>2s}".format(key, data))
              if key == "u": # unit of measurement
                unit = data
              elif key == "mx":
                lightsColorMax = data
              elif key == "mn":
                lightsColorMin = data
              if key == "v": # value
                if unit == "i": # integer
                  value = data
                elif unit == "s":  # string
                  value = int(data) # convert to int
                if my_debug:
                    print(TAG+f"value = {value}, lightsColorMin = {lightsColorMin}, lightsColorMax = {lightsColorMax}")
                if value >= lightsColorMin and value <= lightsColorMax:
                    lightsColorIdx = value
                    if my_debug:
                        print(TAG+f"lightsColorIdx set to: {lightsColorIdx}")
                    NP_color()  # set the color of the ambient bg leds
                else:
                  lightsColorIdx = -1
                        
        elif topicIdx == 3:  # lights/Feath/color_dec
            colorDec = payload.get("colorDec")
            if my_debug:
                print(TAG+f"colorDec payload.items() = {colorDec.items()}")
            for key, data in colorDec.items():
              if my_debug:
                if isinstance(data, int):
                    print(TAG+"key = {:>2s}, data = {:>2d}".format(key, data))
                elif isinstance(data, str):
                    print(TAG+"key = {:>2s}, data = {:>2s}".format(key, data))
              if key == "u": # unit of measurement
                unit = data
              elif key == "mx":
                lightsColorMax = data
              elif key == "mn":
                lightsColorMin = data
              if key == "v": # value
                if unit == "i": # integer
                    value = data
                elif unit == "s":  # string
                    value = int(data) # convert to int
                if my_debug:
                    print(TAG+f"value = {value}, lightsColorMin ={lightsColorMin}, lightsColorMax = {lightsColorMax}")
                if value >= lightsColorMin and value <= lightsColorMax:
                    if my_debug:
                      print(TAG+f"lightsColorIdx set to: {lightsColorIdx}")
                    lightsColorIdx = value
                    NP_color()  # set the color of the ambient bg leds
                else:
                    lightsColorIdx = -1

    except Exception as e:
        print(TAG+"error:", str(e))

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
                        print(TAG+f"key \'{key}\' not found in entry {entry}")
                        
    return ""  # if key not found


def draw(mode:int = 1):
    global payload_txt, payloadLst, msg_drawn, Publisher_ID, publisher_time, publisher_msgID, topic_idx, lights_ON, lights_ON_old
    TAG = "draw(): "
    time_draw = "--:--:--" # Also used for setting the day or night text colour
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
    clean()

    # Display the message
    # See: https://doc-tft-espi.readthedocs.io/tft_espi/colors/
    # NOTE: NAVY gives less brightness than ORANGE
    if time_draw != "--:--:--":
        time_draw_hh = int(time_draw[:2])
    else:
       time_draw_hh = 0
    hh = time_draw_hh    
    
    CURRENT_COLOUR = None
    
    if not my_debug:
        print(TAG+f"hh = {hh}")
    
    if  hh >= 9 and hh < 21:
        display.set_pen(ORANGE)
        CURRENT_COLOUR = ORANGE
    else:
        display.set_pen(NAVY)
        CURRENT_COLOUR = NAVY
    x = 10
    y = 25
    line_space = 30
    margin = 10
    
    hdg = "MQTT " # pub : "
    display.text(hdg, x, y, WIDTH)
    if wifi_connected:
        display.text("Wi-Fi OK", 10, 120, WIDTH) # scale=2)
    if mqtt_connected:
        display.text("MQTT OK",  10, 140, WIDTH) # scale=2)
    #display.text("hh = " + str(hh),  10, 160, WIDTH) # scale=2)
    #display.text(hdg + Publisher_ID, 10, 25, WIDTH)
    if msg_rcvd:
        #display.set_pen(BLACK)  # Black background
        #display.clear()
        clean()
        time_draw = get_payload_member("tm")
        print(TAG+f"time_draw = {time_draw}")
        if time_draw != "--:--:--":
            time_draw_hh = int(time_draw[:2])
        else:
           time_draw_hh = 0
        hh = time_draw_hh    
        if  hh >= 9 and hh < 21:
            display.set_pen(ORANGE)
            CURRENT_COLOUR = ORANGE
        else:
            display.set_pen(NAVY)
            CURRENT_COLOUR = NAVY
        display.text(hdg, 10, 25, WIDTH)
         
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
        #                                             Examples:
        # Read the "doc" members
        time_draw = get_payload_member("tm")      # → "--:--:--"
        ow_draw = Publisher_ID # get_payload_member("ow")  # → "Feather" or "UnoR4W"
        de_draw = get_payload_member("de")        # → "PC-Lab"
        dc_draw = get_payload_member("dc")        # → "BME280", "home", "colr", "colr"
        # sc_draw = get_payload_member("sc");       # → "meas", "ligh", "inc", "dec"
        timestamp_draw = get_payload_member("ts") # → "1748945128" = Tue Jun 03 2025 10:05:28 GMT+0000
        
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
        elif topic_idx == 2 or topic_idx == 3:
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
                
        else:
            return # No valid topic_idx
        
        my_scale = 2
        y = 25 # restart y position
        #display.set_pen(BLACK)  # Black background
        #display.clear()
        clean()
        display.set_pen(CURRENT_COLOUR)
        display.text(hdg + " " + time_draw, x, y, WIDTH, scale = my_scale)
        y += line_space
        display.text(ow_draw + " " + de_draw + " " + dc_draw, x, y, WIDTH, scale = my_scale)
        y += line_space
        display.text("msgID: " + timestamp_draw, x, y, WIDTH, scale = my_scale)
        y += line_space
        if not my_debug:
            print(TAG+f"topic_idx: {topic_idx} = topic: \"{TOPIC_LST[topic_idx]}\"")
        if topic_idx == 0: # sensors/Feath/ambient
            display.text(temp_draw, x, y, WIDTH, scale = my_scale)
            y += line_space
            display.text(pres_draw, x, y, WIDTH, scale = my_scale)
            y += line_space
            display.text(alti_draw, x, y, WIDTH, scale = my_scale)
            y += line_space
            display.text(humi_draw, x, y, WIDTH, scale = my_scale)
        elif topic_idx == 1: # lights/Feath/toggle
            display.text(toggle_draw1, x, y, WIDTH, scale = my_scale)
            y += line_space + 5
            display.text(toggle_draw2, x, y, WIDTH, scale = my_scale)
            y += line_space
        elif topic_idx == 2 or topic_idx == 3: # lights/Feath/color_inc
            display.text(color_txt1_draw, x, y, WIDTH, scale = my_scale) 
            y += line_space + 5
            display.text(color_txt2_draw, x, y, WIDTH, scale = my_scale)
            y += line_space
    
    presto.update()
    
    msg_drawn = True
    
    if not my_debug:
        do_line()
        

def pr_log():
    global log_path, log_obj, log_size_max
    TAG = "pr_log(): "
    try:
        if log_obj:
            log_obj.close()
        
        if log_path:
            log_size = os.stat(log_path)[6]  # File size in bytess
            if log_size > 0:
                print(f"Size of log file: {log_size}. Max log file size can be: {log_size_max} bytes.")
                print(f"Contents of log file: \"{log_path}\"")
                with open(log_path, 'r') as log_obj:
                    f_cnt = 0
                    for line in log_obj:
                        f_cnt += 1
                        print("{:s} {:02d}) {:s}".format(TAG, f_cnt, line.strip())) # Remove trailing newline for cleaner output
                    do_line()
            else:
                print(TAG+f"log file \"{log_path}\" is empty")
    except OSError as e:
        print(TAG+f"No log file found or unable to open. Error: {e}")

def cleanup():
    global ref_exist, ref_obj, ref_path, log_exist, log_obj, log_path
    if ref_obj: # and ref_path is not None and ref_exist:
        ref_obj.close()
    if log_obj: # and log_path is not None and log_exist:
        log_obj.close()

def setup():
    global client, CLIENT_ID, BROKER, PORT, TOPIC0, TOPIC1, TOPIC2, TOPIC3, msg_drawn, mqtt_connected, lights_ON, lights_ON_old
    # MQTT client setup
    TAG = "setup(): "
    """
    if not ck_log(err_log_fn):  # Check if the error log file exists
        print(TAG+f"Error log file: \"{err_log_fn}\" does not exist, creating it")
        create_err_log_file()
    """
    
    print(TAG+"Switching ambient light neopixel leds off")
    lights_ON = False
    lights_ON_old = False
    NP_clear()
    
    #rx_bfr=1024  # ← Increase to 1024 or higher
    print(TAG+f"Connecting to MQTT broker at {BROKER} on port {PORT}") # , recv_buffer {rx_bfr}")
    
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
        for i in range(len(TOPIC_LST)):
            client.subscribe(TOPIC_LST[i])
            #print(TAG+f"Subscribed to topic: \"{TOPIC_LST[i].decode()}\"")
            print(TAG+f"Subscribed to topic: \"{TOPIC_LST[i]}\"")
            #add_to_log("Subscribed to topic: {}".format(TOPIC_LST[i].decode()))
            add_to_log("Subscribed to topic: {}".format(TOPIC_LST[i]))
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
            t = f"Failed to reach the host with address: {BROKER} and port: {PORT}"
            print(TAG+f"{t}")
            add_to_log(t)
            mqtt_connected = False
        else:
            print(TAG+f"Failed to connect to MQTT broker: {e}")
            mqtt_connected = False
    except KeyboardInterrupt as e:
        print(TAG+f"KeyboardInterrupt. Exiting...\n")
        add_to_log("Session interrupted by user — logging and exiting.")
        cleanup()
        pr_ref()
        pr_log()
        raise

# Here begins the "loop()" part:
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
            # print(TAG+"we passed the client.check_msg(). Line 830")
            if msg_rcvd:
                msg_rx_timeout_start_t = msg_rx_timeout_current_t # update the start time
                break
           
            msg_rx_timeout_elapsed_t = msg_rx_timeout_current_t - msg_rx_timeout_start_t
            if msg_rx_timeout_elapsed_t >= msg_rx_timeout_interval_t:
                msg_rx_timeout_start_t = msg_rx_timeout_current_t
                msg_rx_timeout = True
                break
        
        if msg_rx_timeout:
            msg_rx_timeout = False # reset flag
            print(TAG+"msg rx timedout!")
            continue # loop

        # Refresh the display periodically
        if msg_rcvd:
            split_msg()
            if my_debug:
                if publisher_msgID:
                    print(f"{TAG}MQTT message received from: {publisher_msgID}")
                else:
                    print(f"{TAG}MQTT message received")

            draw(1) # Display the new message in mode "PaulskPt"
            msg_rcvd = False
        elif time.time() - last_update_time > MESSAGE_DISPLAY_DURATION:
            draw(1)  # Refresh the screen with the current message
            last_update_time = time.time()
        if msg_rcvd:
            # Cleanup
            print(TAG+"Cleaning up:")
            msg_rcvd = False # reset this flag

    except Exception as e:
        if e.args[0] == 103:
            print(TAG+f"Error ECONNABORTED") # = Software caused connection abort
            # add_to_log(e)
            err.log(e) # print exception to the err.log
            print(TAG+f"Reconnecting to MQTT broker...")
            setup()
            #cleanup()
            #raise RuntimeError
        elif e.args[0] == 104: # ECONNRESET
            print(TAG+f"Error ECONNRESET") # = Software caused connection abort
            # sys.print_exception(e)
            #add_to_log(e)
            err.log(e) # print exception to the err.log
            print(TAG+f"Reconnecting to MQTT broker...")
            setup()
        else:
            print("loop(): Error:", repr(e))
            #err_txt = f"Error while waiting for MQTT messages:"
            #if my_debug:
            #    print(TAG+f"{err_txt} {e}")
            #else:
            #    print(TAG+f"{err_txt} {e.__class__.__name__}: {e}")
            err.log(e) # print exception to the err.log
            cleanup()        
            raise RuntimeError
    except KeyboardInterrupt as e:
        print(TAG+f"KeyboardInterrupt: exiting...\n")
        # sys.print_exception(e)
        # err.log(e)
        add_to_log("Session interrupted by user — logging and exiting.")
        cleanup()
        pr_ref()
        pr_log()
        raise

# for compatibility with the Presto "system" the next two lines have been commented out
# if __name__ == '__main__':
#   main()
