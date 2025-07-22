/*
  Sunday 2025-06-16 20h07 utc +1
  Adafruit Feather ESP32-S3 TFT MQTT test
  This sketch is a port from a sketch for an Adafruit Feather ESP32S3 TFT to send BME280 sensor data to a MQTT broker
  and to receive and display these MQTT messages onto the display of a Pimoroni Presto device.
  Update Saturday 2025-06-28 13h27 utc +1
  
  Notes about power consumption (2025-07-13):
  When connected to USB (long cable) of a MS Windows 11 desktop PC, the average voltage is 5,124 V.
  The current draw is average 0.069 A however with incidently increased draw up to 0,143 A.
  When connected to my multi-port 5Volt power supply, the voltage is: 5,058 V  (0,066 Volt less than the PC).
  I saw that when the Feather is connected to the multi-port 5Volt power supply, the sketch executes with failures,
  like wrong unixTime, consequently wrong derived hh which has strang effects to the checks for gotoSleep or awake of the display.
  When I connect a good Raspberry Pi 5V adapter to the Feather, the Feather works without problem. With a VOM I measured,
  between GND and VBUS pins of the Feather, 5,29 V (+ 0,232V more than on the multi-port 5Volt power supply).

  Note about connecting 3 devices to one I2C bus:
  Devices: 1) M5Stack M5Unit-RTC; 2) Pimoroni multi-sensor-stick; 3) Adafruit Gamepad QT.
  All three devices connected to the Stemma QT/Qwiic connector of the Adafruit Feather ESP32-S3 TFT board,
  via a M5Stack 3-port Grove Hub. 
  Initially I had the Adafruit Gamepad QT connected in series with the Pimoroni multi-sensor-stick,
  however this caused I2C bus problems. In fact the M5Unit-RTC was giving eratical datetime values after having been set with a correct NTP unixtime.
  After disconnecting the Gamepad QT from the multi-sensor-stick and then connecting the Gamepad QT to the 3-port Grove Hub, the I2C bus problems were history.
  From then the Arduino sketch running on the Adafruit Feather ESP32-S3 TFT received correct datetime data from the M5Unit-RTC.

  Update 2025-07-15: this is a first try to work with mqtt message with different topics.
  Update 2025-07-20: remotely commanding the seven ambient neopixels on the back of the Pimoroni Presto, through MQTT message sent by the Adafruit Feather work excellent:
  switching the leds on/off and changing color of these ambient neopixels is successful.

*/
#include <Arduino.h>
#include <Unit_RTC.h>
#include <ArduinoMqttClient.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <NTPClient.h>
#include <WiFiUdp.h>
#include <Adafruit_BME280.h>
//#include <Wire.h>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <string>
#include <ctime>
#include <cstdio>  // for snprintf
#include <type_traits>  // Needed for underlying type conversion
#include <time.h>
#include <stdlib.h>  // for setenv
#include "secrets.h"
#include "Adafruit_MAX1704X.h"
#include "Adafruit_LC709203F.h"
#include <Adafruit_NeoPixel.h>
#include "Adafruit_TestBed.h"
#include <Adafruit_BME280.h>
#include <Adafruit_ST7789.h> 
#include <Adafruit_seesaw.h>
//#include <Fonts/FreeSans12pt7b.h>
#include <Fonts/FreeMono12pt7b.h>

// #define IRQ_PIN   5

#ifdef MY_DEBUG
#undef MY_DEBUG
#endif

Adafruit_LC709203F lc_bat;
Adafruit_MAX17048 max_bat;
extern Adafruit_TestBed TB;

#define DEFAULT_I2C_PORT &Wire

// Some boards have TWO I2C ports, how nifty. We should scan both
#if defined(ARDUINO_ARCH_RP2040) \
    || defined(ARDUINO_ADAFRUIT_QTPY_ESP32S2) \
    || defined(ARDUINO_ADAFRUIT_QTPY_ESP32S3_NOPSRAM) \
    || defined(ARDUINO_ADAFRUIT_QTPY_ESP32S3_N4R2) \
    || defined(ARDUINO_ADAFRUIT_QTPY_ESP32_PICO) \
    || defined(ARDUINO_SAM_DUE) \
    || defined(ARDUINO_ARCH_RENESAS_UNO)
  #define SECONDARY_I2C_PORT &Wire1
#endif

enum mqtt_msg_type {
  tpah_sensor = 0,
  lights_toggle = 1,
  lights_color_increase = 2,
  lights_color_decrease = 3,
  msg_todo = 4
};

mqtt_msg_type myMsgType = tpah_sensor;// create an enum class variable and assign default message type value
char msg_topic[36];  // was 23

// Function declaration so that it will be found by other functions
void disp_msg(const char* arr[], size_t size, bool disp_on_serial);

static constexpr const char *weekdays[] PROGMEM = {"Sun", "Mon", "Tues", "Wednes", "Thurs", "Fri", "Satur" };

//                  Btn    A          B                X                   Y
const char *msgTypes[] = {"sensors", "lights_toggle", "lights_color_inc", "lights_color_dec", "todo"};
int colorIndex = 0;
int colorIndexMin = 0;
int colorIndexMax = 10;

int select_btn_idx = 0;
int select_btn_max = 1;

#ifndef LED_BUILTIN
#define LED_BUILTIN 13
#endif

#ifndef NEOPIXEL_POWER
#define NEOPIXEL_POWER 34
#endif
// NEOPIXEL_POWER_ON

// Which pin on the Arduino is connected to the NeoPixels?
#ifndef PIN_NEOPIXEL
#define PIN_NEOPIXEL   33 // On Trinket or Gemma, suggest changing this to 1
#endif

#ifndef NUMPIXELS
#define NUMPIXELS         1     // Only one onboard NeoPixel
#endif

#define BLACK (0, 0, 0)  // Not defined for the Neopixel in Adafruit_testbed.h

Adafruit_NeoPixel pixel(NUMPIXELS, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);

Adafruit_ST7789 display = Adafruit_ST7789(TFT_CS, TFT_DC, TFT_RST);

GFXcanvas16 canvas(240, 135);

int canvas_width = canvas.width();
int canvas_height = canvas.height();

Adafruit_seesaw ss;

// See: https://learn.adafruit.com/gamepad-qt/arduino
#define BUTTON_NONE      -1
#define BUTTON_X         6
#define BUTTON_Y         2
#define BUTTON_A         5
#define BUTTON_B         1
#define BUTTON_SELECT    0
#define BUTTON_START    16
uint32_t button_mask = (1UL << BUTTON_X) | (1UL << BUTTON_Y) | (1UL << BUTTON_START) |
                       (1UL << BUTTON_A) | (1UL << BUTTON_B) | (1UL << BUTTON_SELECT);

const int NUM_BUTTONS = 6;
enum Button { BTN_A, BTN_B, BTN_X, BTN_Y, BTN_SELECT, BTN_START, BTN_NONE };
const char *ButtonNames[] = { "A", "B", "X", "Y", "Select", "Start", "None" };
bool buttonPressed[NUM_BUTTONS] = {false};
bool a_button_has_been_pressed = false;

// Store previous and current states for debouncing
bool lastButtonState[NUM_BUTTONS] = {false};
bool currentButtonState[NUM_BUTTONS] = {false};

 // Timing variables
unsigned long lastDebounceTime[NUM_BUTTONS] = {0};
const unsigned long debounceDelay = 500; // ms

bool use_gamepad_qt    = false;

// X and Y positions of the Gamepad_QT
int last_x = 0, last_y = 0;

bool maxfound = false;
bool lcfound = false;
bool squixl_mode = true; // compose mqtt messages conform the SQUiXL system (send 4 messages, each for: temp, pres, alti and humi)

// bool my_debug = false;
bool timeSynced = false;
bool do_test_reset = false;
bool isItBedtime = false;
bool display_can_be_used = true; // true if the current hour is between sleepTime and awakeTime

unsigned long msgGrpID = 0L;
unsigned long msgGrpID_old = 0L;
unsigned long msgGrpID_max = 999L;
unsigned long lastUxTime = 0L; // last unix time received from the RTC
unsigned long unixUTC = 0L; // = unixtime UTC
unsigned long unixLOC = 0L; // = unixtime Local (including (+-) tz_offset in seconds)
unsigned long mqttMsgID = 0L;
time_t utcEpoch; // epoch time in seconds
uint16_t EpochErrorCnt = 0;
uint16_t EpochErrorCntMax = 10;

///////please enter your sensitive data in the Secret tab/arduino_secrets.h
char ssid[] = SECRET_SSID;    // your network SSID (name)
char pass[] = SECRET_PASS;    // your network password (use for WPA, or use as key for WEP)

// unsigned int localPort = 2390;  // local port to listen for UDP packets

WiFiClient wifiClient;
MqttClient mqttClient(wifiClient);

// this IP did not work: "85.119.83.194" // for test.mosquitto.org
// 5.196.0.0 - 5.196.255.255 = FR-OVH-20120823, Country code: FR (info from https://lookup.icann.org/en/lookup)

bool use_broker_local; 
const char* broker;  // will be set in setup()

int        port = atoi(SECRET_MQTT_PORT);                                                            // 1883;
const char TOPIC_PREFIX_SENSORS[]                = SECRET_MQTT_TOPIC_PREFIX_SENSORS;                 // "sensors"
const char TOPIC_PREFIX_LIGHTS[]                 = SECRET_MQTT_TOPIC_PREFIX_LIGHTS;                  // "lights"
const char TOPIC_PREFIX_TODO[]                   = SECRET_MQTT_TOPIC_PREFIX_TODO;                    // "todo"

const char TOPIC_PUBLISHER[]                     = SECRET_MQTT_PUBLISHER;                            // "Feath"

const char TOPIC_SUFFIX_SENSORS[]                = SECRET_MQTT_TOPIC_SUFFIX_SENSORS;                 // "ambient"
const char TOPIC_SUFFIX_LIGHTS_TOGGLE[]          = SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_TOGGLE;           // "toggle"
const char TOPIC_SUFFIX_LIGHTS_COLOR_DECREASE[]  = SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_COLOR_DECREASE;   // "color_dec"
const char TOPIC_SUFFIX_LIGHTS_COLOR_INCREASE[]  = SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_COLOR_INCREASE;   // "color_inc"
const char TOPIC_SUFFIX_TODO[]                   = SECRET_MQTT_TOPIC_SUFFIX_TODO;                    // "todo"

