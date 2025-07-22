# Receiving and displaying MQTT messages on a Pimoroni Presto device

by Paulus Schulinck (Github handle: @PaulskPt)

If you do not know what is the MQTT communication protocol see: [MQTT](https://en.wikipedia.org/wiki/MQTT).

For a successful MQTT communication you need: 
- a MQTT Publisher device. In my case: an Adafruit Feather ESP32-S3 TFT board;
- a MQTT Broker device. This can be an online broker or a Broker device in your Local Area Network (LAN). I prefered the latter. In my case: a Raspberry Pi Compute Module 5.
- one or more MQTT Subscriber device(s). This repo is intended to use a Pimoroni Presto as Subscriber device.

How to install?

Download the latest version of Pimoroni [Presto FW](https://github.com/pimoroni/presto/releases/tag/v0.1.0). Flash this firmware onto your Presto. This can be done from within the Thonny IDE. For this subscriber device, copy the files of this repo from these subfolders [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Subscriber) to a folder of your preference, for example: 
```
C:\<Users>\<User>\Documents\Hardware\Pimoroni\Presto\Micropython\mqtt\
```
For the Publisher device, copy the files of this repo from these subfolders [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Publisher) to a folder of your preference, for example: 
```
C:\<Users>\<User>\Documents\Arduino\Feather_ESP32_S3_TFT_MQTT_multi_topic\
```


You need to have installed on your PC: 
- Thonny IDE or equivalent. Needed for the Pimoroni Presto device.
- Arduino IDE v2.3.5. Needed for the Adafruit Feather ESP32-S3-TFT device. Do not use the Arduino (Cloud) online IDE because that limits the possibility to change library files to your needs.
  For example I added a function to the M5Stack M5Unit-RTC library for the Arduino IDE. I added the function:  ``setUnixTime(unsigned long uxTime)```.
  For your convenience I added this modified library [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Arduino/libraries/).

# MQTT message content

The structure for the MQTT message payload is shown below. Except for the members "timestampStr" and "timestamp" the structure members are used in the MQTT messages that my MQTT Publisher device sends. This structure I copied from the firmware for an Unexpected Maker SQUiXL device, however I added three members.

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

The mqtt messages are defined in a Json format. The messages that my Publisher device sends contain one main Json object "doc". Here is an example of the contents of this main Json object:
```
	{"ow":"Feath","de":"PC-Lab","dc":"BME280","sc":"meas","vt":"f","ts":1753098395,[...]}
```
Then, depending on the topic, the MQTT messages my Publisher device sends, contain minimum one nested Json object and maximum four nested Json objects.
The MQTT messages with topic "sensors/Feath/ambient" have four nested Json objects (see below). The other MQTT messages with topics:
"lights/Feath/toggle", "lights/Feath/color_dec" or "lights/Feath/color_inc", contain one nested Json object (see below).

To keep the length of the payload of the MQTT messages under 256 bytes, I have chosen to abbreviate the names of this struct.

Why keep the payload length under 256 bytes? 

I had a problem when using a Pimoroni Presto device as Subscriber device, which uses Micropython.
I discovered that MQTT messages received were cutoff. Initially my MQTT Publisher device sent messages with full names of the structure shown above, which made the payload longer than 256 bytes. That is why I decided to abbreviate the names. I managed to reduce the payload length to less than 256 bytes. Since then the MQTT messages sent by the MQTT Publisher device were received complete.

```
In the "doc" section:
owner        -> ow
description  -> de
device_class -> dc
state_class  -> sc     and its class "measurement" -> "meas"
value_type   -> vt     and the value_type "float"  -> "f"
timestamp    -> ts
```
In case of a MQTT message with topic: "sensor/Feath/ambient"
In the MQTT "payload" with name "reads" there are:
four nested Json objects for each (term) of the BME280 sensor: "temperature", "pressure", "altitude" and "humidity":

```
	 nested Json object (term) "temperature" -> "t"
	 nested Json object (term) "pressure"    -> "p"
	 nested Json object (term) "altitude"    -> "a"
	 nested Json object (term) "humidity"    -> "h"
```

In case of a MQTT message with topic: "lights/Feath/toggle"
the only nested Json object contains, for example: 
```
  	[...]"toggle":{"v":1,"u":"i","mn":1,"mx":0}}, 
```
where "v":1 stands for Toggle leds ON.

In case of a MQTT message with topic: "lights/Feath/color_inc",
the only nested Json object contains, for example: 
```
  	[...]"colorInc":{"v":4,"u":"i","mn":0,"mx":9}}
