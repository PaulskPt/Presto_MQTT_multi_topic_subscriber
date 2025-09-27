# 1) Receiving and displaying ambient data;
# 2) executing commands;
# on a Pimoroni Presto device

by Paulus Schulinck (Github handle: @PaulskPt)

## What is it?
- Receiving, interpreting and displaying ambient data as temperature, pressure and humidity from a remote ambient sensor,
- Receiving $SYS topic MQTT messages,
- executing commands from a remote control device,
- by means of MQTT messages.

See at the end also info about a second Publisher device (alias: "Publisher2") for sending MQTT messages with topic "weather/PL2XLW/metar".

## MQTT messages come by "topics".
### This repo works with four different topics for the Publisher device and six topics for the Subscriber device:
- "sensor/Feath/ambient". Containing ambient data from a remote sensor
- "lights/Feath/toggle". Containing a lights toggle command from a remote controller
- "ligths/Feath/color_inc". Containing a lights color increase command from a remote controller
- "lights/Feath/color_dec". Containing a lights color decrease command from a remote controller
- "$SYS/broker/clients/disconnected". Subscriber device only. 
- "$SYS/broker/clients/connected". Subscriber device only.

If you do not know what is the MQTT communication protocol see: [MQTT](https://en.wikipedia.org/wiki/MQTT).

For a successful MQTT communication you need: 
- a MQTT Publisher device. In my case: an Adafruit Feather ESP32-S3 TFT board ("Publisher1") and a Pimoroni Pico LiPo 2XL W ("Publisher2");
- a MQTT Broker device. This can be an online broker or a Broker device in your Local Area Network (LAN). I prefered the latter. In my case: a Raspberry Pi Compute Module 5;
- one or more MQTT Subscriber device(s). This repo is intended to use a Pimoroni Presto as MQTT Subscriber device.

## How to install?
### For the Subscriber device

Download the latest version of Pimoroni [Presto FW](https://github.com/pimoroni/presto/releases/tag/v0.1.0). You have two options: download micropython with filesystem (examples etcetera), filename: "presto-v0.1.0-micropython-with-filesystem.uf2" or without filesystem, filename: "presto-v0.1.0-micropython.uf2". Flash the .uf2 file of your choice onto your Presto. You can do this easily by bringing the Presto in download mode by pressing and holding the "BOOT" button, then pressing and releasing the "RESET" button and next releasing the "BOOT" button. If you did this well a disk drive (for example D:) will appear in the file manager of your PC. In Linux systems there will appear a disk icon on your desktop. On MS Windows PCs there will popup a window with the name (for example) "RP2350 (D:)". Now you can copy (for example by "dragging" and "dropping") the downloaded .uf2 file onto the "RP2350 (D:)" window. When the copy process has been completed the popup window will disappear from your desktop. Next press the "RESET" button of the Presto.

Next step, for this subscriber device, copy the files of this repo from this subfolder [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Subscriber) to a folder of your preference, for example: 
```
C:\<Users>\<User>\Documents\Hardware\Pimoroni\Presto\Micropython\mqtt\
```

Copy the files for the publisher1 device of this repo from this subfolder [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Publisher/Publisher1_v4/Feather_ESP32_S3_TFT_MQTT_multi_topic_v4) to a folder of your preference, for example: 
```
C:\Users\<User>\Documents\Arduino\Feather_ESP32_S3_TFT_MQTT_multi_topic_v4\
```

If you also use a Publisher2 device, copy the files of this repo for Publisher2 from this subfolder [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Publisher/Publisher2_V1/metar_mqtt_v1) to a folder of your preference, for example:
```
 C:\Users\<User>\Hardware\Pimoroni\PICO_LIPO_2XL_W_PIM776\micropython\metar_mqtt_v1\
```

### Requirements for the development platform
You need to have installed on your PC: 
- Thonny IDE or equivalent. Needed for the Pimoroni Presto device.
- Arduino IDE v2.3.5. Needed for the Adafruit Feather ESP32-S3-TFT device. Do not use the Arduino (Cloud) online IDE because, AFAIK, that limits the possibility to change library files to your needs.
  For example I added a function to the M5Stack M5Unit-RTC library for the Arduino IDE. I added the function:  "setUnixTime(unsigned long uxTime)".
  For your convenience I added this modified library [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Arduino/libraries/).

### Installing files onto your Presto Subscriber device

Before going to copy files from this repo to your Presto I advise you to first edit the file "\src\Subscriber\secrets.json". 

In the section with the key "wifi" fill-in your Wi-Fi SSID and your W-Fi Password.
```
"wifi" : {
      "ssid" : "<Your SSID here>",
      "pass" : "<Your Password here>"],
```
In the section with the key "mqtt" enter:
- your Broker choice: internal or external;
- the IP-addresses of the Brokers, as follows:
```
{
  "mqtt": {
    "use_local_broker" : 1,                (Note: 1 for local Broker, 0 for remote Broker)
    "broker_local" : "192.168.0.215",      (Note: example address)
    "broker_external": "5.196.78.28",      (Note.: address of mosquitto.org MQTT test server)
   [...]
}
```
If your Presto is connected to your PC, disconnect it. If you are going to use an SD-Card it is a good moment to insert the SD-Card into the SD-slot of your Presto.
If you are using the Thonny IDE, start Thonny. In the "View" menu select "Files". A window in the left side of the Thonny IDE window will appear. 
Connect your Presto to your PC using a good quality USB-A to USB-C cable. The Presto will boot and will show its opening screen, a carrousel of application icons. Now stop the execution of the running main.py program on the Presto by pressing on the red "STOP" button in the top left side of the window of the Thonny app.
The following text will appear in the "Shell" window of the Thonny app:
```
Traceback (most recent call last):
  File "main.py", line 332, in <module>
KeyboardInterrupt: 
MicroPython feature/presto-wireless-2025,   on 2025-03-21; Presto with RP2350
Type "help()" for more information.

MPY: soft reboot
MicroPython feature/presto-wireless-2025,   on 2025-03-21; Presto with RP2350

Type "help()" for more information.

>>> 
```
Now you can start copying files of this repo, files intended for the Subscriber device onto the Presto, from within the Thonny app.
In the top half of the "Files" window, name: "This computer", will show a list of files and directories. In the bottom half of the "Files" window, name: "Raspberry Pi Pico", will show a list of files and eventually directories. 

The file structure of "This computer" should look like this:

	C:\<Users>\<User>\Documents\Hardware\Pimoroni\Presto\Micropython\mqtt\
```
\lib
	sdcard.py
	exc.py
\sd
	mqtt_latest_log_fn.txt
	mqtt_log_2025-07-20T172657.txt
boot.py
err.log
mqtt_log_2025-07-02T140505.txt
presto_mqtt_v3.py
secrets.json
sys_broker.json

```

The file structure of "Raspberry Pi Pico" has to go to look like this:
```
Raspberry Pi Pico
/lib
	sdcard.py
	exc.py
/sd
	mqtt_latest_log_fn.txt
	mqtt_log_2025-07-20T172657.txt
        [...here will be created log files, for example: "mqtt_log_2025-07-20T172658.txt"]
	[here you can save other application files and/or photo files.]
boot.py
err.log
mqtt_log_2025-07-02T140505.txt
mqtt_presto_v3.py
secrets.json
sys_broker.json
[all other files from the Pimoroni (firmware) like main.py and all their example .py files]

```
If, in the "Raspberry Pi Pico" files window part, are not yet present the two directories: "lib" and "sd", create them by clicking on "Raspberry Pi Pico", to be sure you are in the "root" of the filesystem on the Presto. To check this: look in the Thonny Shell window. It will show this:

```
	>>> %cd /
```

Next right-click on your mouse. In the small window that pops up, select the menu-item: "New directory". Next type the directory name, for example "lib" or "sd". Then click on "OK". Do this, when necessary, for both directories as shown in the files structure above. Note that the Thonny Shell window only shows "%cd /" or "%cd /lib" or "%cd /sd" for activities inside the "Raspberry Pi Pico" files window part. This will not happen when you move between directories in the "This computer" files window part.
Now copy all files from the "This computer" files window part to their respective directories (root, /lib or /sd) of the "Raspberry Pi Pico" files window part.
When you have copied all the files from this repo, part /src/Subscriber/ to the Pimoroni Presto, you can reboot the Presto. After the Presto has been booted an image of a "carrousel" of icons is shown. Tap six times onto the icon shown in the right corner of the display, then you should see an icon with below it the title "Mqtt Presto V3" [photo](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/images/Subscriber/20250721_013544.png). Tap on this icon to start this micropython script. For some seconds you will see a black screen. The script has to do various checks, load secret.json, establish Wi-Fi communication. Establish communication with the Broker of your choice. In the "Shell" window of Thonny will appear serial output, like this:
```
>>> %Run -c $EDITOR_CONTENT

MPY: soft reboot
global(): error class object created. It is of class: <class 'ERR'>
main(): Connecting to WiFi...
main(): WiFi connected.
NP_clear(): 🌈 ambient neopixels off
setup(): Display hours wakeup: 7, gotosleep: 23
setup(): Connecting to MQTT local broker on port 1883
setup(): Not deleting log files, flag: "delete_logs" = False
setup(): Successfully connected to MQTT broker.
setup(): Subscribed to topic: "sensors/Feath/ambient"
setup(): Subscribed to topic: "lights/Feath/toggle"
setup(): Subscribed to topic: "lights/Feath/color_inc"
setup(): Subscribed to topic: "lights/Feath/color_dec"
setup(): Subscribed to topic: "$SYS/broker/clients/disconnected"
setup(): Subscribed to topic: "$SYS/broker/clients/connected"
--------------------------------------------------
```

Then will appear a first screen with a black background and the following text in navy blue color (see: [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/images/Subscriber/20250722_100733.png)):
```
	mqtt
	waiting for
	messages...

	wi-fi OK
	mqtt OK
```
As soon as the Presto has received the first MQTT message, a new screen will appear with text in orange color during daylight hours or in navy blue during night hours.
See [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/images/Subscriber/20250722_100834.png).
In the Thonny Shell window will appear info about the received message, like this:
```
mqtt_callback(): Received a mqtt message on topic: "sensors/Feath/ambient", timestamp: 1753276934
mqtt_callback(): Decoded raw_msg length: 251
mqtt_callback(): raw_msg: {"ow":"Feath","de":"PC-Lab","dc":"BME280","sc":"meas","vt":"f","ts":1753276934,
"reads":{"t":{"v":28,"u":"C","mn":-10,"mx":50},"p":{"v":1005.6,"u":"mB","mn":800,"mx":1200},
"a":{"v":63.9,"u":"m","mn":0,"mx":3000},"h":{"v":39.5,"u":"%","mn":0,"mx":100}}}
--------------------------------------------------
```

# MQTT message content

The MQTT messages are defined in a Json format. The messages that my Publisher device sends contain a "topic name", for example: "sensors/Feath/ambient" as "message heading" part and a "payload" part, containing one main Json object with the name "doc". Here is an example of the contents of this main Json object:
```
	{"ow":"Feath","de":"PC-Lab","dc":"BME280","sc":"meas","vt":"f","ts":1753098395,[...]}
```

The structure for payload of the MQTT message is shown below. Except for the members "timestampStr" and "timestamp" the structure members are used in the MQTT messages that the MQTT Publisher device sends. This structure I copied from the firmware for an Unexpected Maker SQUiXL device, however I added three members.

```
struct MQTT_Payload
{
	std::string owner = "";
	std::string device_class = "";
	std::string state_class = "";
	std::string term = ""; // Like meterorological term: "Pressure"
	std::string unit_of_measurement = "";
	std::string sensor_value = "";
	std::string value_type = "";
	std::string min_value = "";
	std::string max_value = "";
	std::string description = "";
	std::string timestampStr = ""; // human readable ISO format
	std::string msgID = ""; // In fact thia member contains a Unix timestamp
	int timestamp = 0;  // This member is not sent in the MQTT messages. It is used in the firmware 
}
  ```


Depending on the topic, the MQTT messages my Publisher device sends, contain minimum one nested Json object and maximum four nested Json objects.
The MQTT messages with topic "sensors/Feath/ambient" have four nested Json objects (see below). The other MQTT messages with topics:
"lights/Feath/toggle", "lights/Feath/color_dec" or "lights/Feath/color_inc", contain one nested Json object (see below).

To keep the length of the payload of the MQTT messages under 256 bytes, I have chosen to abbreviate the names of this struct.

Why keep the payload length under 256 bytes? 

I had a problem when using a Pimoroni Presto device as Subscriber device, which uses a modified version of Micropython.
I discovered that MQTT messages received were cutoff. Initially the MQTT Publisher device sent messages with full names of the payload structure shown above, which made the payload longer than 256 bytes. That is why I decided to abbreviate the names. I managed to reduce the payload length to less than 256 bytes. Since then the MQTT messages sent by the MQTT Publisher device were received complete.

```
In the Json object "doc" (in other words: "message heading"):
key: owner        -> ow     value: e.g.: the board model, in my case: "Feather" -> "feath"
key: description  -> de     value: e.g.: the location of the device, in my case: "PC-Lab"
key: device_class -> dc     values: "BME280", "HOME", "INC", "DEC"
key: state_class  -> sc     values: "measurement" -> "meas", "light" -> "ligh", "increase" -> "inc" and "decrease" -> "dec"
key: value_type   -> vt     values: "float" -> "f", "integer" -> "i", "string" -> "s" and "boolean" -> "b"
key: timestamp    -> ts     value: an unsigned long integer, in fact a unixtime (in local time)
```
In case of a MQTT message with topic: "sensor/Feath/ambient"

The "payload" part of the MQTT message is a nested Json object with name "reads". Inside this object there are
four nested Json objects for each (term) of the BME280 sensor: "temperature" (t), "pressure" (p), "altitude" (a)  and "humidity" (h).
For example:

```
[...], "reads" : {
	key: "t"  values: {"v":29,"u":"C","mn":-10,"mx":50}
	key: "p"  values: {"v":1005.6,"u":"mB","mn":800,"mx":1200}
	key: "a"  values: {"v":63.9,"u":"m","mn":0,"mx":3000}
	key: "h"  values: {"v":41.7,"u":"%","mn":0,"mx":100}
	}
```
where for key "t" the item "v":29 stands for a temperature of 29 degrees.
The "u":"C" stands for unit of measurement: degrees centrigrade.
The "mn":-10 stands for a minimum temperature of minus ten degrees.
The "mx":50 stands for a maximum temperature of fifty degrees.

In case of a MQTT message with topic: "lights/Feath/toggle",
containing a lights toggle command,
the only nested Json object, name "toggle", contains, for example: 
```
	[...],"toggle":{"v":1,"u":"i","mn":0,"mx":1}}, 
```

where "v":1 stands for Toggle leds ON.

In case of a MQTT message with topic: "lights/Feath/color_inc",
the only nested Json object, name "colorInc", contains, for example: 
```
  	[...]"colorInc":{"v":4,"u":"i","mn":0,"mx":9}}
```
where "v":4 stands for ColorIndex value 4 (minim 0 and maximum 9)

In case of a MQTT message with topic: "lights/Feath/color_dec",
the only nested Json object, name "colorDec", contains, for example:
```
  	[...]"colorDec":{"v":3,"u":"i","mn":0,"mx":9}}
```

Each nested Json object has the same definition:
```
	"value"               -> "v"
	"unit_of_measurement" -> "u"
	"minimum_value"       -> "mn"
	"maximum_value"       -> "mx"
```

Here is an example of the contents of a MQTT message with topic "sensors/Feath/ambient"
the MQTT Publisher device sends, by default, every minute:

```
	{"ow":"Feath","de":"PC-Lab","dc":"BME280","sc":"meas","vt":"f","ts":1752189817,
 	"reads":{"t":{"v":29,"u":"C","mn":-10,"mx":50},"p":{"v":1005.6,"u":"mB","mn":800,"mx":1200},
  	"a":{"v":63.9,"u":"m","mn":0,"mx":3000},"h":{"v":41.7,"u":"%","mn":0,"mx":100}}}
```

In case of a MQTT message with topic "lights/Feath/toggle":

```
	{"ow":"Feath","de":"PC-Lab","dc":"home","sc":"ligh","vt":"i","ts":1753052138,"toggle":{"v":1,"u":"i","mn":0,"mx":1}}
```
In case of a MQTT message with topic "lights/Feath/color_inc":
```
	{"ow":"Feath","de":"PC-Lab","dc":"colr","sc":"inc","vt":"i","ts":1753052342,"colorInc":{"v":4,"u":"i","mn":0,"mx":9}}
```
In case of a MQTT message with topic "lights/Feath/color_dec":
```
	{"ow":"Feath","de":"PC-Lab","dc":"colr","sc":"dec","vt":"i","ts":1753052302,"colorDec":{"v":3,"u":"i","mn":0,"mx":9}}
```
For the ambient lights of the Presto, in this repo, the following colors are defined:
```
   	0: "BLUE"
	1: "WHITE"
  	2: "RED"
  	3: "ORANGE"
  	4: "GREEN"
  	5: "PINK"
  	6: "CYAN"
  	7: "MAGENTA"
  	8: "YELLOW"
  	9: "GREY"
```
# MQTT Publisher1 (other functionalities)

In case the Arduino sketch of the Publisher1 device encounters that it cannot read the values from the BME280 sensor, the sketch will issue a software reset by calling the function ```reset()``` which calls the function ```ESP.restart()```.

The source of the Arduino sketch for the MQTT Publisher1 device is [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Publisher/Publisher1_v4/Feather_ESP32_S3_TFT_MQTT_multi_topic_v4)

## File secrets.h (for the MQTT Publisher1 device)

To have the Publisher1 device be able to connect to the internet, to: a) get, at intervals, a Unixtime datetime stamp from an NTP server; b) send MQTT messages to the MQTT Broker, you have to fill-in the WiFi SSID and PASSWORD. 