WiFiUDP ntpUDP; // A UDP instance to let us send and receive packets over UDP
int tzOffset = atoi(SECRET_TIMEZONE_OFFSET); // can be negative or positive (hours)
signed long utc_offset = tzOffset * 3600;    // utc_offset in seconds. Attention: signed long! Can be negative or positive
unsigned long uxTimeUTC = 0L;
unsigned long uxTimeLocal = 0L;
uint8_t HoursLocal = 255;  // Initialized to an invalid value
uint8_t HoursLocal_old = 255; // Initialized to an invalid value
unsigned long ntp_interval_t = (15 * 60 * 1000L) - 5; // 15 minutes - 5 secs
//NTPClient timeClient(ntpUDP, SECRET_NTP_SERVER1, utc_offset, ntp_interval_t);
NTPClient timeClient(ntpUDP, SECRET_NTP_SERVER1, 0, ntp_interval_t); // no utc_offset
bool lStart = true; // startup flag
bool rtc_is_synced = false;
char isoBufferUTC[26];  // 19 characters + null terminator representing UTC time
char isoBufferLocal[26];  // same, representing Local time
char timestamp[24] = "not_synced";  // e.g., "2025-07-02T13:32:02"
std::string dispTimeStr; // the local time to be shown on the TFT display see func getUnixTimeFromRTC()
float temperature, humidity, pressure, altitude;
const size_t CAPACITY = 1024;

Unit_RTC RTC;

//                        from Unit_RTC.h    uint8_t buf[3] = {0};
rtc_time_type RTCtime; // uint8_t buf[0] Seconds, uint8_t buf[1] Minutes, buf[2] uint8_t Hours
//                        from Unit_RTC.h    uint8_t buf[4] = {0};
// Note RTC_DateStruct->Month MSB (0x80) if "1" then Year = 1900 + buf[3]. If "0" then Year = 2000 + buf[3]
rtc_date_type RTCdate; // uint_t buf[0] date = 0, uint8_t buf[1] weekDay = 0, uint8_t buf[2] month = 0, uint16_t buf[3] year = +1900 or +2000, 
// uint8_t DateString[9]; // from Unit_RTC.h
// uint8_t TimeString[9]; // also

uint8_t displaySleepTime;
uint8_t displayAwakeTime;

char str_buffer[64];

int led =  LED_BUILTIN;

bool led_is_on = false;
bool remote_led_is_on = false;

#define led_sw_cnt 20  // Defines limit of time count led stays on

int status = WL_IDLE_STATUS;

int count = 0;

#define SEALEVELPRESSURE_HPA (1013.25)

Adafruit_BME280 bme; // I2C
bool bmefound = false;
uint8_t bme_bad_read_cnt = 0;
uint8_t bme_bad_read_cnt_max = 3;

unsigned long delayTime;

// Function to compose the MQTT message topic based on the message type
// msg_topic is a global variable
void composeMsgTopic(enum mqtt_msg_type msgType = tpah_sensor) {  // default message type is tpah_sensor
  // Compose the message type string based on the enum value
  //char msgTopicStr[] = {};
  msg_topic[0] = '\0'; // Initialize the msg_topic string to an empty string
  switch (msgType) {  
    case tpah_sensor:
    {
      //msg_topic = msgTypes[tpah_sensor]; //"sensors";
      strcat(msg_topic, TOPIC_PREFIX_SENSORS);
      strcat(msg_topic, "/");
      strcat(msg_topic, TOPIC_PUBLISHER);
      strcat(msg_topic, "/");
      strcat(msg_topic, TOPIC_SUFFIX_SENSORS);
      break;
    }
    case lights_toggle:
    {
      //msg_topic = msgTypes[lights_toggle]; // "lights_toggle";
      strcat(msg_topic, TOPIC_PREFIX_LIGHTS);
      strcat(msg_topic, "/");
      strcat(msg_topic, TOPIC_PUBLISHER);
      strcat(msg_topic, "/");
      strcat(msg_topic, TOPIC_SUFFIX_LIGHTS_TOGGLE);
      break;
    }
    case lights_color_increase:
    case lights_color_decrease:
    {
      //msg_topic = (msgType == lights_color_decrease) ? msgTypes[lights_color_decrease] : msgTypes[lights_color_increase]);
      strcat(msg_topic, TOPIC_PREFIX_LIGHTS);
      strcat(msg_topic, "/");
      strcat(msg_topic, TOPIC_PUBLISHER);
      strcat(msg_topic, "/");
      if (msgType == lights_color_increase)
        strcat(msg_topic, TOPIC_SUFFIX_LIGHTS_COLOR_INCREASE);
      else if (msgType == lights_color_decrease)
        strcat(msg_topic, TOPIC_SUFFIX_LIGHTS_COLOR_DECREASE);
      else
        strcat(msg_topic, "unknown");
      break;
    }
    default:
    {
      //msg_topic = msgTypes[msg_todo];
      strcat(msg_topic, TOPIC_PREFIX_TODO);
      strcat(msg_topic, "/");
      strcat(msg_topic, TOPIC_PUBLISHER);
      strcat(msg_topic, "/");
      strcat(msg_topic, TOPIC_SUFFIX_TODO);
      break;
    }
  }
  //return msg_topic;
}

void setupDisplayTimes() {
  // displaySleepTime and displayAwakeTime are global variables
  displaySleepTime = static_cast<uint8_t>(atoi(SECRET_DISPLAY_SLEEPTIME)); // in hours
  displayAwakeTime = static_cast<uint8_t>(atoi(SECRET_DISPLAY_AWAKETIME)); // in hours

  if (displaySleepTime > 23)
      displaySleepTime = 23;

  if (displayAwakeTime > 23)
      displayAwakeTime = 8;
#ifdef MY_DEBUG
  Serial.print(F("displaySleepTime = "));
  Serial.println(displaySleepTime);
  Serial.print(F("displayAwakeTime = "));
  Serial.println(displayAwakeTime);
#endif
}

bool isItDisplayBedtime() {
  // HoursLocal, displaySleepTime and displayAwakeTime are global variables
  // Check if the current hour is between displaySleepTime and displayAwakeTime

  // update the global variable HoursLocal
  // getUnixTimeFromRTC();  // This function is called in setup() and next called every minutes.
  
  bool is_it_disp_bedtime = true;
  if (HoursLocal >= displayAwakeTime && HoursLocal < displaySleepTime) {
    is_it_disp_bedtime = false;
  }
#ifdef MY_DEBUG
  Serial.print(F("isItDisplayBedtime(): HoursLocal = "));
  Serial.println(HoursLocal);
  Serial.print(F("is_it_disp_bedtime = ")); 
  Serial.println(is_it_disp_bedtime ? "true" : "false");
#endif
  return is_it_disp_bedtime;
}

// Function to turn the built-in LED on
void led_on() {
  //blinks the built-in LED every second
  digitalWrite(led, HIGH);
  led_is_on = true;
  //delay(1000);
}

// Function to turn the built-in LED off
void led_off()
{
  digitalWrite(led, LOW);
  led_is_on = false;
  //delay(1000);
}

void neopixel_on()
{
  led_is_on = true;
  digitalWrite(NEOPIXEL_POWER, HIGH); // Switch on the Neopixel LED
  //Serial.println("Color GREEN");
  pixel.setPixelColor(0, pixel.Color(0, 150, 0)); // Green color
  pixel.show();

}

void neopixel_off()
{
  led_is_on = false;
  //Serial.println("Color BLACK (Off)");
  pixel.setPixelColor(0, pixel.Color(0, 0, 0)); // color black (Turn off)
  pixel.show();
  digitalWrite(NEOPIXEL_POWER, LOW); // Switch off the Neopixel LED
}

void neopixel_test()
{
  Serial.println("neopixel test");
  for (int j = 0; j < 4; j++)
  {
    if (j == 0)
    {
      //Serial.println("Color RED");
      pixel.setPixelColor(0, pixel.Color(255, 0, 0));
    }
    else if (j == 1)
    {
      //Serial.println("Color GREEN");
      pixel.setPixelColor(0, pixel.Color(0, 255, 0));
    }
    else if (j == 2)
    {
      //Serial.println("Color BLUE");
      pixel.setPixelColor(0, pixel.Color(0, 0, 255));
    }
    else if (j == 3)
    {
      //Serial.println("Color BLACK (Off)");
      pixel.setPixelColor(0, pixel.Color(0, 0, 0));
    }
    pixel.show();  // Send the updated pixel colors to the hardware.
    delay(500);
  }
}

void disp_reset_msg(bool disp_on_serial = false) {
  const char *msg[] = {"Going to do a",
                       "software reset",
                       "in 5 seconds"};

  disp_msg(msg, sizeof(msg) / sizeof(msg[0]), disp_on_serial);
}

/*
// Alternative check if the Gamepad QT is connected or not
bool isGamepadConnected() {
    Wire.beginTransmission(GAMEPAD_I2C_ADDRESS);
    return Wire.endTransmission() == 0;
}
*/

bool seesawConnectMsgShown = false;

bool seesawIsConnected() {
  byte addr = 0x50;

  if (TB.scanI2CBus(addr)) {  // For the Pimoroni multi-sensor-stick
    Serial.print(F("✅ gamepad QT address: 0x"));
    Serial.println(addr, HEX);
    use_gamepad_qt = true;
  }
  else
  {
    if (!seesawConnectMsgShown) {
      seesawConnectMsgShown = true;
      Serial.print(F("❌ gamepad QT not found at address: 0x"));
      Serial.println(addr, HEX);
    }
    use_gamepad_qt = false;
  }
  return use_gamepad_qt;
}

bool seesaw_connect() {
  byte addr = 0x50;
  uint8_t nr_of_tries = 0;
  uint8_t nr_of_tries_max = 10;
  seesawConnectMsgShown = false; // reset flag
  if (!seesawIsConnected())
    return use_gamepad_qt;

  use_gamepad_qt = ss.begin(addr);
  while(!use_gamepad_qt) { // try to reset the gamepad QT
    use_gamepad_qt = ss.begin(addr);
    if (!use_gamepad_qt) {
      nr_of_tries++;
      if (nr_of_tries >nr_of_tries_max) {
        Serial.println(F("❌ ERROR! seesaw not found, Trying again later."));
        break;
      }
    }
    delay(100);
  }
  if (!use_gamepad_qt) {
    return use_gamepad_qt;
  }
  else {
    Serial.println(F("✅ seesaw started"));
    uint32_t version = ((ss.getVersion() >> 16) & 0xFFFF);
    if (version != 5743) {
      Serial.print(F("❌ Wrong firmware loaded? "));
      use_gamepad_qt = false;
      Serial.println(version);
      delay(10);
    }
    else {
      Serial.println(F("✅ Found Product 5743"));
      use_gamepad_qt = true;
    }
  }
  
  if (use_gamepad_qt) {
    ss.pinModeBulk(button_mask, INPUT_PULLUP);
    ss.setGPIOInterrupts(button_mask, 1);
  }

#if defined(IRQ_PIN)
    pinMode(IRQ_PIN, INPUT);
#endif

  return use_gamepad_qt;

}