```
where "v":4 stands for ColorIndex value 4 (minim 0 and maximum 9)

In case of a MQTT message with topic: "lights/Feath/color_dec",
the only nested Json object contains, for example:
```
  	[...]"colorDec":{"v":3,"u":"i","mn":0,"mx":9}}
```

Each nested Json object has the same definition:
```
	"sensor_value"        -> "v"
	"unit_of_measurement" -> "u"
	"minimum_value"       -> "mn"
	"maximum_value"       -> "mx"
```

Here is an example of the contents of a MQTT message with topic "sensors/Feath/ambient"
my MQTT Publisher device sends every minute:

```
	{"ow":"Feath","de":"PC-Lab","dc":"BME280","sc":"meas","vt":"f","ts":1752189817,
 	"reads":{"t":{"v":29,"u":"C","mn":-10,"mx":50},"p":{"v":1005.6,"u":"mB","mn":800,"mx":1200},
  	"a":{"v":63.9,"u":"m","mn":0,"mx":3000},"h":{"v":41.7,"u":"%","mn":0,"mx":100}}}
```

In case of a MQTT message with topic "lights/Feath/toggle":

```
	{"ow":"Feath","de":"PC-Lab","dc":"home","sc":"ligh","vt":"i","ts":1753052138,"toggle":{"v":1,"u":"i","mn":1,"mx":0}}
```
In case of a MQTT message with topic "lights/Feath/color_inc":
```
	{"ow":"Feath","de":"PC-Lab","dc":"colr","sc":"inc","vt":"i","ts":1753052342,"colorInc":{"v":4,"u":"i","mn":0,"mx":9}}
```
In case of a MQTT message with topic "lights/Feath/color_dec":
```
	{"ow":"Feath","de":"PC-Lab","dc":"colr","sc":"dec","vt":"i","ts":1753052302,"colorDec":{"v":3,"u":"i","mn":0,"mx":9}}