Set the timezone offset from UTC:
```
#define SECRET_TIMEZONE_OFFSET "1" // Europe/Lisbon (UTC offset in hours)
```

Choose the kind of MQTT Broker you want to use. Set it in this line: 
```
	#define SECRET_USE_BROKER_LOCAL "1"             (Note: 1 for local Broker, 0 for remote Broker)
```

Set the hours to set to sleep and to awake from sleep the display:
```
#define SECRET_DISPLAY_SLEEPTIME "23"  // Feather display going to sleep (black) time
#define SECRET_DISPLAY_AWAKETIME "8"   // Feather display wakeup time
```
During the "sleep" hours, the MQTT Publisher device continues to send MQTT messages at the programmed interval time (in this moment once per minute). When one of the buttons A, B, X or Y on the Gamepad QT is pressed the message topic will be changed accordingly. A message of topic change will be shown on the display for a short time. Then a message with the new topic will be send immediately. Next, if no other of the mentioned buttons has been pressed within the time inverval, the topic will change back to the default topic. Then, at the scheduled time interval, messages of the default topic will continue to be transmitted. The Publisher device also continues, at intervals of 15 minutes, to synchronize the external M5Stack Unit RTC from a NTP datetime stamp.

Below th list of all settings in the file secrets.h:

```
#define SECRET_SSID "<Your_WiFi_SSID_here>"
#define SECRET_PASS "<Your_WiFi_Password_here>"
#define SECRET_TIMEZONE_OFFSET "1" // Europe/Lisbon
// #define TIMEZONE_OFFSET "-4" // America/New_York
#define SECRET_USE_BROKER_LOCAL "1"  // We usa a local MQTT broker
#define SECRET_NTP_SERVER1 "1.pt.pool.ntp.org"
#define SECRET_MQTT_BROKER "5.196.78.28" // test.mosquitto.org"
#define SECRET_MQTT_BROKER_LOCAL1 "192.168._.__"  // Local mosquitto broker app on desktop PC Paul2
#define SECRET_MQTT_BROKER_LOCAL2 "192.168._.___"  // Local mosquitto broker app on RPi CM5
#define SECRET_MQTT_PORT "1883"
#define SECRET_MQTT_TOPIC_PREFIX_SENSORS "sensors"
#define SECRET_MQTT_TOPIC_PREFIX_LIGHTS "lights"
#define SECRET_MQTT_TOPIC_PREFIX_TODO "todo"
#define SECRET_MQTT_PUBLISHER "Feath"
#define SECRET_MQTT_CLIENT_ID "Adafruit_Feather_ESP32S3TFT"
#define SECRET_MQTT_TOPIC_SUFFIX_SENSORS "ambient"
#define SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_TOGGLE "toggle"
#define SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_COLOR_DECREASE "color_dec"
#define SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_COLOR_INCREASE "color_inc"
#define SECRET_MQTT_TOPIC_SUFFIX_TODO "todo"
#define SECRET_DISPLAY_SLEEPTIME "23"
#define SECRET_DISPLAY_AWAKETIME "8"
```
- Debug output
  
  If you want debug serial output, change these lines and build the sketch again:
  ```
	62 #ifdef MY_DEBUG         into:     62 #ifndef MY_DEBUG
	63 #undef MY_DEBUG                   63 #define MY_DEBUG
	64 #endif                            64 #endif
  ```