/* Function to perform a software reset on an Arduino board,
   specifically using the ArduinoCore-renesas.
   Arduino has a built-in function named as resetFunc()
   which we need to declare at address 0 and when we 
   execute this function Arduino gets reset automatically.
   Using this function resulted in a "Fault on interrupt 
   or bare metal (no OS) environment crash!
*/
void do_reset() {
  disp_reset_msg(true);
  delay(5000);
  ESP.restart();
}

// Default version for most use cases (160-byte buffer)
void serialPrintf(const char* format, ...) {
  char buffer[160];
  va_list args;
  va_start(args, format);
  vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);
  Serial.print(buffer);
}

// Extended version where you can specify buffer size
// (= Function Overloading!)
void serialPrintf(size_t bufferLen, const char* format, ...) {
  char buffer[bufferLen];
  va_list args;
  va_start(args, format);
  vsnprintf(buffer, bufferLen, format, args);
  va_end(args);
  Serial.print(buffer);
}

void printWifiStatus() {
  // print the SSID of the network you're attached to:
  serialPrintf(PSTR("SSID: %s\n"), WiFi.SSID().c_str());

  // print your board's IP address:
  IPAddress ip = WiFi.localIP();
  serialPrintf(PSTR("IP Address: %s\n"), ip.toString().c_str());

/*
  // print the received signal strength:
  long rssi = WiFi.RSSI();
  serialPrintf(PSTR("signal strength (RSSI): %ld dBm\n"), rssi);
*/
}
bool ConnectToWiFi()
{
  bool ret = false;
  int connect_tries = 0;
  // attempt to connect to WiFi network:


  while (WiFi.status() != WL_CONNECTED) 
  {
    //serialPrintf(PSTR("Attempting to connect to SSID: %s\n"), ssid);
    // Connect to WPA/WPA2 network. Change this line if using open or WEP network:
    WiFi.begin(ssid, pass);
    //serialPrintf(PSTR("WiFi connection tries: %d.\n"), connect_tries);
    connect_tries++;
    if (connect_tries >= 5)
    {
      serialPrintf(PSTR("❌ WiFi connection failed %d times.\n"), connect_tries);
      break;
    }

    // wait 10 seconds for connection:
    delay(10000);
  }

  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.print(F("✅ Connected to "));
    printWifiStatus();
    ret = true;
  }
  return ret;
}

void do_line(uint8_t le = 4)
{
  // Default
  if (le == 4)
  {
    for (uint8_t i= 0; i < le; i++)
    {
      Serial.print(F("----------")); // length 10
    }
  }
  // Variable
  else
  {
    for (uint8_t i= 0; i < le; i++)
    {
      Serial.print('-'); // length 1
    }
  }
  Serial.println();
}

void disp_msg(const char* arr[], size_t size, bool disp_on_serial = false) {
  uint8_t hPos = 0;
  uint8_t vPos = 25;

  if (size == 0)
    return;

  canvas.fillScreen(ST77XX_BLACK);

  for (uint8_t i = 0; i < size; i++) {
    switch (i) {
      case 0: canvas.setTextColor(ST77XX_GREEN);   vPos = 25;  break;
      case 1: canvas.setTextColor(ST77XX_YELLOW);  vPos = 50;  break;
      case 2: canvas.setTextColor(ST77XX_CYAN);    vPos = 75;  break;
      case 3: canvas.setTextColor(ST77XX_MAGENTA); vPos = 100; break;
      case 4: canvas.setTextColor(ST77XX_BLUE);    vPos = 125; break;
      default: break;
    }

    canvas.setCursor(hPos, vPos);
    canvas.println(arr[i]);

    if (disp_on_serial) {
      if (i == 0)
        Serial.println(); // Print a new line before the first message
      Serial.println(arr[i]);
    }
  }

  display.drawRGBBitmap(0, 0, canvas.getBuffer(), canvas_width, canvas_height);
}

void disp_intro(bool disp_on_serial = false) {
  const char *msg[] = {"Adafruit Feather",
                       "ESP32-S3 TFT as",
                       "MQTT publisher",
                      "device"};

  disp_msg(msg, sizeof(msg) / sizeof(msg[0]), disp_on_serial);
}

void disp_btn_info() {
  const char *msg[] = {"Gamepad Btns:",
                       "A/B +/- topic",
                       "X/Y +/- color",
                       "Sel > show this",
                       "Sta > reset board"};
  
  disp_msg(msg, sizeof(msg) / sizeof(msg[0]), true);
}

void disp_topic_types() {
  // Display the message types on the TFT display
  const char *msg[] = {"Topic types:",
                       "X: Sensor data",
                       "Y: Lights toggle",
                       "A: Color increase",
                       "B: Color decrease"};
  
  disp_msg(msg, sizeof(msg) / sizeof(msg[0]), true);
}

// msgGrpID, mqttMsgID and dispTimeStr are global variables
void disp_msg_info(bool disp_on_serial = false) {
  std::string msgGrpIDstr1 = "MQTT msg group";
  std::string msgGrpIDstr2 = std::to_string(msgGrpID) + " sent";
  std::string dispMsgID = "msgID: " + std::to_string(mqttMsgID);
  const char *msg[] = {dispTimeStr.c_str(), msgGrpIDstr1.c_str(), msgGrpIDstr2.c_str(), dispMsgID.c_str()};
  disp_msg(msg, sizeof(msg) / sizeof(msg[0]), disp_on_serial);
}

void disp_msgType_chg() {
  // Display the current message type on the TFT display
  std::string tempStr = "New Msg type:\n" + std::string(msgTypes[static_cast<int>(myMsgType)]);
  // Convert to const char* for display
  const char *msg[] = {tempStr.c_str()};
  disp_msg(msg, sizeof(msg) / sizeof(msg[0]), true);
  Serial.println();
}

void disp_sensor_data(bool disp_on_serial = false) {
  static std::string tempStr, presStr, altitr, humiStr;

  std::ostringstream tempSS, presSS, altiSS, humiSS;
  canvas.print((char)0xF8); // ISO-8859-1 code for °
  tempSS << "Temp: " << std::right << std::setw(6) << std::fixed << std::setprecision(1) << temperature << " ºC";
  presSS << "Pres: " << std::right << std::setw(6) << std::fixed << std::setprecision(1) << pressure    << " hPa";
  altiSS << "Alt:  " << std::right << std::setw(6) << std::fixed << std::setprecision(1) << altitude    << " m";
  humiSS << "Humi: " << std::right << std::setw(6) << std::fixed << std::setprecision(1) << humidity    << " %";

  tempStr = tempSS.str();
  presStr = presSS.str();
  altitr  = altiSS.str();
  humiStr = humiSS.str();

  const char* msg[] = {tempStr.c_str(), presStr.c_str(), altitr.c_str(), humiStr.c_str()};
  disp_msg(msg, sizeof(msg) / sizeof(msg[0]), disp_on_serial);
}

void disp_goodnight() {
  const char *msg[] = {"Good night! 🌙", "Display go off", "Send msg", "continues!", "See you tomorrow!"};
  disp_msg(msg, sizeof(msg) / sizeof(msg[0]), true);
  delay(5000); // Show the text for 5 seconds
  canvas.fillScreen(ST77XX_BLACK);
}

void greeting_handler() {
  const char* txts[] PROGMEM = {
      "Good ", "morning ", "☀️",
      "afternoon ", "evening ",
      "display on", "Have a nice day!"
  };
  static char msg1[50], msg2[20], msg3[30]; // Buffers for full messages
  const char* msg_arr[3]; // Array to hold final strings
  msg1[0] = '\0'; // Initialize msg1 to an empty string
  msg2[0] = '\0'; // Initialize msg2 to an empty string
  msg3[0] = '\0'; // Initialize msg3 to an empty string
  msg_arr[0] = nullptr; // Initialize the array to avoid dangling pointers
  msg_arr[1] = nullptr; // Initialize the array to avoid dangling pointers
  msg_arr[2] = nullptr; // Initialize the array to avoid dangling pointers
  // Morning greeting example
  if (HoursLocal >= 0 && HoursLocal < 12) {
    strcpy(msg1, txts[0]);      // "Good "
    strcat(msg1, txts[1]);      // + "morning "
    strcat(msg1, txts[2]);      // + "☀️"
  }
  else if (HoursLocal >= 12 && HoursLocal < 18) {
    strcat(msg1, txts[0]);  // "Good "
    strcat(msg1, txts[3]);  // "afternoon"
  }
  else if (HoursLocal >= 18 && HoursLocal < 24) {
    strcat(msg1, txts[0]);  // "Good "
    strcat(msg1, txts[4]);  // "evening"
  }
  strcpy(msg2, txts[5]);      // "display on"
  strcpy(msg3, txts[6]);      // "Have a nice day!"

  msg_arr[0] = msg1;
  msg_arr[1] = msg2;
  msg_arr[2] = msg3;

  disp_msg(msg_arr, 3, true);
}

/*
  From Copilot:
  your custom portable_timegm() workaround safely converts a 
  UTC-based std::tm into a 
  time_t epoch 
  without relying on system-level timezone logic.
*/
time_t portable_timegm(std::tm* utc_tm) 
{
  char* old_tz = getenv("TZ");
  setenv("TZ", "", 1);  // Set to UTC
  tzset();

  time_t utc_epoch = std::mktime(utc_tm);

  // Restore previous timezone
  if (old_tz)
    setenv("TZ", old_tz, 1);
  else
    unsetenv("TZ");
  tzset();

  return utc_epoch;
}

// return an unsigned long unixUTC
/*
 Note:
 Epoch timestamp: 32503679999
 Timestamp in milliseconds: 32503679999
 Date and time (GMT): Tuesday, December 31, 2999 11:59:59 PM
 This function is also called when needed to update the global variable HoursLocal
 */
