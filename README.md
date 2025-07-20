# Receiving and displaying MQTT messages on a Pimoroni Presto device

by Paulus Schulinck (Github handle: @PaulskPt)

If you do not know what is the MQTT communication protocol see: [MQTT](https://en.wikipedia.org/wiki/MQTT).

For a successful MQTT communication you need: 
- a MQTT Publisher device. In my case: an Adafruit Feather ESP32-S3 TFT board;
- a MQTT Broker device. This can be an online broker or a Broker device in your Local Area Network (LAN). I prefered the latter. In my case: a Raspberry Pi Compute Module 5.
- one or more MQTT Subscriber device(s). This repo is intended to use a Pimoroni Presto as Subscriber device.

How to install?

Download the latest version of Pimoroni [Presto FW](https://github.com/pimoroni/presto/releases/tag/v0.1.0). Install that repo in your PC in a folder of your preference. Copy the files of this repo from the subfolders [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Subscriber) to a folder of your preference, for example: 
```
C:\<Users>\<User>\Documents\Hardware\Pimoroni\Presto\Micropython\mqtt\
```
Copy the files of this repo from the subfolders [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Publisher) to a folder of your preference, for example: 
```
C:\<Users>\<User>\Documents\Arduino\Feather_ESP32_S3_TFT_MQTT_multi_topic\
```


You need to have installed on your PC: 
- Thonny IDE or equivalent. Needed for the Pimoroni Presto device.
- Arduino IDE v2.3.5. Needed for the Adafruit Feather ESP32-S3-TFT device. Do not use the Arduino (Cloud) online IDE because that limits the possibility to change library files to your needs.
  For example I added a function to the M5Stack M5Unit-RTC library for the Arduino IDE. I added the function:  ``setUnixTime(unsigned long uxTime)```.
  For your convenience I added this modified library [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Arduino/libraries/).

# MQTT message content

The structure for the MQTT message payload below, contains most of the members that are used in the MQTT messages that my MQTT Publisher device sends.
This structure I copied from the firmware for a Unexpected Maker SQUiXL device.

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

The mqtt messages are defined in a Json format.
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
In the "reads" subsection:
another four sub-sub-sections for each (term) of the BME280 sensor: "temperature", "pressure", "altitude" and "humidity":

```
	 sub-sub-section (term) "temperature" -> "t"
	 sub-sub-section (term) "pressure"    -> "p"
	 sub-sub-section (term) "altitude"    -> "a"
	 sub-sub-section (term) "humidity"    -> "h"
```

In case of a MQTT message with topic: "lights/Feath/toggle"
the only subsection contains, for example: 
```
  	[...]"toggle":{"v":1,"u":"i","mn":1,"mx":0}}, 
```
where "v":1 stands for Toggle leds ON.

In case of a MQTT message with topic: "lights/Feath/color_inc",
the only subsection contains, for example: 
```
  	[...]"colorInc":{"v":4,"u":"i","mn":0,"mx":9}}
```
where "v":4 stands for ColorIndex value 4 (minim 0 and maximum 9)

In case of a MQTT message with topic: "lights/Feath/color_dec",
the only subsection contains, for example:
```
  	[...]"colorDec":{"v":3,"u":"i","mn":0,"mx":9}}
```

Each sub-sub-section has the same definitions:
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

To build and upload the Arduino sketch for the MQTT Publisher device I used the Arduino IDE v2.3.5. In the Arduino sketch for the MQTT Publisher (Adafruit ESP32-S3 TFT board) I added functionality to set the display to "sleep" at a time defined in the file ```secrets.h```. In this moment 23h. And a "wakeup" time. In this moment 8h. See in the file secrets.h: 
```
#define SECRET_DISPLAY_SLEEPTIME "23"  // Feather display going to sleep (black) time
#define SECRET_DISPLAY_AWAKETIME "8"   // Feather display wakeup time
```
During the "sleep" hours, the MQTT Publisher device continues to send MQTT messages at the programmed interval time (in this moment once per minute). It also continues, at intervals of 15 minutes, to synchronize the via I2C connected external M5Stack Unit RTC from a NTP datetime stamp.

In case the Arduino sketch of the Publisher device encounters that it cannot read the values from the BME280 sensor, the sketch will issue a software reset by calling the function ```reset()``` which calls the function ```ESP.restart()```.

The source of the Arduino sketch for the MQTT Publisher device is [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/tree/main/src/Publisher)

# File secrets.h (for the MQTT Publisher device)

To have the Publisher device be able to connect to the internet, to get, at intervals, a Unixtime datetime stamp from an NTP server, you have to fill-in the WiFi SSID and PASSWORD. Further you can change the following settings in the file secrets.h:

```
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

# MQTT broker

If you, like me, also use a Raspberry Pi model to host a Mosquitto broker application, see the files in ```/etc```
- ```/etc/hosts.allow``` : insert in this file the ip-addres of your mosquitto broker. In my case: ```mosquitto: 127.0.0.1```
- ```/etc/mosquitto/mosquitto.conf```. See the contents of the mosquitto.conf file that I use in the folder: ```/src/Broker/etc/mosquitto```.

See also photos of sites where to download the mosquitto broker app for Raspberry Pi or for a MS Windows PC in the folder. ```/src/Broker```.

# MQTT Subscriber 
The Pimoroni Presto, in the role of MQTT Subscriber, runs on Micropython. The firmware is a special version of micropython. See the link above.


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
For an image of the I2C wiring see [here](https://github.com/PaulskPt/Presto_MQTT_multi_topic_subscriber/blob/main/images/20250720_202423_hardware.png)

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