# MQTT Subscriber 
The Pimoroni Presto, in the role of MQTT Subscriber, runs on micropython. The firmware is a special version of micropython. See the link above. The micropython script for this Subscriber device "dims" the screen content during night hours by changing the colour from orange to navy blue (which is more dark). 

The commands of the MQTT messages with topics "lights/Feath/color_inc" and "lights/Feath/color_dec" will only be executed when before has been received a MQTT message with topic "lights/Feath/toggle". If this is not the case the message: "REMOTE: PRESS BTN B!" will be shown on the bottom of the display. See [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/images/Subscriber/20250723_064539.png)

The choice to use a "local MQTT broker" or an "external MQTT broker" is defined in the file "secrets.json".
In the script these lines load the broker choice and print info about this choice as shown below:
```
	311 # MQTT setup
	312 use_local_broker = mqtt_config_dict['use_local_broker']
	313 #print(f"type(use_local_broker) = {type(use_local_broker)}")
	314 if my_debug:
	315   if use_local_broker:
	316      print("Using local Broker")
	317   else:
	318      print("Using external Broker")
	319
	320 if use_local_broker:
	321    BROKER = mqtt_config_dict['broker_local'] # Use the mosquitto broker app on the RaspberryPi CM5
	322 else:
	323    BROKER = mqtt_config_dict['broker_external']

```
The "CLIENT_ID", "PUBLISHER_ID0 and "PUBLISHER_ID1" are also defined in the file "secrets.json". They are read into the script as follows:
```
	354 CLIENT_ID = bytes(mqtt_config_dict['client_id'],'utf-8') # bytes(secrets['mqtt']['client_id'], 'utf-8')
	355 if 'publisher_id0' in mqtt_config_dict.keys():
	356    PUBLISHER_ID0 = mqtt_config_dict['publisher_id0'] # secrets['mqtt']['publisher_id0']
	357 else:
	358    PUBLISHER_ID0 = ""
	359    print(f"key \'publisher_id0\' not found in mqtt_config_dict.keys(): {mqtt_config_dict.keys()}")
	360    
	361 if 'publisher_id1' in mqtt_config_dict.keys():
	362     PUBLISHER_ID1 = mqtt_config_dict['publisher_id1'] # secrets['mqtt']['publisher_id0']
	363 else:
	364     PUBLISHER_ID1 = ""
	365     print(f"key \'publisher_id1\' not found in mqtt_config_dict.keys(): {mqtt_config_dict.keys()}")
```
If you put an SD-card into your Presto, this micropython script will start logging. Log filenames contain a date and time. When the logfile becomes of a certain file length, a new logfile will be created. Another file on SD-card, name: "mqtt_latest_log_fn.txt" will contain the filename of the current logfile. At the moment you force the running script to stop, by issuing the key-combo "<Ctrl+C>", this will provoke a KeyboardInterrupt. In this case the contents of the current logfile will be printed to the Thonny Shell window (serial output). In principle, the logfile(s) created on SD-card will not be deleted by the micropython script, leaving you the opportunity to copy them to another device or just read them once again. If you want old logfile(s) to be deleted automatically, set the following boolean flag to True: 
```
	133 delete_logs = False
```
Beside these type of logfiles there exists also an "err.log" file in the root folder of the filesystem of the Presto.