unsigned long getUnixTimeFromRTC() 
{
  static constexpr const char txt0[] PROGMEM = "getUnixTimeFromRTC(): ";
  //rtc_time_type RTCtime;  // is are global variable
  //rtc_date_type RTCdate;  // same
  bool updateFmNTP = false; // Flag to check if we need to update from NTP

  // RTCtime and RTCdate are global variables (of types: rtc_time_type and rtc_date_type)
  rtc_time_type RTCtime2;
  rtc_date_type RTCdate2;

  RTC.getTime(&RTCtime2);
  RTC.getDate(&RTCdate2);

  Serial.print(txt0);
  Serial.print(F("RTCdate and time: "));
  serialPrintf(PSTR("%sday, %4d-%02d-%02dT%02d:%02d:%02d UTC\n"),
                weekdays[RTCdate2.WeekDay],
                RTCdate2.Year, 
                RTCdate2.Month, 
                RTCdate2.Date, 
                RTCtime2.Hours, 
                RTCtime2.Minutes, 
                RTCtime2.Seconds);
 
  if (RTCdate2.Month < 1 || RTCdate2.Month > 12 || RTCdate2.Date > 31 || RTCdate2.WeekDay > 7 || RTCtime2.Hours > 23 || RTCtime2.Minutes > 59 || RTCtime2.Seconds > 59) 
  {
    Serial.println(F("❌ RTC datetime invalid!"));
    return 0;
  }

  // Copy the local date and time structs to the global ones, now the values are OK
  RTCdate = RTCdate2;
  RTCtime = RTCtime2;

  // Prepare a tm structure (interpreted as UTC time)
  std::tm timeinfoUTC{};

  timeinfoUTC.tm_year = RTCdate2.Year - 1900;  // tm_year is years since 1900
  timeinfoUTC.tm_mon  = RTCdate2.Month - 1;    // tm_mon is 0-based
  timeinfoUTC.tm_mday = RTCdate2.Date;
  timeinfoUTC.tm_hour = RTCtime2.Hours;
  timeinfoUTC.tm_min  = RTCtime2.Minutes;
  timeinfoUTC.tm_sec  = RTCtime2.Seconds;

#ifdef MY_DEBUG
  Serial.print(txt0);
  Serial.print(F("timeinfoUTC.tm_year etc..."));
  serialPrintf("%4d-%02d-%02dT%02d:%02d:%02d\n",
                timeinfoUTC.tm_year, 
                timeinfoUTC.tm_mon, 
                timeinfoUTC.tm_mday, 
                timeinfoUTC.tm_hour, 
                timeinfoUTC.tm_min, 
                timeinfoUTC.tm_sec);
#endif

  // convert to an ISO8601 string (utc time) in buffer: isoBufferUTC
  toIso8601String(timeinfoUTC, isoBufferUTC, sizeof(isoBufferUTC), 0);


  // utcEpoch is a global variable
  utcEpoch = portable_timegm(&timeinfoUTC);
  
  // Add 1 hour to get Local epoch (since RTC is in UTC)
  // Adjust to UTC using global utc_offset
  // Convert to time_t (local time)
  time_t localEpoch = utcEpoch + utc_offset;

  // Prepare a tm structure (interpreted as local time)
  std::tm timeinfoLocal{};

  // Convert time_t to tm struct for local time 
  //std::tm* tmp = localtime(&localEpoch);
  std::tm* tmp = std::gmtime(&localEpoch);

  // Convert time_t LocalEpoch to std::tm struct timeinfoLocal
  //std::tm* tmp = std::localtime(&localEpoch);isobufferLocal
  if (tmp != nullptr) 
  {
    timeinfoLocal = *tmp;
    // ------------------------------------------
    // Set the global variable to the hours value 
    // (needed for display sleep or not)
    HoursLocal = timeinfoLocal.tm_hour;  // update the global variable HoursLocal

    Serial.print(txt0);
    Serial.print(F("HoursLocal = "));
    Serial.print(HoursLocal);
    Serial.print(F(", HoursLocal_old = "));
    Serial.println(HoursLocal_old);

    if (lStart) { // At boot/reset both HoursLocal and HoursLocal_old are set to 255 
      lStart = false; // switch off the start flag
      HoursLocal_old = HoursLocal; // update the global variable HoursLocal_old
    }
    else if (HoursLocal != HoursLocal_old)
      HoursLocal_old = HoursLocal; // update the global variable HoursLocal_old
   
    //-------------------------------------------
  }
  else
  {
    Serial.print(txt0);
    Serial.println(F("❌ Failed to create timeinfoLocal"));
    HoursLocal = 255; // Set to an invalid value
  }
  // convert to an ISO8601 string (local time) in buffer: isoBufferLocal
  toIso8601String(timeinfoLocal, isoBufferLocal, sizeof(isoBufferLocal), utc_offset);

  char timeStr[9] = {};  // HH:MM:SS\0
  std::snprintf(timeStr, 9, "%02d:%02d:%02d",
                timeinfoLocal.tm_hour,
                timeinfoLocal.tm_min,
                timeinfoLocal.tm_sec);
  
  dispTimeStr.assign(timeStr, 9); // "hh:mm:ss" is 8 characters long
#ifdef MY_DEBUG
  Serial.print(txt0);
  serialPrintf(PSTR("hh:mm:ss = %s LOCAL\n"), dispTimeStr.c_str());
#endif

  unixUTC = static_cast<unsigned long>(utcEpoch);
  unixLOC = static_cast<unsigned long>(localEpoch);

#ifdef MY_DEBUG
  Serial.print(txt0);
  Serial.print(F("unixUTC = "));
  Serial.print(unixUTC);
  Serial.print(F(" = "));
  Serial.println(isoBufferUTC);

  Serial.print(txt0);
  Serial.print(F("unixLOC = "));
  Serial.print(unixLOC);
  Serial.print(F(" = "));
  Serial.println(isoBufferLocal);
#endif

  return unixLOC; // was: unixUTC
}

// Check if the time is valid based on the lastUxTime, utcEpoch, HoursLocal, and HoursLocal_old
// lastUxTime is a global variable
// utcEpoch is a global variable
// HoursLocal and HoursLocal_old are global variables
bool ck_timeIsValid() 
{
  bool isValid = false;
  if (EpochErrorCnt > EpochErrorCntMax)
    return isValid;

  static constexpr const char txt0[] PROGMEM = "ck_timeIsValid(): ";
  const char* txts[] PROGMEM = { "❌ ",            // 0
                        "Epoch time is ",  //  1
                        "too ",            //  2 
                        "small ",          //  3
                        "large ",          //  4
                        "more ",           //  5
                        "less ",           //  6
                        "than 24 hours ",  //  7
                        "ahead ",          //  8
                        "behind ",         //  9
                        "in the ",         // 10
                        "past ",           // 11
                        "future ",         // 12
                        "HoursLocal is ",  // 13
                        "than 10 hours "};  // 14

  uint8_t HoursLimit = 10; // Limit for hour difference check
  unsigned long epochLimit = 86400; // 24 hours in seconds
  //if (lastUxTime == 0L) {
  //  Serial.println(F("❌ lastUxTime is not set!"));
  //  return isValid; // Invalid time if lastUxTime is not set
  // }
  if (utcEpoch < 	946684800) // 946684800 is the epoch timestamp for 1 January 2000 at 00:00:00 UTC
  {
    Serial.print(txt0);
    Serial.print(txts[0]);   // "❌ "
    Serial.print(txts[1]);   // "Epoch time is "
    Serial.print(txts[2]);   // "too "
    Serial.print(txts[3]); // "small "
    Serial.print(F(" utcEpoch = "));
    Serial.println(utcEpoch);
    EpochErrorCnt++;
    return isValid;
  }
  if (utcEpoch >= 	3061065600) // 	3061065600 is the epoch timestamp for 1 January 2067 at 00:00:00 UTC
  {
    Serial.print(txt0);
    Serial.print(txts[0]);   // "❌ "
    Serial.print(txts[1]);   // "Epoch time is "
    Serial.print(txts[2]);   // "too "
    Serial.print(txts[4]); // "large "
    Serial.print(F(" utcEpoch = "));
    Serial.println(utcEpoch);
    EpochErrorCnt++;
    return isValid;
  }
  if (utcEpoch < lastUxTime)
  {
    if (utcEpoch - lastUxTime > epochLimit) // 86400 seconds = 24 hours
    {
      Serial.print(txt0);
      Serial.print(txts[0]);    // "❌ "
      Serial.print(txts[1]);    // "Epoch time is "
      Serial.print(txts[5]);    // "more "
      Serial.print(txts[7]);    // "than 24 hours "
      Serial.print(txts[10]);   // "in the "
      Serial.println(txts[11]); // "past "
      EpochErrorCnt++;
      return isValid;
    }
  }
  else if (lastUxTime >= utcEpoch) 
  {
    if (lastUxTime - utcEpoch > epochLimit) // 86400 seconds = 24 hours
    {
      Serial.print(txt0);
      Serial.print(txts[0]);    // "❌ "
      Serial.print(txts[1]);    // "Epoch time is "
      Serial.print(txts[6]);    // "less "
      Serial.print(txts[7]);    // "than 24 hours "
      Serial.print(txts[10]);   // "in the "
      Serial.println(txts[12]); // "future "
      EpochErrorCnt++;
      return isValid;
    }
  }
  if (HoursLocal > HoursLocal_old)
  {
    if (HoursLocal - HoursLocal_old > HoursLimit)
    {
      Serial.print(txt0);
      Serial.print(txts[0]);   // "❌ "
      Serial.print(txts[13]);  // "HoursLocal is "
      Serial.print(txts[5]);   // "more "
      Serial.print(txts[14]);  // "than 10 hours"
      Serial.println(txts[8]); // "ahead "
      return isValid; // Return false to indicate invalid time
    }
  }
  else if (HoursLocal_old >= HoursLocal) 
  {
    if (HoursLocal_old - HoursLocal > HoursLimit)
    {
      Serial.print(txt0);
      Serial.print(txts[0]);   // "❌ "
      Serial.print(txts[13]);  // "HoursLocal is "
      Serial.print(txts[5]);   // "more "
      Serial.print(txts[14]);  // "than 10 hours"
      Serial.println(txts[9]); // "behind "
      return isValid; // Return false to indicate invalid time
    }
  }
  return true; // Return true to indicate valid time
}