```

# MQTT Publisher (other functionalities)

To build and upload the Arduino sketch for the MQTT Publisher device I used the Arduino IDE v2.3.5. In the Arduino sketch for the MQTT Publisher (Adafruit Feather ESP32-S3 TFT board) I added functionality to set the display to "sleep" at a time defined in the file ```secrets.h```. In this moment 23h. And a "wakeup" time. In this moment 8h. See in the file secrets.h: 
```
#define SECRET_DISPLAY_SLEEPTIME "23"  // Feather display going to sleep (black) time
#define SECRET_DISPLAY_AWAKETIME "8"   // Feather display wakeup time
```
During the "sleep" hours, the MQTT Publisher device continues to send MQTT messages at the programmed interval time (in this moment once per minute). The Publisher repeats to send messages with the same topic as long as the user doesn't change the topic by pressing one of the buttons A, B, X or Y on the Gamepad QT. The Publisher device also continues, at intervals of 15 minutes, to synchronize the external M5Stack Unit RTC from a NTP datetime stamp.

In case the Arduino sketch of the Publisher device encounters that it cannot read the values from the BME280 sensor, the sketch will issue a software reset by calling the function ```reset()``` which calls the function ```ESP.restart()```.

The source of the Arduino sketch for the MQTT Publisher device is [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Publisher)

# File secrets.h (for the MQTT Publisher device)

To have the Publisher device be able to connect to the internet, to get, at intervals, a Unixtime datetime stamp from an NTP server, you have to fill-in the WiFi SSID and PASSWORD. Further you can change the following settings in the file secrets.h:

```
#define SECRET_SSID "<Your_WiFi_SSID_here>"
#define SECRET_PASS "<Your_WiFi_Password_here>"
#define SECRET_TIMEZONE_OFFSET "1" // Europe/Lisbon (UTC offset in hours)
// #define TIMEZONE_OFFSET "-4" // America/New_York
#define SECRET_NTP_SERVER1 "1.pt.pool.ntp.org"
#define SECRET_MQTT_BROKER "5.196.78.28" // test.mosquitto.org"
#define SECRET_MQTT_BROKER_LOCAL1 "192.168._.___"  // Your Local mosquitto broker app on PC ____
#define SECRET_MQTT_BROKER_LOCAL2 "192.168._.___"  // Your Local mosquitto broker app on Raspberry Pi ___ (in my case a RPi CM5)
#define SECRET_MQTT_PORT "1883" 
#define SECRET_MQTT_TOPIC_PREFIX_SENSORS "sensors"
#define SECRET_MQTT_TOPIC_PREFIX_LIGHTS "lights"
#define SECRET_MQTT_TOPIC_PREFIX_TODO "todo"
#define SECRET_MQTT_PUBLISHER "Feath"
#define SECRET_MQTT_TOPIC_SUFFIX_SENSORS "ambient"   // Sent by the Publisher device (in my case an Adafruit Feather ESP32-S3 TFT)
#define SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_TOGGLE "toggle"
#define SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_COLOR_DECREASE "color_dec"
#define SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_COLOR_INCREASE "color_inc"
#define SECRET_MQTT_TOPIC_SUFFIX_TODO "todo"
#define SECRET_DISPLAY_SLEEPTIME "23"  // Feather display going to sleep (black) time
#define SECRET_DISPLAY_AWAKETIME "8"   // Feather display wakeup time
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
The choice to use a "local MQTT broker" or an "external MQTT broker" is defined in this line of the micropython script:
```
	60 use_local_broker = True # Use the BROKER running on a local PC (in my case a Raspberry Pi Compute Module 5).
```
The "publisher_id" and "subscriber_id" are also defined in the file "secrets.json". They are read into the script as follows:
```
	139 CLIENT_ID = bytes(secrets['mqtt']['client_id'], 'utf-8')
	140 PUBLISHER_ID = secrets['mqtt']['publisher_id']

```
If you put an SD-card into your Presto, this micropython script will start logging. Logfile names contain a date and time. When the logfile becomes of a certain file length, a new logfile will be created. Another file on SD-card, name: "mqtt_latest_log_fn.txt" will contain the filename of the current logfile. At the moment you force the running script to stop, by issuing the key-combo "<Ctrl+C>", this will provoke a KeyboardInterrupt. In this case the contents of the current logfile will be printed to the Thonny Shell window (serial output). In principle, the logfile(s) created on SD-card will not be deleted by the micropython script, leaving you the opportunity to copy them to another device or just read them once again. If you want old logfile(s) to be deleted automatically, set the following boolean flag to True: 
```
	59 delete_logs = False
```
Beside these type of logfiles there exists also an "err.log" file in the root folder of the filesystem of the Presto.

Example of the contents of the file: "mqtt_latest_log_fn.txt":
```
	mqtt_log_2025-07-20T172657.txt
```

Example of the log showed after a KeyboardInterrupt:
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

# File secrets.json (for the MQTT Subscriber device)
```
{
  "mqtt": {
    "broker_local0" : "192.168._.__",
    "broker_local1" : "192.168._.___",           <<<=== This one is used when you opt for a "local Broker". Fill-in the IP-address.
    "broker_local2" : "curl mqtt://127.0.0.1",
    "broker_local3" : "curl mqtt://localhost",
    "local_server" : "192.168._.__",
    "broker_external": "5.196.78.28",
    "port": "1883",
    "topic0": "sensors/Feath/ambient",
    "topic1": "lights/Feath/toggle",
    "topic2": "lights/Feath/color_inc",
    "topic3": "lights/Feath/color_dec",
    "client_id":  "PrestoMQTTClient",
    "publisher_id": "Feath"
  },
  "wifi" : {
      "ssid" : "<Your WiFi SSID here>",
      "pass" : "<Your WiFi Password here>"
  },
  "timezone" : {
      "utc_offset_in_hrs" : "1",
      "utc_offset_in_secs" : "3600"
  },
  "mqtt_server" : {
      "url" : "mqtt://localhost",
      "url2" : "mqtt://127.0.0.1"
  }
}
```
# MQTT broker