Example of the contents of the file: "mqtt_latest_log_fn.txt":
```
	mqtt_log_2025-07-20T172657.txt
```

Example of the contents of the current log showed after a KeyboardInterrupt:
```
	loop(): KeyboardInterrupt: exiting...
	
	Size of log file: 8313. Max log file size can be: 51200 bytes.
	Contents of log file: "/sd/mqtt_log_2025-07-20T172657.txt"
	pr_log():  01) ---Log created on: 2025-07-20T17:26:57---
	pr_log():  02) 
	pr_log():  03) 2025-07-20T17:31:25 WiFi connected to: _____________
	pr_log():  04) 2025-07-20T17:31:25 Connected to MQTT broker: 192.168._.___
	pr_log():  05) 2025-07-20T17:31:26 Subscribed to topic: sensors/Feath/ambient
	pr_log():  06) 2025-07-20T17:31:26 Subscribed to topic: lights/Feath/toggle
	pr_log():  07) 2025-07-20T17:31:26 Subscribed to topic: lights/Feath/color_inc
	pr_log():  08) 2025-07-20T17:31:26 Subscribed to topic: lights/Feath/color_dec
	pr_log():  09) 2025-07-20T18:05:37 Session interrupted by user — logging and exiting.
	[...]
```
- Debug output: If you want more output to the serial output (Thonny Shell window), set the following boolean variable to True:
```
	58 my_debug = False
```