void printISO8601FromRTC() 
{
  static constexpr const char txt0[] PROGMEM = "printISO8601FromRTC(): ";
  if (!rtc_is_synced)
  {
    Serial.print(txt0);
    Serial.println(F("RTC has not been set. Exiting this function"));
    isoBufferUTC[0] = '\0'; // empty the isoBufferUTC
  }
  // rtc_time_type RTCtime; // is a global variable
  // rtc_date_type RTCdate; // same

  RTC.getTime(&RTCtime); // UTC
  RTC.getDate(&RTCdate);

  std::tm timeinfoUTC = {};
  timeinfoUTC.tm_year = RTCdate.Year - 1900;
  timeinfoUTC.tm_mon  = RTCdate.Month - 1;
  timeinfoUTC.tm_mday = RTCdate.Date;
  timeinfoUTC.tm_hour = RTCtime.Hours;
  timeinfoUTC.tm_min  = RTCtime.Minutes;
  timeinfoUTC.tm_sec  = RTCtime.Seconds;

  // Convert RTC UTC time to epoch
  //time_t utcEpoch = portable_timegm(&timeinfoUTC);  // instead of mktime()
  time_t utcEpoch = portable_timegm(&timeinfoUTC);
  time_t localEpoch = utcEpoch + utc_offset;

  // Prepare a tm structure (interpreted as UTC time)
  // Use gmtime to avoid double-applying system timezone
  std::tm utcTime{};
  std::tm* tmp = std::gmtime(&utcEpoch);
  if (tmp) 
  {
    utcTime = *tmp;
  }
  // Use localtime
  // Prepare a tm structure (interpreted as Local time)
  std::tm localTime{};
  tmp = std::gmtime(&localEpoch);
  if (tmp) 
  {
    localTime = *tmp;
  }

  // Call the helper for both buffers
  toIso8601String(utcTime, isoBufferUTC, sizeof(isoBufferUTC), 0);
  toIso8601String(localTime, isoBufferLocal, sizeof(isoBufferLocal), utc_offset);
#ifdef MY_DEBUG
  Serial.print(txt0);
  Serial.print(F("isoBufferUTC   = "));
  Serial.println(isoBufferUTC);
  Serial.print(txt0);
  Serial.print(F("isoBufferLocal = "));
  Serial.println(isoBufferLocal);
#endif
}

void toIso8601String(const std::tm& t, char* buffer, size_t bufferSize, int utc_offset_seconds) 
{
  char tz_suffix[7];  // Enough for "+HH:MM" or "-HH:MM" + null terminator

  int total_minutes = utc_offset_seconds / 60;
  int hours = total_minutes / 60;
  int minutes = (total_minutes >= 0) ? (total_minutes % 60) : -(total_minutes % 60);
  char sign = (utc_offset_seconds >= 0) ? '+' : '-';

  // Ensure hours is positive for formatting
  int abs_hours = (hours >= 0) ? hours : -hours;

  std::snprintf(tz_suffix, sizeof(tz_suffix), "%c%02d:%02d", sign, abs_hours, minutes);

  std::snprintf(buffer, bufferSize, "%04d-%02d-%02dT%02d:%02d:%02d%s",
                t.tm_year + 1900,
                t.tm_mon + 1,
                t.tm_mday,
                t.tm_hour,
                t.tm_min,
                t.tm_sec,
                tz_suffix);
}

void setRTCFromEpoch(unsigned long uxTime) {
  if (!RTC.setUnixTime(uxTime)) {
      Serial.println(F("❌ Failed to set RTC from Unix time."));
  } else {
      Serial.println(F("✅ RTC successfully set from Unix time."));
      rtc_is_synced = true;
  }
}


void rtc_sync() 
{
  unsigned long dummy;
  //do_line(49);
  Serial.print("🕒 ===>>> ");
  timeClient.update();  // This prints also the text "Update from NTP Server"
  // Get the current date and time from an NTP server and convert
  // it to UTC +1 by passing the time zone offset in hours.
  // You may change the time zone offset to your local one.

  //if (my_debug)
  //  serialPrintf(PSTR("RTC before set: %s\n"), String(currentTime).c_str());

  uxTimeUTC = timeClient.getEpochTime();  // timezone offset already given at init of timeClient;
  uxTimeLocal = uxTimeUTC + utc_offset;

  Serial.print(F("✅ NTP Unix time (UTC) = "));
  serialPrintf(PSTR("%lu\n"), uxTimeUTC);
  // Set RTC with received NTP datetime stamp
  setRTCFromEpoch(uxTimeUTC);

  delay(100); // leave the RTC time to be set by uxTimeUTC
  // Then check:
  dummy = getUnixTimeFromRTC(); // function sets utcEpoch (time_t)
  
  // Retrieve the date and time from the RTC and print them
  // RTCTime currentTime;
  //RTC.getTime(&RTCtime); 
  printISO8601FromRTC(); // this function writes result to global variable isoBufferUTC

#ifdef MY_DEBUG
  Serial.printf("RTC raw: %04d-%02d-%02d %02d:%02d:%02d\n",
    RTCdate.Year,  RTCdate.Month,   RTCdate.Date,
    RTCtime.Hours, RTCtime.Minutes, RTCtime.Seconds);

  Serial.print(F("RTC datetime = "));
  Serial.println(isoBufferUTC);
  //serialPrintf(PSTR("✅ RTC was set to: %s\n"), String(RTCtime).c_str());
#endif
  do_line(55);
  // mqttMsgID = getUnixTimeFromRTC();
  // Get a compilation timestamp of the format: Wed May 10 08:54:31 2023
  // __TIMESTAMP__ is a GNU C extension macro
  // We can't use the standard macros __DATE__ and __TIME__ because they don't provide the day of the week
  // String timeStamp = __TIMESTAMP__;
}


void clr_payloadBuffer(char* buffer, size_t size) {
    memset(buffer, 0, size); // Clear the buffer
}

char payloadBuffer[768]; // was: 512


int composePayload(char* outBuffer, size_t outSize,
                    float temperature, float pressure, float altitude, float humidity,
                    const char* timestamp) {

  bool stop = false;

  StaticJsonDocument<CAPACITY> doc;

  clr_payloadBuffer(payloadBuffer, sizeof(payloadBuffer)); // Clear the payload buffer
  if (!doc.isNull())
    doc.clear(); // Clear the JSON document
  
  mqttMsgID = getUnixTimeFromRTC(); // Important! Used in composePayload()
  //  170000000 (17 million) is the minimum value for a valid unix timestamp
  //  946684800 is the epoch timestamp for 1 Januari 2000 at 00:00:00 UTC
  // 3061065600 is the epoch timestamp for 1 January 2067 at 00:00:00 UTC 
  if (mqttMsgID < 946684800 || mqttMsgID >= 3061065600) 
  {
    Serial.print(F("❌ Invalid mqttMsgID ("));
    Serial.print(mqttMsgID);
    Serial.println(F("), exiting composePayload()"));
    return -1; // Invalid timestamp
  }

  // Root fields
  doc["ow"] = "Feath";    // owner
  doc["de"] = "PC-Lab";   // description (room, office, etc.)

  switch(myMsgType) 
  {
    case tpah_sensor:
    {
      doc["dc"] = "BME280";   // device_class
      doc["sc"] = "meas";     // state_class
      doc["vt"] = "f";        //  f = value type (for all values) float
      break;
    }
    case lights_toggle:
    {
      doc["dc"] = "home";     // device_class
      doc["sc"] = "ligh";     // state_class
      doc["vt"] = "i";        //  i = value type (for all values) integer (however, representing boolean: 1 = true, 0 = false)
      break;
    }
    case lights_color_increase:
    case lights_color_decrease:
    {
      doc["dc"] = "colr";  // device_class
      if (myMsgType == lights_color_increase)
        doc["sc"] = "inc";  // state_class
      else if (myMsgType == lights_color_decrease)
        doc["sc"] = "dec";
      doc["vt"] = "i";     //  i = value type
      break;
    }
    case msg_todo:
    {
      doc["dc"] = "todo";   // device_class
      doc["sc"] = "todo";   // state_class
      doc["vt"] = "s";      //  s = value type (for all values) string
      break;
    }
    default:
    {
      Serial.println(F("❌ Invalid myMsgType, exiting composePayload()"));
      stop = true; // Invalid message type
      break;
    }
  }
  if (stop)
    return -2; // Invalid message type

  doc["ts"] = mqttMsgID;  //  global var mqttMsgID is an unsigned long (takes 10 bytes while a human-readable full datetime = 19bytes)

  switch(myMsgType) 
  {
    case tpah_sensor:
    {
      // Readings
      JsonObject readings = doc.createNestedObject("reads");

      // Temperature
      JsonObject temp = readings.createNestedObject("t");
      temp["v"] = roundf(temperature * 10) / 10.0; // 1 decimal place  v = value
      temp["u"] = "C";  //  u = unit_of_measurement
      temp["mn"] = -10.0;  // mn = minimum_value
      temp["mx"] = 50.0;   // mx = maximum_value

      // Pressure
      JsonObject pres = readings.createNestedObject("p");
      pres["v"] = roundf(pressure * 10) / 10.0;
      pres["u"] = "mB";
      pres["mn"] = 800.0;
      pres["mx"] = 1200.0;

      // Altitude
      JsonObject alti = readings.createNestedObject("a");
      alti["v"] = roundf(altitude * 10) / 10.0;
      alti["u"] = "m";
      alti["mn"] = 0.0;
      alti["mx"] = 3000.0;

      // Humidity
      JsonObject humi = readings.createNestedObject("h");
      humi["v"] = roundf(humidity * 10) / 10.0;
      humi["u"] = "%";
      humi["mn"] = 0.0;
      humi["mx"] = 100.0;

      break;
    }
    case lights_toggle:
    {
      // Lights toggle
      JsonObject toggle = doc.createNestedObject("toggle");
      toggle["v"] = (remote_led_is_on) ? 1 : 0; // v = value, true if LED is on, false if off
      toggle["u"] = "i"; // unit of measurement, an integer representing true or false value
      toggle["mn"] = 0;  // minimum value
      toggle["mx"] = 1;   // maximum value
      break;
    }
    case lights_color_increase:
    case lights_color_decrease:
    {
      // JsonObject color_IncDec;
      // Lights color increase/decrease
      JsonObject color_IncDec = doc.createNestedObject((myMsgType == lights_color_increase) ? "colorInc" : "colorDec");
      color_IncDec["v"] = colorIndex; // is a global variable
      color_IncDec["u"] = "i";   // unit of measurement, here it is an integer
      color_IncDec["mn"] = 0;    // minimum value
      color_IncDec["mx"] = 9;   // maximum value
      break;
    }
    case msg_todo:
    {
      JsonObject todoObj = doc.createNestedObject("todo");
      todoObj["v"] = "todo";    // Placeholder for future use
      todoObj["u"] = "s";       // unit of measurement, here it is a string
      todoObj["mn"] = "none";   // minimum value
      todoObj["mx"] = "none";   // maximum value
      break;
    }
    default:
    {
      Serial.println(F("❌ Invalid myMsgType, exiting composePayload()"));
      stop = true;
      break;
    }
  }
 
  // Serialize JSON to the output buffer
  //doc["readings"]["temperature"]["value"] = serialized(String(temperature, 1));  // 1 decimal
  int written;

  if (stop)
    written =  -3; // Invalid message type
  else 
    written = serializeJson(doc, outBuffer, outSize);  // Return the int value written
  return written;
}