If you, like me, also use a Raspberry Pi model to host a Mosquitto broker application, see the files in the folder [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Broker/etc)
- ```/etc/hosts.allow``` : insert in this file the ip-addres of your mosquitto broker. In my case: ```mosquitto: 127.0.0.1```
- ```/etc/mosquitto/mosquitto.conf```. See the contents of the mosquitto.conf file that I use in the folder [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Broker/etc/mosquitto).

See also photos of sites where to download the mosquitto broker app for Raspberry Pi or for a MS Windows PC [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Broker).

- Broker reset: in the case you reset or reboot your local broker device, after the local broker is running you need to reset both the MQTT Publisher device and the MQTT Subscriber(s) device(s) so that they report themselves to the MQTT local broker device as Publisher and Subscriber(s).


# Adafruit Gamepad QT

In the Arduino sketch for the MQTT Publisher device I have added functionality to read the state of the buttons and the joystick.
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

# Hardware used:

For the MQTT Publisher device: Adafruit Feather ESP32-S3 TFT [info](https://www.adafruit.com/product/5483);

Accessories for the MQTT Publisher device:
Equipment connected to the Publisher device:
- Pimoroni multi-sensor-stick (PIM 745) [info](https://shop.pimoroni.com/products/multi-sensor-stick?variant=42169525633107);
- M5Stack Unit-RTC [info](https://docs.m5stack.com/en/unit/UNIT%20RTC);
- M5Stack Grove Hub [info](https://shop.m5stack.com/products/mini-hub-module)

For the MQTT Broker device:
- a Raspberry Pi Compute Module 5 [info](https://www.raspberrypi.com/products/compute-module-5/?variant=cm5-104032);
- a Raspberry Pi Compute Module IO Board [info](https://thepihut.com/products/raspberry-pi-compute-module-5-io-board)
- a case for the Raspberry Pi Compute Module 5 [info](https://thepihut.com/products/raspberry-pi-compute-module-5-io-case)

For the MQTT Subscriber device:
- Pimoroni Presto device: [info](https://shop.pimoroni.com/products/presto?variant=54894104019323).

# Publisher device and accessories
For an image of the I2C wiring see [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/images/20250720_202423_hardware.png). Note that this is an edited image. There was another device on the breadboard. I covered that part to not confuse the image with the unused device.

# Known problems:

My advise for the Publisher device: the Adafruit Feather ESP32-S3 TFT (and probably any other device used as MQTT Publisher device) and also the attached BME280 sensor, it is really necessary to use a 5,1 Volt DC power source of good quality. My experience is at this hardware / this sensor needs at least 5,1 Volt DC. For example: the USB port of my desktop PC delivered 5,132 Volt DC. That was OK. I also used an original Raspberry Pi 5,1 Volt DC power apdapter. That was also OK. When I used a power source that delivered 5,058 Volt DC, that was not insufficient. At times the BME280 was not recognized and at times the MQTT Publisher device sent messages containing a wrong NTP Unixtime value as MsgID. When using a good quality 5,1 Volt DC power supply, the MQTT Publisher device runs many hours without problem, resulting in the MQTT Broker receiving MQTT message correctly and the MQTT Subscriber device(s) do the same.

 Note about connecting 3 external devices to the same I2C bus:
 Devices: 
  - M5Stack M5Unit-RTC (Address 0x51);
  - Pimoroni multi-sensor-stick, ambient sensor BME280 (Address 0x76);
  - Adafruit Gamepad QT (Address: 0x50).
 Beside these three external I2C devices the Adafruit Feather ESP32-S3 TFT board has other internal devices on the I2C bus:
 The I2C bus scan reported devices found with the following addresses: 0x23, 0x36, 0x50, 0x51, 0x6A, 0x76.
 The three external devices are connected to the Stemma QT/Qwiic connector of the Adafruit Feather ESP32-S3 TFT board, via a M5Stack 3-port Grove Hub. 
 Initially I had the Adafruit Gamepad QT connected in series with the Pimoroni multi-sensor-stick, however this caused I2C bus problems. In fact the M5Unit-RTC was giving unreliable datetime values after having been set with a correct NTP unixtime.  After disconnecting the Gamepad QT from the multi-sensor-stick and then connecting the Gamepad QT to the 3-port Grove Hub, the I2C bus problems were history. From then on the Arduino sketch running on the Adafruit Feather ESP32-S3 TFT received correct datetime data from the M5Unit-RTC.