## File secrets.json (for the MQTT Subscriber device)
```
{
  "mqtt": {
    "use_local_broker" : 1,
    "broker_local" : "192.168._.___",
    "broker_external": "5.196.78.28",
    "port": "1883",
    "topic0": "sensors/Feath/ambient",
    "topic1": "lights/Feath/toggle",
    "topic2": "lights/Feath/color_inc",
    "topic3": "lights/Feath/color_dec",
    "topic4": "$SYS/broker/clients/connected",
    "topic5": "$SYS/broker/clients/disconnected",
    "client_id":  "PrestoMQTTClient",
    "publisher_id": "Feath"
    "publisher_id0": "Feath",
    "publisher_id1": "PL2XLW",
    "METAR_TAF_API_KEY": "<Your metar-taf.com API KEY>",
    "METAR_TOKEN": "<Your metar-taf.com TOKEN>"
  },
  "wifi" : {
      "ssid" : "<Your WiFi SSID>",
      "pass" : "<Your WiFi PASSWORD"
  },
  "display" : {
    "gotosleep": 23,
    "wakeup": 7
  },
    "timezone" : {
    "tz_utc_offset" : "1",
    "tz" : "Europe/Lisbon"
  }
}
```
## File sys_broker.json  (for the MQTT Subscriber device)
The file "/sys_broker.json" will be cleared at the start of the Subscriber script. As soon as arrive a $SYS topic message of one of the $SYS topics subscribed, the topic name and its value will be added to sys_broker.json. As soon as the running of the sketch is interrupted by a key-combo: <Ctrl+C>, the contents of the file sys_broker.json will be printed to the Thonny Shell window.

```
sys_broker_dict written to file: "sys_broker.json"
Size of sys_broker json file: 40.
Contents of sys_broker json file: "/sys_broker.json"
pr_log():  01) {"sys_broker": {"clients/connected": 2}}
```

# MQTT Broker

If you, like me, also use a Raspberry Pi model to host a Mosquitto broker application, see the files in the folder [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Broker/etc)
- ```/etc/hosts.allow``` : insert in this file the ip-addres of your mosquitto broker. In my case: ```mosquitto: 127.0.0.1```
- ```/etc/mosquitto/mosquitto.conf```. See the contents of the mosquitto.conf file that I use in the folder [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Broker/etc/mosquitto).

### Broker log
The broker application saves its log in ```\var\log\mosquitto\mosquitto.log```.

To see the status of the broker app on a Raspberry Pi, from a terminal session, type:
```
sudo systemctl status mosquitto.service
```
See an example of the mosquitto.service status log [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/doc/Broker/Broker.service_log.txt).

Photo of the result of this command see: [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/images/Broker/20250724_20h56m18s_mosquitto.service_status.png)