int ck_payloadBuffer(int wrt, bool pr_chrs = false)
{
  static constexpr const char txt0[] PROGMEM = "ck_payloadBuffer(): ";
  int ret = -1; // if >= 0, this search found a null-terminator inside the buffer up to the written value
#ifdef MY_DEBUG
  Serial.print(txt0);
  Serial.print(F("param wrt = "));
  Serial.println(wrt);
#endif
  if (wrt <= 0)
    return ret;

  for (int i = 0; i <= wrt; ++i) {
    char c = payloadBuffer[i];
    if (pr_chrs) {
      Serial.print(F(" Char["));
      Serial.print(i);
      Serial.print(F("]: '"));
    }
    // Print visible character or escape for control chars if param pr_chrs is true
    if (pr_chrs) {
      if (isprint(c)) {
          Serial.print(c);
      } else if (c == '\0') {
        Serial.print(F("\\0"));
        Serial.print((uint8_t)c, HEX);  // Print hex for non-printables
      } else {
        Serial.print(F("\\x"));
        Serial.print((uint8_t)c, HEX);  // Print hex for non-printables
      }
      Serial.print(F("' (0x"));
      Serial.print((uint8_t)c, HEX);    // Hex value of the character
      Serial.println(F(")"));
    }
    
    if (c == '\0' && ret == -1) {
      ret = i;
#ifdef MY_DEBUG
      Serial.print(txt0);
      Serial.print(F("found a null-terminator at pos: "));
      Serial.println(i);
#endif
    }
  }
  return ret;
}

// This function devides the mqtt_msg to be printed in half,
// then checks for the next comma character.
// If found a comma character, it inserts a new line print command
// This function is called from the function send_msg()
void prettyPrintPayload(const char* buffer, int length) {
    int halfway = length / 2;
    bool splitInserted = false;
    for (int i = 0; i < length && buffer[i] != '\0'; ++i) {
        Serial.print(buffer[i]);

        if (!splitInserted && i >= halfway && buffer[i] == ',') {
            Serial.println();      // Break line
            splitInserted = true; // Ensure only one line break
        }
    }
    Serial.println(); // Final newline
}


bool send_msg()
{
  static constexpr const char txt0[] PROGMEM = "send_msg(): ";

  bool ret = false;
  if (!isItBedtime)
      neopixel_on();

  if (myMsgType == tpah_sensor)
  {
    static constexpr const char txt0[] PROGMEM = "send_msg(): ";
    const char *txts[] PROGMEM = { "reading",       // 0
                                  "temperature",   // 1
                                  "pressure",      // 2
                                  "altitude",      // 3
                                  "humidity",      // 4
                                  "is extreme",    // 5
                                  "resetting" };   // 6
  
    bool do_reset2 = false;
  
    read_bme280_data(); // Read BME280 data and store in global variables
    
    do_test_reset = false;
    /*
    if (do_test_reset)
    {
      temperature = 0.0;
      pressure = 1010.0;
      Altitude = 0.0;
      Humidity = 100.0;
    }
    */

    if (do_test_reset)
      temperature = -20.0; // For testing purposes only

    if (temperature < -10.0 || temperature > 50.0)
    {
      // Temperature:
      serialPrintf(PSTR("%s%s %s %s\n"), txt0, txts[0], txts[1], txts[5]);
      temperature = 0.0;
      serialPrintf(PSTR("%s%s %s to %3.1f\n"), txt0, txts[6], txts[1], temperature);
    }

    if (do_test_reset)
      pressure = 1200.0;  // For test purposes only

    if (pressure < 800.0 || pressure > 1100.0)
    {
      // Pressure:
      serialPrintf(PSTR("%s%s %s %s: %7.2f\n"), txt0, txts[0], txts[2], txts[5], pressure);
      pressure = 1010.0;
      serialPrintf(PSTR("%s%s %s to %6.1f\n"), txt0, txts[6], txts[2], pressure);
      // return ret; // don't accept unrealistic extremes
    }

    if (do_test_reset)
      altitude = NAN;

    if (isnan(altitude)) {
      // Altitude:
      serialPrintf(PSTR("%s%s %s %s %F\n"), txt0, txts[0], txts[3], "resulted in", altitude);
      altitude = 0.0; // or some sentinel value
      serialPrintf(PSTR("%s%s %s to %3.1f\n"), txt0, txts[6], txts[3], altitude);
      // Log or handle safely  
    }

    if (do_test_reset)
      humidity = 200.0;

    if (humidity > 100.0)
    {
      // Humidity:
      serialPrintf(PSTR("%s%s %s %s\n"), txt0, txts[0], txts[4], txts[5]);
      humidity = 100.0;
      serialPrintf(PSTR("%s%s %s to %4.1f\n"), txt0, txts[6], txts[4], humidity);
    }
    
    if ( isnan(temperature) && isnan(pressure) && isnan(humidity) ) // do not check Altitude (Altitude) because it will be 0.00 m
      do_reset2 = true;
    else if (temperature == 0.0 && pressure == 1010.0 && altitude == 0.0 && humidity == 100.0)
      do_reset2 = true;

    if (do_reset2)
      bool dummy = handle_bme280();
  }
  else if (myMsgType == lights_toggle) {
    ; // Toggle the lights
  }
  else if (myMsgType == lights_color_decrease) {
    ; // Decrease the color value
  }
  else if (myMsgType == lights_color_increase) {
    ; // Increase the color value
  }

  msgGrpID++;
  if (msgGrpID > msgGrpID_max)
    msgGrpID = 1;

  int written = composePayload(payloadBuffer, sizeof(payloadBuffer), temperature, pressure, altitude, humidity, timestamp);
  if (written > 0)
  {
    serialPrintf(PSTR("Bytes written by composePayload(): %d\n"), written);
    //char msg_topic[36];  // was 23
    
    const char *txts[] PROGMEM = {"sensors", // 0
                                "Feath",     // 1
                                "ambient",   // 2
                                "lights",    // 3
                                "toggle",    // 4
                                "color",     // 5
                                "dec",       // 6
                                "inc",       // 7
                                "todo"};     // 8
#ifndef MY_DEBUG
    Serial.print(F("Topic: "));
    serialPrintf(PSTR("\"%s\"\n"), msg_topic);
#endif

#ifndef MY_DEBUG
    Serial.println(F("contents payloadBuffer: "));
    int null_found = ck_payloadBuffer(written, false); 
    if (null_found == written)  // a null-terminator has been found at the end of the payloadBuffer
    {
      // No null-terminator char found inside the written part of the payloadBuffer
      //Serial.println(payloadBuffer);
      // Try to split the (long) payloadBuffer text into two parts
      prettyPrintPayload(payloadBuffer, written); // function print-split nicely the payloadBuffer

    } else if (null_found < written) {
      // A null-terminator char found inside the written part of the payloadBuffer
      // so, don't split print the payloadBuffer!
      Serial.println(payloadBuffer);
    }
#endif
    size_t topicLength = strlen(msg_topic);
    Serial.print(F("Topic length: "));
    Serial.println(topicLength);
    size_t payloadLength = strlen(payloadBuffer);
    Serial.print(F("Payload length: "));
    Serial.println(payloadLength);
    Serial.print(F("MQTT message ID: "));
    Serial.print(mqttMsgID);
    Serial.print(F(" = "));
    Serial.println(isoBufferLocal);
    
    mqttClient.beginMessage(msg_topic);
    mqttClient.print(payloadBuffer);
    mqttClient.endMessage();
    // delay(1000);  // spread the four messages 1 second
    Serial.print(F("MQTT message group: "));
    serialPrintf(PSTR("%3d sent\n"), msgGrpID);
    ret = true;

  } else {
    Serial.println("⚠️ Failed to compose JSON payload");
  }
  
  // Prepare and show text on the TFT display
  // disp_msg_info();
  if (!isItBedtime)
    neopixel_off();

  do_line(55);
  return ret;
}

bool handle_bme280()
{
  bool ret = false;
  // default settings
   
  // You can also pass in a Wire library object like &Wire2
  // status = bme.begin(0x76, &Wire2)
  /*
      Extract from the Bosch BME280 datasheet

      5.4.2 Register 0xE0 "reset"
      The "reset" register contains the soft reset word reset(7:0). 
      If the value 0xB6 is written to the register,
      the device is reset using the complete power-on-reset procedure.
      Writing other values than 0xB6 has no effect.
      The readout value is always 0x00.

      Calling the self-test procedure starts with a soft reset of the sensor
      
  */
  uint8_t bme_check_cnt = 0;
  uint8_t bme_check_cnt_max = 3;
  byte addr = 0x76;
  if (TB.scanI2CBus(addr)) {  // For the Pimoroni multi-sensor-stick
    Serial.print("✅ BME280 address: 0x");
    Serial.println(addr, HEX);
  }
  else
  {
    Serial.print("❌ BME280 not found at address: ");
    Serial.println(addr, HEX);
  }
  status = bme.begin(addr, TB.theWire); 
  if (status)
    ret = true;
  else
  {
    while (!status)
    {
      Serial.println(F("❌ Could not find a valid BME280 sensor, check wiring, address, sensor ID!"));
      Serial.print(F("SensorID was: 0x")); 
      Serial.println(bme.sensorID(),16);
      Serial.print(F("        ID of 0xFF probably means a bad address, a BMP 180 or BMP 085\n"));
      Serial.print(F("   ID of 0x56-0x58 represents a BMP 280,\n"));
      Serial.print(F("        ID of 0x60 represents a BME 280.\n"));
      Serial.print(F("        ID of 0x61 represents a BME 680.\n"));
    
      status = bme.begin(0x76, &Wire1); 
      delay(100);
      if (status)
      {
        ret = true;
        break;
      }
      bme_check_cnt++;
      if (bme_check_cnt >= bme_check_cnt_max)
      {
        do_reset();
        //break;
      }
    }
  }
  if (ret)
    Serial.println(F("✅ BME280 successfully (re-)initiated."));
  return ret;
}

void read_bme280_data()
{
  static constexpr const char txt0[] PROGMEM = "read_bme280_data(): ";
  // Read temperature, pressure, altitude and humidity
  temperature = bme.readTemperature();
  pressure = bme.readPressure() / 100.0F; // Convert Pa to mBar
  altitude = bme.readAltitude(SEALEVELPRESSURE_HPA); // Altitude in meters
  humidity = bme.readHumidity();

#ifdef MY_DEBUG
  Serial.print(txt0);
  Serial.print(F("Temp: "));
  Serial.print(temperature);
  Serial.print(F(" °C, Pressure: "));
  Serial.print(pressure);
  Serial.print(F(" mBar, Altitude: "));
  Serial.print(altitude);
  Serial.print(F(" m, Humidity: "));
  Serial.print(humidity);
  Serial.println(F(" %"));
#endif
}

void handleButtonPress(enum Button i)  //static_cast<Button>(i)) {
{
  static constexpr const char txt0[] PROGMEM = "handle_btn_press(): ";
  const char* txts[] = {"Button", "pressed"};
  if (!seesawIsConnected())
    return;
  
  switch (i) {
    case BTN_A:
    {
      //Serial.println(F("Button A pressed"));
      serialPrintf(PSTR("\n%s A %s\n"), txts[0], txts[1]);
      myMsgType = tpah_sensor;
      Serial.println(F("changing to temperature, pressure, humidity sensor mode"));
      break;
    }
    case BTN_B:
    {
      //Serial.println(F("Button B pressed"));
      serialPrintf(PSTR("\n%s B %s\n"), txts[0], txts[1]);
      myMsgType = lights_toggle;
      remote_led_is_on = !remote_led_is_on; // toggle the value
      Serial.print(F("remote light changed. Light = "));
      Serial.println((remote_led_is_on) ? "On" : "Off");
      break;
    }
    case BTN_X:
    case BTN_Y:
    {
      if (i == BTN_X) {
        // Serial.println(F("Button X pressed"));
        serialPrintf(PSTR("\n%s X %s\n"), txts[0], txts[1]);
        myMsgType = lights_color_increase;
        colorIndex++;
        if (colorIndex > colorIndexMax)
          colorIndex = colorIndexMax;
      } else {
        // Serial.println(F("Button Y pressed"));
        serialPrintf(PSTR("\n%s Y %s\n"), txts[0], txts[1]);
        myMsgType = lights_color_decrease;
        colorIndex--;
        if (colorIndex < 0)
          colorIndex = 0;
      }
      Serial.print(F("colorIndex = "));
      Serial.println(colorIndex);
      break;
    }
    case BTN_SELECT:
    {
      // Serial.println(F("Button SELECT pressed"));
      serialPrintf(PSTR("\n%s SELECT %s\n"), txts[0], txts[1]);
      select_btn_idx++;
      if (select_btn_idx > select_btn_max)
        select_btn_idx = 0;
      break;
    }
    case BTN_START:
    {
      // Serial.println(F("Button START pressed"));
      serialPrintf(PSTR("\n%s START %s\n"), txts[0], txts[1]);
      do_reset();
      break; // This line will not be reached, but it's good practice to include it
    }
    default:
    {
      Serial.println(F("Unknown button pressed"));
    }
  }
  if (i == BTN_A || i == BTN_B || i == BTN_X || i == BTN_Y) { //} || btnSelect_pressed || btnStart_pressed) {
    buttonPressed[i] = false; // Reset the button state after handling
    a_button_has_been_pressed = true; // needed to provoke an immediate transmittion of the next mqtt message
    lastButtonState[i] = currentButtonState[i]; // Update the last state
    currentButtonState[i] = false; // Reset the current state for the next loop
    disp_msgType_chg();
    composeMsgTopic(myMsgType); // Prepare the MQTT topic based on the new message type (global variable msg_topic)
    delay(3000);
    canvas.fillScreen(ST77XX_BLACK);
    display.drawRGBBitmap(0, 0, canvas.getBuffer(), canvas_width, canvas_height);
  }
  else if (i == BTN_SELECT) {
    a_button_has_been_pressed = true; // needed to provoke an immediate transmittion of the next mqtt message
    buttonPressed[i] = false; // Reset the button state after handling
    lastButtonState[i] = currentButtonState[i]; // Update the last state
    currentButtonState[i] = false; // Reset the current state for the next loop
    disp_topic_types();
    delay(3000);
    disp_btn_info();
    delay(3000);
    canvas.fillScreen(ST77XX_BLACK);
    display.drawRGBBitmap(0, 0, canvas.getBuffer(), canvas_width, canvas_height);
  }
  else 
    i = BTN_NONE; // Reset the button index to todo value
}

bool ck_gamepad()
{
  if (!use_gamepad_qt) {
    return false; // If not using the gamepad, return false
  }

  static constexpr const char txt0[] PROGMEM = "ck_gamepad(): ";
   // Reverse x/y values to match joystick orientation
  int x = 1023 - ss.analogRead(14);
  int y = 1023 - ss.analogRead(15);
  bool btnPressed1 = false;
  
  if ( (abs(x - last_x) > 3)  ||  (abs(y - last_y) > 3)) {
    Serial.print("Joystick x: "); Serial.print(x); Serial.print(", "); Serial.print("y: "); Serial.println(y);
    last_x = x;
    last_y = y;
  }
  
#if defined(IRQ_PIN)
  if(!digitalRead(IRQ_PIN)) {
    return;
  }
#endif
  uint32_t buttons = ss.digitalReadBulk(button_mask);

  //Serial.println(buttons, BIN);

  if (! (buttons & (1UL << BUTTON_A))) {
    buttonPressed[BTN_A] = {true};
  } else {
    buttonPressed[BTN_A] = {false}; // Reset the button state if not pressed
  }
  if (! (buttons & (1UL << BUTTON_B))) {
    buttonPressed[BTN_B] = {true};
  } else {
    buttonPressed[BTN_B] = {false};
  }
  if (! (buttons & (1UL << BUTTON_X))) {
    buttonPressed[BTN_X] = {true};
  } else {
    buttonPressed[BTN_X] = {false};
  }
  if (! (buttons & (1UL << BUTTON_Y))) {
    buttonPressed[BTN_Y] = {true};
  } else {
    buttonPressed[BTN_Y] = {false};
  }
  if (! (buttons & (1UL << BUTTON_SELECT))) {
    buttonPressed[BTN_SELECT] = {true};
  } else {
    buttonPressed[BTN_SELECT] = {false};
  }
  if (! (buttons & (1UL << BUTTON_START))) {
    buttonPressed[BTN_START] = {true};
  } else {
    buttonPressed[BTN_START] = {false};
  }
  for (int i = 0; i < NUM_BUTTONS; i++) {
    if (buttonPressed[i]) {
      btnPressed1 = true;
      break; // Exit the loop if any button is pressed
    }
  }
#ifdef MY_DEBUG
  if (btnPressed1) {
    Serial.print(txt0);
    Serial.print(F("Button(s): "));
    for (int i = 0; i < NUM_BUTTONS; i++) {
      if (buttonPressed[i]) {
        Serial.print(ButtonNames[i]); // Print the button name
        Serial.print(" ");
      }
    }
    Serial.println(F("pressed"));
  }
#endif
  return btnPressed1;
}

bool preButtonChecks()
{
  static constexpr const char txt0[] PROGMEM = "preButtonChecks(): ";
  
  if (!use_gamepad_qt)
    return false;
  
  bool btnPressed2 = ck_gamepad(); // Check if any button is pressed
  
#ifdef MY_DEBUG
  Serial.print(txt0);
  Serial.print(F("button pressed ? "));
  Serial.println(btnPressed2 ? "Yes" : "No");
#endif

  if (!btnPressed2) {
    // If no button is pressed, return false
    return false;
  }

  unsigned long currentTime = millis();

  // If any button is pressed, update the last debounce time
  for (int i = 0; i < NUM_BUTTONS; i++) {
    if (buttonPressed[i]) {
#ifdef MY_DEBUG
      Serial.print(txt0);
      Serial.print(F("Button \'"));
      Serial.print(ButtonNames[i]); // Print the button name
      Serial.print(F("\' pressed at time: "));
      Serial.println(currentTime);
#endif
    }
    
    currentButtonState[i] = buttonPressed[i];
    // Check if the button state has changed since the last check
    if ( (currentButtonState[i] != lastButtonState[i]) && currentButtonState[i] ) {
      // Button state changed
      // Button is pressed
      handleButtonPress(static_cast<Button>(i));

      lastDebounceTime[i] = currentTime;
#ifdef MY_DEBUG
      Serial.print(txt0);
      Serial.print(F("Button \'"));
      Serial.print(ButtonNames[i]); // Print the button name
      Serial.print(F("\' current state: "));
      Serial.print(currentButtonState[i] ? "Pressed" : "Released");
      Serial.print(F(", last state: "));
      Serial.println(lastButtonState[i] ? "Pressed" : "Released");

      Serial.print(txt0);
      Serial.print(F("currentTime: "));
      Serial.print(currentTime);
      Serial.print(F(", lastDebounceTime["));
      Serial.print(i);
      Serial.print(F("]: "));
      Serial.print(lastDebounceTime[i]);
      Serial.print(F(", debounceDelay: "));
      Serial.println(debounceDelay);
      Serial.print(F("currentTime - lastDebounceTime["));
      Serial.print(i);
      Serial.print(F("] = "));
      Serial.print(currentTime - lastDebounceTime[i]);
      Serial.print(F("> debounceDelay: "));
      Serial.println( ( (currentTime - lastDebounceTime[i]) > debounceDelay) ? "true" : "false");
#endif
      if ((currentTime - lastDebounceTime[i]) > debounceDelay) {
        // If the button state is stable for longer than the debounce delay
        if (currentButtonState[i]) {
#ifdef MY_DEBUG
          Serial.print(txt0);
          Serial.print(F("Button \'"));
          Serial.print(ButtonNames[i]); // Print the button name
          Serial.print(F("\' pressed at time: "));
          Serial.println(currentTime);
#endif
          // btnPressed2 = true;
          break;
        }
      }
      //else {
        // Button is not pressed
      //  currentButtonState[i] = false;
      //}
      // Update the last button state
      lastButtonState[i] = currentButtonState[i];
      break; // The key that is presses is found, so exit loop
    }
  }
  return btnPressed2;
}