For more information about logging for the mosquitto app see: [mosquitto logging](https://cedalo.com/blog/mosquitto-mqtt-broker-logging/)

See also photos of sites where to download the mosquitto broker app for Raspberry Pi or for a MS Windows PC [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Broker).



- Broker reset: in the case you reset or reboot your local broker device: wait until the local broker is running. Then reset both the MQTT Publisher device and the MQTT Subscriber(s) device(s) so that they report themselves to the MQTT local broker device as Publisher and Subscriber(s).


# Adafruit Gamepad QT

In the Arduino sketch for the MQTT Publisher1 device I have added functionality to read the state of the buttons and the joystick.
The joystick is not used yet. The buttons are defined as follows:
```
+----------+-----------------------------------------------+
| Button   |  Function                                     |
+----------+-----------------------------------------------+
|   A      | switch to MQTT topic "sensors/Feath/ambient"  |
|   B      | switch to MQTT topic "lights/Feath/toggle"    |
|   X      | switch to MQTT topic "lights/Feath/color_inc" |
|   Y      | switch to MQTT topic "lights/Feath/color_dec" |
|  SELECT  | show information about button functions etc.  |
|  START   | execute a software reset                      |
+----------+-----------------------------------------------+
```

# Hardware used

### For the MQTT Publisher1 device: 
Adafruit Feather ESP32-S3 TFT [info](https://www.adafruit.com/product/5483);

and for version 2: Pimoroni Qw/ST I2C Game controller (PIM752) [info](https://shop.pimoroni.com/products/qwst-pad?variant=53514400596347);

Accessories for the MQTT Publisher device:
Equipment connected to the Publisher device:
- Pimoroni multi-sensor-stick (PIM 745) [info](https://shop.pimoroni.com/products/multi-sensor-stick?variant=42169525633107);
- M5Stack Unit-RTC [info](https://docs.m5stack.com/en/unit/UNIT%20RTC);
- M5Stack Grove 1 to 3 HUB Expansion Unit [info](https://shop.m5stack.com/products/mini-hub-module)

### For the MQTT Broker device:
- a Raspberry Pi Compute Module 5 [info](https://www.raspberrypi.com/products/compute-module-5/?variant=cm5-104032);
- a Raspberry Pi Compute Module IO Board [info](https://thepihut.com/products/raspberry-pi-compute-module-5-io-board)
- a case for the Raspberry Pi Compute Module 5 [info](https://thepihut.com/products/raspberry-pi-compute-module-5-io-case)

### For the MQTT Subscriber device:
- Pimoroni Presto device: [info](https://shop.pimoroni.com/products/presto?variant=54894104019323).

# Publisher1 device and external I2C devices wiring

For an image of the I2C wiring see [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/images/20250720_202423_hardware.png). Note that this is an edited image. There was another device on the breadboard. I covered that part to not confuse the image with the unused device.

# Known problems

### DC Power 
My advise for the Publisher1 device: the Adafruit Feather ESP32-S3 TFT (and probably any other device used as MQTT Publisher device) and also the attached BME280 sensor, it is really necessary to use a 5,1 Volt DC power source of good quality. My experience is at this hardware / this sensor needs at least 5,1 Volt DC. For example: the USB port of my desktop PC delivered 5,132 Volt DC. That was OK. I also used an original Raspberry Pi 5,1 Volt DC power apdapter. That was also OK. When I used a power source that delivered 5,058 Volt DC, that was not insufficient. At times the BME280 was not recognized and at times the MQTT Publisher device sent messages containing a wrong NTP Unixtime value as MsgID. When using a good quality 5,1 Volt DC power supply, the MQTT Publisher device runs many hours without problem, resulting in the MQTT Broker receiving MQTT message correctly and the MQTT Subscriber device(s) do the same.

### I2C bus - connecting three or more external devices to the same I2C bus
 
 #### Devices
  - M5Stack M5Unit-RTC (Address 0x51);
  - Pimoroni multi-sensor-stick, ambient sensor BME280 (Address 0x76);
  - Adafruit Gamepad QT (Address: 0x50) or:
  - Pimoroni Qw/ST Pad (I2C game controller (Addressses: 0x21, 0x23) 1x or 2x to be used with Version 2 of the sketch.

 Beside these three or more external I2C devices the Adafruit Feather ESP32-S3 TFT board has other internal devices on the I2C bus:
 The I2C bus scan reported devices found with the following addresses: 0x23, 0x36, 0x50, 0x51, 0x6A, 0x76.
 The three external devices are connected to the Stemma QT/Qwiic connector of the Adafruit Feather ESP32-S3 TFT board, via a M5Stack 3-port Grove Hub. 
 Initially I had the Adafruit Gamepad QT connected in series with the Pimoroni multi-sensor-stick, however this caused I2C bus problems. In fact the M5Unit-RTC was giving unreliable datetime   values after having been set with a correct NTP unixtime.  After disconnecting the Gamepad QT from the multi-sensor-stick and then connecting the Gamepad QT to the 3-port Grove Hub, the I2C bus problems were history. From then on the Arduino sketch running on the Adafruit Feather ESP32-S3 TFT received correct datetime data from the M5Unit-RTC.

# Updates

## 2025-08-18 Publisher1, sketch version 2 
Added:
- Using another type of game controller, the Pimoroni Qw/ST Pad I2C game controller.
- For this I ported a Pimoroni qwstpad-micropython library for micropython to C++. See the files qwstpad.h and qwstpad.cpp. See [repo about port](https://github.com/PaulskPt/qwstpad-arduino)
- Functionality to use one or (up to four) of these Pimoroni Qw/ST Pad I2C game controllers. They have more buttons than the Adafruit Gamepad Qt controller that I used for version 1. The buttons L(eft) and R(ight) are defined to change the color of the display text of the remote Pimoroni Presto subscriber.
- Added functionality to blink all or one of the four LEDs on the Qw/ST Pad game controllers. I tested up to two Qw/ST game controllers. However, because I have also other I2C devices connected to the Adafruit ESP32-S3 TFT board, I had to connect the game controllers to the second I2C port.
- Added two MQTT message topics: 
- "ligths/Feath/dclr_inc". Containing a display text color increase command from a remote controller
- "lights/Feath/dclr_dec". Containing a display text color decrease command from a remote controller
- changed the contents of the MQTT message structure. In version 1 for the sensor/Feath/ambient topic message the first part, containing general data, had no name, the data part had the name "reads". In version 2 the general data section, in fact a nested JSon object, is given the name "head". Because of length of MQTT message problem on the Presto subscriber (micropython limitation?) the name "head" is shortened to "hd". The payload part of the MQTT message can be maximum 256 bytes. The new general section is as follows (example): "hd": {"ow": "Feath", "de": "Lab", "dc": "BME280", "sc": "meas", "vt": "f", "ts": 1755622875}," while the data section "read" stays the same as in Version 1.

## Subscriber script updates

### 2025-08-22
Added:
- functionality to remotely change the color of the display text (using buttons L(eft) and R(ight) on a Qw/ST I2C game controller, connected to the MQTT Publisher device).
  To change the display text color, I added the function redraw(). This new function is similar to the draw() function. The difference is that draw() uses data from the MQTT message received at that moment while redraw() uses data from the latest received and stored MQTT message.
  The idea is: upon receiving a MQTT message containing a display text color change command, the display is cleared,
  the text color is set to the new color and the screen is build-up using the data from the latest received
  MQTT message with topic "sensor/Feath/ambient". To show that not the most recent data is shown, the text "RD"
  will be shown in the top-right corner of the screen. As soon as a next MQTT message with topic "sensor/Feath/ambient"
  is received, the normal draw() function will continue to buid-up the screen, using the new text color.
- objects for each of the non $SYS topics (sensor_obj, toggle_obj, amb_obj, disp_obj and metar_obj) are created and
  maintained. They act as "memory" for some settings, while "memory" of received MQTT messages is done by saving them
  in a file on SD-Card.
- functionality to maintain certain maximum of received messages in a file on SD-Card (/sd/msg_hist.json);

- In the Arduino sketch for the MQTT Publisher1 device I have added functionality to read the state of the buttons.
The buttons of the Pimoroni Qw/ST I2C game controller are defined as follows:

# Pimoroni Qw/ST I2C game controller
```
+----------+----------------------------------------------------------------+
| Button   |  Function                                                      |
+----------+----------------------------------------------------------------+
|   A      | switch to MQTT topic "sensors/Feath/ambient"                   |
|   B      | switch to MQTT topic "lights/Feath/toggle"                     |
|  X/U     | switch to MQTT topic "lights/Feath/color_inc" (= Ambient LEDs) |
|  Y/D     | switch to MQTT topic "lights/Feath/color_dec" (= same          |
|   L      | decrease display text color, topic "lights/Feath/dclr_dec"     |
|   R      | increase display text color, topic "lights/Feath/dclr_inc"     |
|   -      | show information about button functions etc.                   |
|   +      | execute a software reset                                       |
+----------+----------------------------------------------------------------+
```

### Update 2025-09-07
In this update changed to "Presto(full_res=hi_res)" mode. Another, better font type. Vector.text() and some other improvements.

Script upgraded to receive and display MQTT messages with topic ```weather/PL2XLW/metar```.

See: [photo](https://imgur.com/a/SKHAVRJ) and [video](https://imgur.com/a/Mbb5P9i).  For images comparison between the Pimoroni Presto and an Unexpected Maker SQUiXL see: [photos](https://imgur.com/a/ARvUNSK)

### Update 2025-09-19
For MQTT messages of topic "weather/PL2XLW/LPPT" added functionality to display (and print) metar-taf.com account data: "Status" and "Credits".
In the payload this is for example: 
```
	"acc": {"st": 1, "cr": 1201}
```

## Publisher1 update
This version adds DST awareness to the timezone offset. In secret.h one can choose between #define REGION_EUROPE, #define REGION_USA or create ones own region data.
In the sketch these variables are set from the values in file ```secret.h```.
```
	int tzDST_Offset = atoi(SECRET_TIMEZONE_DST_OFFSET); // can be negative or positive (hours)
	int tzSTD_Offset = atoi(SECRET_TIMEZONE_STD_OFFSET); // can be negative or positive (hours)
	const char SECRET_TIMEZONE_DST_ID[] = SECRET_TZ_DST_ID;
	const char SECRET_TIMEZONE_STD_ID[] = SECRET_TZ_STD_ID;
```
In the sketch there are these DST related definitions (lines 120-142):
```
// Used by isDST()
struct DstPeriod {
  time_t start;
  time_t end;
};

// Used by isDST()
#ifdef REGION_EUROPE
std::map<std::string, DstPeriod> dst_start_end = {
  { "2025", {1741503600, 1762063200} },
  { "2026", {1772953200, 1793512800} },
  { "2027", {1805007600, 1825567200} },
  { "2028": {1837645200, 1856397600} }
};
#endif

#ifdef REGION_USA
std::map<std::string, DstPeriod> dst_start_end = {
  { "2025", {1741503600, 1762063200} },
  { "2026", {1772953200, 1793512800} },
  { "2027", {1805007600, 1825567200} },
  { "2028", {1836457200, 1857016800} }
};
#endif

```

## Publisher2 device added 

### (Pimoroni Pico LiPo 2XL W) (Update 2025-08-26)
This Publisher2 [info](https://shop.pimoroni.com/products/pimoroni-pico-lipo-2-xl-w?variant=55447911006587) is dedicated to receive, at intervals, weather messages from server ```metar-taf.com```, filter the METAR section, compose and send, at other intervals, MQTT messages with the topic ```weather/PL2XLW/metar```.
See [serial output](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/doc/Publisher/MQTT_Publisher2_PuTTY_session_output.txt) and for Publisher2 version2 [serial output](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/doc/Publisher/Publisher2_V2/2025-09-15_19h11_Pimoroni_PL2XLW_MPY_metar_mqtt_epd_monitor_output.txt).

### Note about Publisher unixTime(s)
Te unixTime the Publisher devices send is in GMT. It is up to the algorithm of the MQTT Subscriber to present the received unixTime as localTime or GMT. I have chosen to have the Subscriber device convert and display the received unixTime to ISO6801 format (example: "hh:mm:ss+01:00") [photos](https://imgur.com/a/MmotOGn)

## Publisher2 updates

### 2025-09-09
Added several changes to improve the script. Most changes are in function "ck_for_next_metar()". Now the calculation for requesting the next METAR and subsequent sending of a MQTT METAR topic message, is derived from the "observed" key in the received METAR message. The value of the "observed" key is a unixtime. This time will be increased by 40 minutes. Airport METAR's are refreshed each 30 minutes. Tests revealed that requesting a new METAR at least 10 minutes after its time of publication, is a reliable moment to "catch" a METAR with "fresh" data compared with the METAR message received before. To limit, during tests, the "loss" of credits from my subscription with metar-taf.com, I limited the number of METAR fetches to 3
(see file: "secrets.json", key MAX_METAR_FETCHED).

### 2025-09-14
Added functionality to display the received METAR data onto a connected Lolin 2.13 inch 3-Color e-Paper display. [photo](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/images/Publisher/Publisher2_V2/20250914_204914.jpg)

Added hardware: Lolin 2.13 inch 3-Color e-Paper display [info](https://www.wemos.cc/en/latest/d1_mini_shield/epd_2_13_3.html). Note that this ePD has the following screen dimensions: 250 x 122 pixels, as printed on the backside of the board in the link and not as shown on the image of the front of this ePD in the link.

### 2025-09-15
Added a startup file "main.py" that calls the script "metar_mqtt_epd.py". In this script added function splitMetarforDisplay(). Changes in function draw() for displaying the metar data. Renamed function "main()" into "go_epd()".

### 2025-09-17
Added Publisher2 V3 [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/src/Publisher/Publisher2_V3/metar_mqtt_edp_udplogger). In this version added functionality to send print statements as UDP packets to any UDP Listener device in the LAN. In this way the Publisher2 board doesn't need to be connected to a PC to see its print output. Only need another device in the same LAN running a very small python script to print to the terminal window any print data received through the UDP packets. In my case I use as "UDP Listener" the Raspberry Pi Compute Module 5, the device I also use as MQTT Broker. Source code: [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/src/UDP_Listener/udp_rx.py). Example output: [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/doc/UDP_Listener/UDP_Listener_output.txt).

### 2025-09-19
Added functionality to send metar-taf.com account information. In the MQTT message payload added a key: "acc" with the contents, for example: "acc" : {"st" : 1, "cr" : 1201}, in which "acc" stands for "account", "st" for "Status" and "cr" for "Credits" (remaining).

### 2025-09-27
Added Publisher2 V4 [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Publisher/Publisher2_V4/metar_mqtt_edp_tcplogger) In this version replaced UDP packets by TCP packets to any TCP Listerner device in the LAN. Added a "TCP Listener" Python script that I tested on a Raspberry Pi 4B-4GB. Source code: [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/src/TCP_Listener/tcp_rx_v2.py). Serial output: [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/doc/TCP_Listener/2025-09-27_10h23_TCP_Listener_output.txt). See also the contents of the file "secrets.json", key "lan" [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/src/Publisher/Publisher2_V4/metar_mqtt_edp_tcplogger/secrets.json). 
Below is the section in the Publisher2 V4 script (lines 81-114) where the values for eventual "target" devices in the LAN are read from the file "secrets.json". The list "tcp_targets" (line 88) needs to contain the variable name(s) of the targets intended. Note that to my experience the TCP Listener devices using a RP2040 or RP2035, like the Pimoroni Pico Plus 2W and the iLabs RPICO32 had poor performance as TCP Listener device. They "missed" a lot of TCP packets sent by the Publisher2 (Pimoroni Pico Plus 2XL W). The Raspberry Pi devices: RPiCM5 and RPi4B-4GB performed excellent as TCP Listener device. These deviced missed no TCP packets sent. As written above, below the code section that reads the IP-addresses of "target" devices:
```
	# Set the IP addresses of TCP targets
	# Note that TCP can only send to one IP-address at a time!
	t1 = secrets['lan']['presto']  # '192.168.1.__'  # Pimoroni Presto - MQTT Subscriber1
	t2 = secrets['lan']['pp2w']    # '192.168.1.__'  # Pimoroni Pico Plus 2W nr1 - TCP Listener
	t3 = secrets['lan']['rpico32'] # '192.168.1.__'  # iLabs RPICO32 - TCP Listener
	t4 = secrets['lan']['rpicm5']  # '192.168.1.114' # Raspberry Pi Compute Module 5 - MQTT Broker - TCP Listener
	t5 = secrets['lan']['rpi4b']   # '192.168.1.__'  # Raspberry Pi 4B-4GB with RP senseHat V2 - TCP Listener
	tcp_targets = [t5]  # was [t2, t4]
	
	try:
	    # Wait until connected
	    while not net.isconnected():
	        time.sleep(0.2)
	
	    TCP_PORT = 12345
	    use_tcp_logger = True
	    tcp_logger_verbose = False
	    tcp_logger = TCPLogger(TCP_PORT, tcp_targets, use_tcp_logger)
	    
	    ip, subnet, _, _ = net.ifconfig()
	    time.sleep(0.1)
	    # Use a helper to calculate broadcast IP from IP and subnet
	    tcp_logger.write(BOARD+TAG+f"ip: {ip}, subnet: {subnet}"+"\n")
	
	    tcp_logger.write(BOARD+TAG+"tcp_target(s): " + f"{tcp_targets}\n")
	    # ===== Create an instance of the TCPLogger class =====
	
	
	except OSError as e:
	    tcp_logger.write(BOARD+TAG+f"OSError: {e}\n")
	    raise RuntimeError
	except Exception as e:
	    tcp_logger.write(BOARD+TAG+f"Exception: {e}\n")
    raise RuntimeError
```

## General cleanup 2025-09-15
Cleaned up various versions for the Subscriber device and various versions of the Publisher device1. For each only one version is left.