void setup() 
{
  //Initialize serial and wait for port to open:
  Serial.begin(115200);  
  //while (!Serial) { // Do not use this wait loop. It blocks mqtt transmissions when only on 5Volt power source!
  //  ; // wait for serial port to connect. Needed for native USB port only
  //}
  Serial2.begin(115200);  // WiFi/BT AT command processor on ESP32-S3

  delay(1000);

use_broker_local = (atoi(SECRET_USE_BROKER_LOCAL) == 1);

if (use_broker_local)
  broker = SECRET_MQTT_BROKER_LOCAL2; // "192.168._.___";
else
  broker = SECRET_MQTT_BROKER; // "test.mosquitto.org";

 // turn on the TFT / I2C power supply
#if defined(ARDUINO_ADAFRUIT_FEATHER_ESP32S3_TFT)
  pinMode(TFT_I2C_POWER, OUTPUT);
  digitalWrite(TFT_I2C_POWER, HIGH);
#endif

  pinMode(led, OUTPUT); // for the builtin single color (red) led

  pinMode(NEOPIXEL_POWER, OUTPUT);
  digitalWrite(NEOPIXEL_POWER, HIGH); // Switch off the Neopixel LED
  pixel.begin();
  pixel.setBrightness(50);
  neopixel_test();

  delay(10);

  display.init(135, 240);           // Init ST7789 240x135
  display.setRotation(3);
  //canvas.setFont(&FreeSans12pt7b);
  canvas.setFont(&FreeMono12pt7b);
  canvas.setTextColor(ST77XX_WHITE);
  if (lc_bat.begin()) 
  {
    Serial.println("✅ Found LC709203F");
    Serial.print("Version: 0x"); Serial.println(lc_bat.getICversion(), HEX);
    lc_bat.setPackSize(LC709203F_APA_500MAH);
    lcfound = true;
  }
  else 
  {
    Serial.println(F("❌ Couldn\'t find Adafruit LC709203F?\nChecking for Adafruit MAX1704X.."));
    delay(200);
    if (!max_bat.begin()) 
    {
      Serial.println(F("❌ Couldn\'t find Adafruit MAX1704X?\nMake sure a battery is plugged in!"));
      while (1) delay(10);
    }
    Serial.print(F("✅ Found MAX17048"));
    Serial.print(F(" with Chip ID: 0x")); 
    Serial.println(max_bat.getChipID(), HEX);
    maxfound = true;
    
  }
  
  setupDisplayTimes();

  pinMode(TFT_BACKLITE, OUTPUT);
  digitalWrite(TFT_BACKLITE, HIGH);

  //display.drawRGBBitmap(0, 0, canvas.getBuffer(), canvas_width, canvas_height);

  // ESP32 is kinda odd in that secondary ports must be manually
  // assigned their pins with setPins()!

  // Result output: Default port (Wire) I2C scan: 0x23, 0x36, 0x51, 0x6A, 0x76,
  Serial.print("Default port (Wire) ");
  TB.theWire = DEFAULT_I2C_PORT;
  TB.theWire->setClock(100000);
  TB.printI2CBusScan();

/*
#if defined(SECONDARY_I2C_PORT)
  Serial.print("Secondary port (Wire1) ");
  TB.theWire = SECONDARY_I2C_PORT;
  TB.printI2CBusScan();
#endif
*/
  byte rtc_address = 0x51;
  if (TB.scanI2CBus(rtc_address))
  { 
    Serial.print(F("✅ RTC found at address: 0x"));
    Serial.print(rtc_address, HEX);
    Serial.println(F(". Starting it."));
    RTC.begin();
    delay(1000); // Let the RTC settle itself
  }
  else
  {
    Serial.println(F("❌ RTC not found."));
    do_reset();
  }


  if (!handle_bme280())
  {
    Serial.println("❌ Initiating BME280 failed");
    Serial.println("Check wiring. Going into an endless loop...");
    while (true)
      delay(5000);
  }

  bool dummy2 = seesaw_connect();

  // attempt to connect to WiFi network:
  if (ConnectToWiFi())
  {
    if (WiFi.status() == WL_CONNECTED)
    {
      timeClient.begin();
      Serial.print(F("\nTimezone offset = "));
      if (tzOffset < 0)
        Serial.print("-");
      Serial.print(abs(utc_offset)/3600);
      Serial.println(F(" hour(s)"));
      Serial.println(F("Starting connection to NTP server..."));
      /*
      WiFiClient probe;
      if (probe.connect("192.168.1.114", 1883)) {  // 192.168.1.96 = PC Paul5, 192.168.1.114 = RaspberryPi CM5
        Serial.println(F("✅ TCP probe connect to broker successful"));
        probe.stop();
      } else {
        Serial.println(F("❌ TCP probe connect to broker failed"));
      }
      */
      //Serial.print(F("\nMQTT Attempting to connect to broker: "));
      //serialPrintf(PSTR("%s:%s\n"), broker, String(port).c_str());
  
      bool mqtt_connected = false;
      for (uint8_t i=0; i < 10; i++)
      {
        if (!mqttClient.connect(broker, port))
        {
          if (mqttClient.connectError() == 5) // = Connection refused. Client is not authorized
          {
            Serial.println(F("❌ MQTT connection refused. Client not authorized."));
            break;
          }
          else
          {
            serialPrintf(PSTR("❌ MQTT connection to broker failed! Error code = %s\n"), String(mqttClient.connectError()).c_str() );        
            delay(1000);
          }
        }
        else
        {
          mqtt_connected = true;
        }
      }
      if (!mqtt_connected)
      {
        Serial.print(F("❌ MQTT Unable to connect to broker in LAN. Going into infinite loop..."));
        while (true)
          delay(5000);
      }

      Serial.print(F("✅ MQTT You're connected to "));
      serialPrintf(PSTR("%s broker %s:%s\n"), (use_broker_local) ? "local" : "remote", broker, String(port).c_str());
    }
  }
  composeMsgTopic(); // Prepare the MQTT default topic (global variable msg_topic)
  /*
  disp_topic_types();
  delay(5000);
  disp_btn_info();
  delay(5000);
  */
  rtc_sync(); // Update RTC from NTP server
  // Note that rtc_sync() calls getUnixTimeFromRTC() too (as was done in the 2nd following line below)
  // We call this function now to have the global variable HoursLocal updated
  //unsigned long dummy1 = getUnixTimeFromRTC();
  // HoursLocal is now set. It will be used in isItDisplayBedtime()

  if (!isItDisplayBedtime())
    disp_intro();
}

void loop() 
{
  static constexpr const char txt0[] PROGMEM = "loop(): ";
  char sID[] = "Feather";  // length 7 + 1
  //set interval for sending messages (milliseconds)
  unsigned long mqtt_start_t = millis();
  unsigned long mqtt_curr_t = 0L;
  unsigned long mqtt_elapsed_t = 0L;
  unsigned long mqtt_interval_t = 1 * 60 * 1000; // 1 minute

  unsigned long ntp_start_t = mqtt_start_t;
  unsigned long ntp_curr_t = 0L;
  unsigned long ntp_elapsed_t = 0L;
  unsigned long ntp_interval_t = 15 * 60 * 1000; // 15 minutes

  bool start = true;

  serialPrintf(PSTR("board ID = \"%s\"\n"), sID);

  uint8_t interval_in_mins = mqtt_interval_t / (60 * 1000);
  serialPrintf(PSTR("%sMQTT message send interval = %d minute%s\n"), txt0, interval_in_mins, interval_in_mins <= 1 ? "" : "s");
  bool dummy = false;
  bool displayIsAsleep = false;
  bool newBtnPressed = false;
  unsigned long currentTime;
  
  unsigned long previousMillis = 0;
  const unsigned long interval = 3000;
  int screenState = 0; // 0 = info, 1 = sensor

  while (true)
  {
    // If the gamepad, for one or another reason is not connected
    if (!use_gamepad_qt) {
      dummy = seesawIsConnected();
      if (dummy)  // gamepad QT found, connect to it
        seesaw_connect();
    }
    dummy = preButtonChecks(); // Check for button presses and handle them
    
    // call poll() regularly to allow the library to send MQTT keep alive which
    // avoids being disconnected by the broker
    mqttClient.poll();

    unsigned long ntp_curr_t = millis();
    ntp_elapsed_t = ntp_curr_t - ntp_start_t;
    if (start || ntp_curr_t - ntp_start_t >= ntp_interval_t)
    {
      ntp_start_t = ntp_curr_t;
      rtc_sync();
    }

    if (!ck_timeIsValid())
      rtc_sync(); // Sync the RTC with the NTP server if the time is not valid

    mqtt_curr_t = millis();
    mqtt_elapsed_t = mqtt_curr_t - mqtt_start_t;
    if (start || a_button_has_been_pressed || mqtt_elapsed_t >= mqtt_interval_t) 
    { 
      start = false;
      a_button_has_been_pressed = false; // reset this flag
      // save the last time a message was sent
      mqtt_start_t = mqtt_curr_t;

      uint8_t try_cnt = 0;
      uint8_t try_cnt_max = 10;

      while (!send_msg())
      {
        try_cnt++;
        if (try_cnt >= try_cnt_max)
          break;
        delay(50);
      } 
    }
    
    // Only display the messages if not in bedtime mode
    isItBedtime = isItDisplayBedtime();

#ifdef MY_DEBUG
    serialPrintf(PSTR("isItBedtime = %s\n"), (isItBedtime) ? "true" : "false");
#endif
    if (isItBedtime)
    {
      // If it is bedtime, clear the display
      if (!displayIsAsleep)
      {
        if (!preButtonChecks()) {  // Check and handle gamepad keypresses first
          // If the display is not asleep, show a goodnight message
          disp_goodnight();
          delay(5000); // Show the text for 5 seconds
          // Clear the display
          canvas.fillScreen(ST77XX_BLACK);
          display.drawRGBBitmap(0, 0, canvas.getBuffer(), canvas_width, canvas_height);
          //digitalWrite(TFT_I2C_POWER, LOW); // This probably also cuts off the I2C connection with the BME280
          displayIsAsleep = true;
        }
      }
    }
    else
    {
      if (displayIsAsleep)
      {
        // Only display the messages if not in bedtime mode

        isItBedtime = isItDisplayBedtime();
        if (!isItBedtime) {
#ifdef MY_DEBUG
          serialPrintf(PSTR("isItBedtime = %s\n"), (isItBedtime) ? "true" : "false");
#endif
        }
        digitalWrite(TFT_I2C_POWER, HIGH);
        if (!preButtonChecks()) {  // Check and handle gamepad keypresses first
          // disp_goodmorning();
          greeting_handler();
          delay(5000); // Show the text for 5 seconds
          // Clear the display
          canvas.fillScreen(ST77XX_BLACK);
          display.drawRGBBitmap(0, 0, canvas.getBuffer(), canvas_width, canvas_height);
          displayIsAsleep = false; // reset the displayIsAsleep flag
        }
      }
      if (!preButtonChecks()) {
        unsigned long currentMillis = millis();

        // Check if it's time to switch screen
        if (currentMillis - previousMillis >= interval) {
          previousMillis = currentMillis;

          // Toggle between screens
          if (screenState == 0) {
            disp_msg_info(false);
            screenState = 1;
          } else {
            disp_sensor_data(false);
            screenState = 0;
          }
        }
      }
    }
  }
}

