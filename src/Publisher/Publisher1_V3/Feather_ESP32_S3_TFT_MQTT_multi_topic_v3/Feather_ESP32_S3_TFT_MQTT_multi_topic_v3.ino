/*
  Feather_ESP32_S3_TFT_MQTT_w_Pimoroni_2xqwstpad_v2.ino

  Sunday 2025-08-03 05h25 utc +1
  Adafruit Feather ESP32-S3 TFT MQTT test adaption for use with Pimoroni QwST Gamepad
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
  Update 2025-08-13. Change to use Pimoroni QwstPad. Eventually more than one QwstPad (max 4). Changed ckForButtonPress. Using Event functionality
  Update 2025-08-19. In split_msg() added code to handle an added nexted JSonObject "header" alias "head" containing the elements (example sensorTPAH message type): 
  "head": {"ow": "Feath", "de": "PC-Lab", "dc": "BME280", "sc": "meas", "vt": "f", "ts": 1755622875},
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
#include <vector>
#include <time.h>
#include <stdlib.h>  // for setenv
#include "secrets.h"
#include "Adafruit_MAX1704X.h"
#include "Adafruit_LC709203F.h"
#include <Adafruit_NeoPixel.h>
#include "Adafruit_TestBed.h"
#include <Adafruit_BME280.h>
#include <Adafruit_ST7789.h> 
//#include <Adafruit_seesaw.h>
#include "qwstpad.h"
//#include <Fonts/FreeSans12pt7b.h>
#include <Fonts/FreeMono12pt7b.h>
#include "esp_heap_caps.h"

#include "buttons.h"
// #define IRQ_PIN   5

#ifdef USE_QNH 
#undef USE_QNH
#endif

#ifdef MY_DEBUG
#undef MY_DEBUG
#endif

#ifdef USE_QNH
#include <HTTPClient.h>
bool use_qnh = false;
int qnh = 1012; // default mBar
#endif 

uint8_t NUM_PADS = 0;

struct padBtn {
  uint8_t padID = 0; // Unique identifier for the pad
  bool use_qwstpad = false;
  uint8_t address = 0;
  int8_t logic = -1; // set to -1 if not set
  uint16_t buttons = 0;
  uint16_t buttons_old = 0;
  std::string key = "";
  int8_t btn_idx = -1;
  bool buttonPressed = false;
  bool lastButtonState = false;
  bool currentButtonState = false;
  unsigned long lastDebounceTime = 0;
};

std::map<std::string, std::string> keyAliases = {
  {"X", "X"},
  {"Y", "Y"},
  {"A", "A"},
  {"B", "B"},  
  {"P", "PLUS"},
  {"M", "MINUS"},
  {"U", "UP"},
  {"L", "LEFT"},
  {"R", "RIGHT"},
  {"D", "DOWN"}
};

// Make this definition in your application code to use std::functions for onMessage callbacks instead of C-pointers:
#define MQTT_CLIENT_STD_FUNCTION_CALLBACK

Adafruit_LC709203F lc_bat;
Adafruit_MAX17048 max_bat;
extern Adafruit_TestBed TB;

#define DEFAULT_I2C_PORT &Wire
#define SECONDARY_I2C_PORT &Wire1
#define CURRENT_MAX_PADS 2

#ifndef SDA1
#define SDA1 10
#endif

#ifndef SCL1
#define SCL1 11 
#endif

// Create a QwstPad instance
// QwstPad* pad;  // Global pointer
QwstPad* pads[CURRENT_MAX_PADS];  // Declare globally as pointers

padBtn padLogic[CURRENT_MAX_PADS]; // Logic array aligned with pads

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
  lights_dclr_increase = 4,
  lights_dclr_decrease = 5,
  msg_todo = 6
};

mqtt_msg_type myMsgType = tpah_sensor;// create an enum class variable and assign default message type value
char msg_topic[36];  // was 23

// Function declaration so that it will be found by other functions
void disp_msg(const char* arr[], size_t size, bool disp_on_serial);

static constexpr const char *weekdays[] PROGMEM = {"Sun", "Mon", "Tues", "Wednes", "Thurs", "Fri", "Satur" };

//               Button    A                   B               
//                         X                   Y        
//                         LEFT                RIGHT
const char *msgTypes[] = {"sensors",          "lights_toggle", 
                          "lights_color_inc", "lights_color_dec", 
                          "lights_dclr_inc",  "lights_dclr_dec",   "todo"};
int colorIndex = 0;
int colorIndexMin = 0;
int colorIndexMax = 9;

int DispColorIndex = 1;  // color NAVY
int DispColorIndexMin = 1;  // No black (0)
int DispColorIndexMax = 11;

int select_btn_idx = 0;
int select_btn_max = 1;

#ifndef LED_BUILTIN
#define LED_BUILTIN 13
#endif

#ifndef NEOPIXEL_POWER
#define NEOPIXEL_POWER 34
#endif

#ifndef TFT_BACKLITE
#define TFT_BACKLITE 45
#endif
bool backLite = true;

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


#ifdef USE_QNH
//const char* ssid = "your_wifi_ssid";
//const char* password = "your_wifi_password";
uint8_t qnh_fetch_limit = atoi(SECRET_METAR_FETCH_LIMIT);
const char* my_api_key = SECRET_METAR_TAF_API_KEY;
const char* base_url = "https://api.metar-taf.com/metar?api_key=";
String endpoint = String(base_url) + String(SECRET_METAR_TAF_API_KEY) + "&v=2.3&locale=pt-PT&id=LPPT";
// Copilot advised: if you later add more parameters like locale or airport ID, you can extend the string like so:
int credits_left = 0;

int fetchQNH() {
  HTTPClient http;
  http.begin(endpoint.c_str());
  int httpCode = http.GET();

  if (httpCode > 0) {
    String response = http.getString();
    DynamicJsonDocument doc(2048);  // current length 1747 (capacity = 1747 * 1.1; // ≈ 1922 bytes) round it upt to 2048
    DeserializationError error = deserializeJson(doc, response);
    bool test = true;
    if (!error) {
      if (test) {
        Serial.print(F("fetchQNH(): http.GET() result = "));
        size_t jsonLength = serializeJson(doc, Serial);
        Serial.println(); // optional newline
        Serial.print("Length: ");
        Serial.println(jsonLength);
        Serial.println();
      }
      bool new_status = doc["status"];
      int new_credits_left = doc["credits"];
      Serial.print(F("status: "));
      Serial.println(new_status);
      Serial.print(F("credits: "));
      Serial.println(new_credits_left);
      int fQnh = doc["metar"]["qnh"];
      const char* metar_raw = doc["metar"]["raw"];
      Serial.print(F("METAR raw: "));
      Serial.println(metar_raw);
      return fQnh;
    } else {
      Serial.println("JSON parsing failed");
    }
  } else {
    Serial.print("HTTP error: ");
    Serial.println(httpCode);
  }
  http.end();
  return -1; // Sentinel value for failure
}
#endif

bool displayIsAsleep = false;

Adafruit_ST7789 display = Adafruit_ST7789(TFT_CS, TFT_DC, TFT_RST);

GFXcanvas16 canvas(240, 135);

int canvas_width = canvas.width();
int canvas_height = canvas.height();


// See: https://learn.adafruit.com/gamepad-qt/arduino
/*
// See definition of enum Button in qwstpad.h
#define BUTTON_NONE      -1
#define BUTTON_UP        1
#define BUTTON_LEFT      2
#define BUTTON_RIGHT     3
#define BUTTON_DOWN      4
#define BUTTON_MINUS     5  // replacement for Adafruit SELECT
#define BUTTON_PLUS      11 // replacement for Adafruit START
#define BUTTON_B         12
#define BUTTON_Y         13
#define BUTTON_A         14
#define BUTTON_X         15
*/

uint16_t button_mask = (1UL << BUTTON_X)    | (1UL << BUTTON_Y) | 
                       (1UL << BUTTON_A)    | (1UL << BUTTON_B) | 
                       (1UL << BUTTON_UP)   | (1UL << BUTTON_DOWN) |
                       (1UL << BUTTON_LEFT) | (1UL << BUTTON_RIGHT) | 
                       (1UL << BUTTON_PLUS) | (1UL << BUTTON_MINUS);

const unsigned long debounceDelay = 500; // ms

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
unsigned long mqttMsgID_old = 0L;
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

int        port = atoi(SECRET_MQTT_PORT); 
const char MQTT_CLIENT_ID[]                      = SECRET_MQTT_CLIENT_ID;                                                           // 1883;
const char TOPIC_PREFIX_SENSORS[]                = SECRET_MQTT_TOPIC_PREFIX_SENSORS;                 // "sensors"
const char TOPIC_PREFIX_LIGHTS[]                 = SECRET_MQTT_TOPIC_PREFIX_LIGHTS;                  // "lights"
const char TOPIC_PREFIX_TODO[]                   = SECRET_MQTT_TOPIC_PREFIX_TODO;                    // "todo"

const char TOPIC_PUBLISHER[]                     = SECRET_MQTT_PUBLISHER;                            // "Feath"

const char TOPIC_SUFFIX_SENSORS[]                = SECRET_MQTT_TOPIC_SUFFIX_SENSORS;                 // "ambient"
const char TOPIC_SUFFIX_LIGHTS_TOGGLE[]          = SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_TOGGLE;           // "toggle"
const char TOPIC_SUFFIX_LIGHTS_COLOR_DECREASE[]  = SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_COLOR_DECREASE;   // "color_dec"
const char TOPIC_SUFFIX_LIGHTS_COLOR_INCREASE[]  = SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_COLOR_INCREASE;   // "color_inc"
const char TOPIC_SUFFIX_LIGHTS_DCLR_DECREASE[]   = SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_DCLR_DECREASE;    // "dclr_dec"
const char TOPIC_SUFFIX_LIGHTS_DCLR_INCREASE[]   = SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_DCLR_INCREASE;    // "dclr_inc"
const char TOPIC_SUFFIX_TODO[]                   = SECRET_MQTT_TOPIC_SUFFIX_TODO;                    // "todo"
const char topic1[]                              = SECRET_MQTT_SYS_TOPIC1;                           // "$SYS/broker/clients/connected";
const char topic2[]                              = SECRET_MQTT_SYS_TOPIC2;                           // "$SYS/broker/clients/disconnected";

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
/*
 My location streetlevel elevation is 96m. 
 My apt building roof elevation is 135 m = 39m above streetlevel.
 Assuming each floor has a height of 4m, then the 10th of 11 floors is
 Roof - 2 x 4m = roof - 8m = 135 - 8 = 127m above sealeavel = 
 127 - 96 = 31m above my street level.
 If, in this moment the corrected altitude = 102m then we should add as correction for my
 floor level: 25m. 
 Note that the calculated altitude by the BME280 is changing when the barometric pressure is changing,
 which is OK if you would be in a car or an aircraft that is changing elevation,
 however I live in a building at a fixed elevation. Therefore it cannot be that the elevation is changing.
 Anyway, I think that it is good to apply (for my location) a correction of +25m to the reading.
*/
#define ELEVATION_CORRECTION (25) 

Adafruit_BME280 bme; // I2C
bool bmefound = false;
uint8_t bme_bad_read_cnt = 0;
uint8_t bme_bad_read_cnt_max = 3;

unsigned long delayTime;

void clr_buttons(uint8_t i, bool all = false) {
  if (i < 0 || i >= CURRENT_MAX_PADS) {
    Serial.println(F("Invalid pad index in clr_buttons()"));
    return;
  }

  if (all) { // Clear all pads
    for (int i = 0; i < CURRENT_MAX_PADS; ++i) {
      if (padLogic[i].use_qwstpad) {
        padLogic[i].key = ""; // Clear the key
        padLogic[i].btn_idx = -1;
        padLogic[i].buttons = 0; // Clear the button state
        padLogic[i].buttons_old = 0; // Clear the old button state
        padLogic[i].buttonPressed = 0; // Clear the button state
        padLogic[i].lastButtonState = false; // Reset last button state
        padLogic[i].currentButtonState = false; // Reset current button state
        padLogic[i].lastDebounceTime = 0; // Reset debounce time
      }

    }
  } else { // Clear only the specified pad
    if (padLogic[i].use_qwstpad) {
      padLogic[i].key = ""; // Clear the key
      padLogic[i].btn_idx = -1; // Clear the btn_idx
      padLogic[i].buttons = 0; // Clear the button state
      padLogic[i].buttons_old = 0; // Clear the old button state
      padLogic[i].buttonPressed = 0; // Clear the button state
      padLogic[i].lastButtonState = false; // Reset last button state
      padLogic[i].currentButtonState = false; // Reset current button state
      padLogic[i].lastDebounceTime = 0; // Reset debounce time
    }
  }
}

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
    case lights_dclr_increase:
    case lights_dclr_decrease:
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
      else if (msgType == lights_dclr_increase)
        strcat(msg_topic, TOPIC_SUFFIX_LIGHTS_DCLR_INCREASE);
      else if (msgType == lights_dclr_decrease)
        strcat(msg_topic, TOPIC_SUFFIX_LIGHTS_DCLR_DECREASE);
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

void printFreeMemory() {
  Serial.print("Free heap: ");
  Serial.print(esp_get_free_heap_size());
  Serial.println(" bytes");

  Serial.print("Minimum free heap ever: ");
  Serial.print(esp_get_minimum_free_heap_size());
  Serial.println(" bytes");

  Serial.print("Largest block available: ");
  Serial.print(heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT));
  Serial.println(" bytes");
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
  // getUnixTimeFromRTC(true);  // This function is called in setup() and next called every minutes.
  
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

bool qwstpadConnectMsgShown = false;

bool qwstpadIsConnected(uint8_t PadNr) {
  byte addr;
  bool use_qwstpad = false;

  if (PadNr == 0)
    addr = DEFAULT_ADDRESS;
  else if (PadNr == 1)
    addr = ALT_ADDRESS_1;

  if (TB.scanI2CBus(addr)) {  // For the Pimoroni multi-sensor-stick
    Serial.print(F("✅ qwst Pad address: 0x"));
    Serial.println(addr, HEX);
    use_qwstpad = true;
  }
  else
  {
    if (!qwstpadConnectMsgShown) {
      qwstpadConnectMsgShown = true;
      Serial.print(F("❌ qwst Pad not found at address: 0x"));
      Serial.println(addr, HEX);
    }
  }
  return use_qwstpad;
}

bool qwstpad_connect(uint8_t PadNr) {
  //QwstPad* pad = (PadNr == 0) ? &pad1 : &pad2;
  //PadBtn* padLogic = (PadNr == 0) ? &padLogic1 : &padLogic2;
  const char* padLabel = (PadNr == 0) ? "Pad 1" : "Pad 2";

  const uint8_t maxTries = 10;
  uint8_t tries = 0;
  qwstpadConnectMsgShown = false;

  while (!padLogic[PadNr].use_qwstpad && tries < maxTries) {
    if (pads[PadNr]->isConnected()) {
      padLogic[PadNr].use_qwstpad = true;
      Serial.print(F("✅ "));
      Serial.print(padLabel);
      Serial.println(F(" is connected!"));
      pads[PadNr]->begin();
      break;
    } else {
      Serial.print(F("❌ "));
      Serial.print(padLabel);
      Serial.println(F(" not found."));
      tries++;
      delay(100);
    }
  }

  if (!padLogic[PadNr].use_qwstpad) {
    Serial.print(F("❌ ERROR! "));
    Serial.print(padLabel);
    Serial.println(F(" not found, trying again later."));
    return false;
  }

  Serial.print(F("✅ "));
  Serial.print(padLabel);
  Serial.println(F(" started"));

#if defined(IRQ_PIN)
  pinMode(IRQ_PIN, INPUT);
#endif

  return true;
}


/* Function to perform a software reset on an Arduino board,
   specifically using the ArduinoCore-renesas.
   Arduino has a built-in function named as resetFunc()
   which we need to declare at address 0 and when we 
   execute this function Arduino gets reset automatically.
   Using this function resulted in a "Fault on interrupt 
   or bare metal (no OS) environment crash!
*/
void do_reset(bool disp_on_serial = false) {
  disp_reset_msg(disp_on_serial);
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
      do_reset(true);
      //break;
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

  if (!backLite)
    backlite_toggle();

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

  if (backLite && displayIsAsleep) {
    delay(3000);
    backlite_toggle();
  }
}

void disp_intro(bool disp_on_serial = false) {
  const char *msg[] = {"Adafruit Feather",
                       "ESP32-S3 TFT as",
                       "MQTT publisher",
                      "device"};

  disp_msg(msg, sizeof(msg) / sizeof(msg[0]), disp_on_serial);
}

void disp_btn_info() {


#ifdef USE_QNH
  const char *msg1[] = {"Gamepad Btns 1:",
                       "A/B +/- topic",
                       "X/Y +/- color",
                       "Sel > show this",
                       "Sta > reset board"};
  const char *msg2[] = {"Gamepad Btns 2:",
                       "L QNH on/off",
                       "R ----------",
                       "U ----------",
                       "D ----------"};
  
  for (uint8_t i = 0; i < 2; i++) {
    if (i == 0)
      disp_msg(msg1, sizeof(msg1) / sizeof(msg1[0]), true);
    else if (i == 1)
      disp_msg(msg2, sizeof(msg2) / sizeof(msg2[0]), true);
    else
      break;
  }
#else 
  const char *msg[] = {"Gamepad Btns:",
                       "U/D +- amb color",
                       "L/R +- disp color",
                       "Min > show this",
                       "Plu > reset board"};
  
  disp_msg(msg, sizeof(msg) / sizeof(msg[0]), true);
#endif
}

void disp_topic_types() {
  // Display the message types on the TFT display
  const char *msg[] = {"Topic types:",
                       "A: Sensor data",
                       "B: Lights toggle",
                       "X/Y +- Amb color"};
  
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
 Parameter ret_LOCAL_or_GMT default false.
   if true:  returns unixLOC
   if false: returns unixUTC
}
 */
unsigned long getUnixTimeFromRTC(bool ret_Loc_or_GMT = false) 
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

  //return unixLOC; // was: unixUTC
  if (ret_Loc_or_GMT)
    return unixLOC;
  else 
    return unixUTC;
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
  // mqttMsgID = getUnixTimeFromRTC(false); // Use unixUTC !
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
  
  static constexpr const char txt0[] PROGMEM = "composePayload(): ";
  bool stop = false;

  StaticJsonDocument<CAPACITY> doc;

  clr_payloadBuffer(payloadBuffer, sizeof(payloadBuffer)); // Clear the payload buffer
  if (!doc.isNull())
    doc.clear(); // Clear the JSON document
  
  mqttMsgID = getUnixTimeFromRTC(false); // Important! Used in composePayload() use unixUTC!
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

  JsonObject header = doc.createNestedObject("hd");

  // Root fields
  header["ow"] = "Feath";    // owner
  header["de"] = "Lab";   // description (room, office, etc.)

  switch(myMsgType) 
  {
    case tpah_sensor:
    {
      header["dc"] = "BME280";   // device_class
      header["sc"] = "meas";     // state_class
      header["vt"] = "f";        //  f = value type (for all values) float
      break;
    }
    case lights_toggle:
    {
      header["dc"] = "home";     // device_class
      header["sc"] = "ligh";     // state_class
      header["vt"] = "i";        //  i = value type (for all values) integer (however, representing boolean: 1 = true, 0 = false)
      break;
    }
    case lights_color_increase:
    case lights_color_decrease:
    {
      header["dc"] = "colr";  // device_class
      if (myMsgType == lights_color_increase)
        header["sc"] = "inc";  // state_class
      else if (myMsgType == lights_color_decrease)
        header["sc"] = "dec";
      header["vt"] = "i";     //  i = value type
      break;
    }
    case lights_dclr_increase:
    case lights_dclr_decrease:
    {
      header["dc"] = "dclr";  // device_class
      if (myMsgType == lights_dclr_increase)
        header["sc"] = "inc";  // state_class
      else if (myMsgType == lights_dclr_decrease)
        header["sc"] = "dec";
      header["vt"] = "i";     //  i = value type
      break;
    }
    case msg_todo:
    {
      header["dc"] = "todo";   // device_class
      header["sc"] = "todo";   // state_class
      header["vt"] = "s";      //  s = value type (for all values) string
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

  //  global var mqttMsgID is an unsigned long (takes 10 bytes while a human-readable full datetime = 19bytes)
  header["t"] = mqttMsgID;  

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
      color_IncDec["mn"] = colorIndexMin;    // minimum value
      color_IncDec["mx"] = colorIndexMax;   // maximum value
      break;
    }
    case lights_dclr_increase:
    case lights_dclr_decrease:
    {
      // JsonObject dclr_IncDec;
      // Lights display color increase/decrease
      JsonObject dclr_IncDec = doc.createNestedObject((myMsgType == lights_dclr_increase) ? "dclrInc" : "dclrDec");
      dclr_IncDec["v"] = DispColorIndex; // is a global variable
      dclr_IncDec["u"] = "i";   // unit of measurement, here it is an integer
      dclr_IncDec["mn"] = DispColorIndexMin;    // minimum value
      dclr_IncDec["mx"] = DispColorIndexMax;   // maximum value
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
  //header["readings"]["temperature"]["value"] = serialized(String(temperature, 1));  // 1 decimal
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

uint8_t ensureMqttConnection() {
  if (!mqttClient.connected()) {
    Serial.println("MQTT disconnected. Attempting reconnect...");

    // Customize your client ID
    mqttClient.setId(MQTT_CLIENT_ID);
    
    // Optional: set credentials
    // mqttClient.setUsernamePassword("username", "password");

    mqttClient.connect(broker, 1883);
    if (mqtt_connect_fail())
      do_reset(true);
    /*
    if (result == 1) {
      Serial.println("MQTT connected ✅");
    } else {
      Serial.print("MQTT connect failed ❌ Error code: ");
      Serial.println(mqttClient.connectError());
    }
    */
  }
  return (mqttClient.connected());
}

void onMqttMessage(int messageSize) {
  static constexpr const char txt0[] PROGMEM = "onMqttMessage(): ";
  Serial.print(F(txt0));
  Serial.print(F("Received a message, topic: \""));
  String topic = mqttClient.messageTopic();
  Serial.print(topic);
  Serial.print(F("\", length: "));
  Serial.print(messageSize);
  Serial.println(F(" bytes:"));

  char msg_lines[5][18] = {};  // 5 lines, 17 chars max (+1 null terminator)
  uint8_t line_idx = 0;
  uint8_t col_idx = 0;
  uint16_t c_cnt = 0;

  // Line 0 holds the topic
  String formatted_topic = "TOPIC: " + topic;
  strncpy(msg_lines[0], formatted_topic.c_str(), 17);
  msg_lines[0][17] = '\0';

  // Line 1 gets "MSG: " prefix
  strncpy(msg_lines[1], "MSG: ", 5);
  col_idx = 5;
  line_idx = 1;

  // Prepare buffer for raw payload (separate from msg_lines)
  char payloadBuffer[8] = {};
  uint8_t p_idx = 0;

  // Fill in the payload character by character
  Serial.print(F("msg received: \""));
  while (mqttClient.available()) {
    char c = (char)mqttClient.read();
    Serial.print(c);
    c_cnt++;

    // Store in display buffer
    if (line_idx < 5 && col_idx < 17) {
      msg_lines[line_idx][col_idx++] = c;
      msg_lines[line_idx][col_idx] = '\0';
    } else if (line_idx < 4) {
      line_idx++;
      col_idx = 0;
      msg_lines[line_idx][col_idx++] = c;
      msg_lines[line_idx][col_idx] = '\0';
    }

    // Store in clean payload buffer
    if (p_idx < sizeof(payloadBuffer) - 1) {
      payloadBuffer[p_idx++] = c;
      payloadBuffer[p_idx] = '\0';
    }
  }
  Serial.println("\"");

  // Smart message formatting based on topic type
  if (topic.indexOf("connect") >= 0) {
    int clientCount = atoi(payloadBuffer);
    snprintf(msg_lines[1], 18, "Connected: %d", clientCount);
  } else if (topic.indexOf("disconnect") >= 0) {
    int clientCount = atoi(payloadBuffer);
    snprintf(msg_lines[1], 18, "Disconnected: %d", clientCount);
  } else {
    snprintf(msg_lines[1], 18, "MSG: %s", payloadBuffer);
  }

  Serial.print(F(txt0));
  Serial.print("characters rcvd: ");
  Serial.println(c_cnt);

  // Prepare pointers for display
  const char* line_ptrs[5];
  for (int i = 0; i < 5; i++) {
    line_ptrs[i] = msg_lines[i];
  }

  disp_msg(line_ptrs, line_idx + 1, true);
  delay(5000);
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
  else if (myMsgType == lights_dclr_decrease) {
    ; // Decrease the display color value
  }
  else if (myMsgType == lights_dclr_increase) {
    ; // Increase the displaycolor value
  }

  int written = composePayload(payloadBuffer, sizeof(payloadBuffer), temperature, pressure, altitude, humidity, timestamp);
  if (written <= 0) {
    Serial.println("⚠️ Failed to compose JSON payload");
    neopixel_off();
    return ret;
  } else {
    if (myMsgType == tpah_sensor && mqttMsgID == mqttMsgID_old) { // prevent double transmission
#ifdef MY_DEBUG
    Serial.print(txt0);
    Serial.print(F("⚠️ msg not sent! Reason: mqttMsgID = "));
    Serial.print(mqttMsgID);
    Serial.print(F(", mqttMsgID_old = "));
    Serial.println(mqttMsgID_old);
#endif
      neopixel_off();
      return -1;
    }
    Serial.print(txt0);
    serialPrintf(PSTR("Bytes written by composePayload(): %d\n"), written);
    //char msg_topic[36];  // was 23
    
    msgGrpID++;
    if (msgGrpID > msgGrpID_max)
      msgGrpID = 1;


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
    Serial.print(txt0);
    Serial.print(F("Topic: "));
    serialPrintf(PSTR("\"%s\"\n"), msg_topic);
#endif

#ifndef MY_DEBUG
    Serial.print(txt0);
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
    Serial.println(isoBufferUTC);  // was isoBufferLocal, however the sent mqttMsgID (a unixTime) is in UTC !

    if (ensureMqttConnection()) {
      mqttClient.beginMessage(msg_topic);
      mqttClient.print(payloadBuffer);
      bool success = mqttClient.endMessage();
      // delay(1000);  // spread the four messages 1 second
      if (success) {
        Serial.println("✅ MQTT message sent");
      } else {
        Serial.println("❌ Failed to send MQTT message ");
      }
      Serial.print(F("MQTT message group: "));
      serialPrintf(PSTR("%3d sent\n"), msgGrpID);
      ret = true;
    }
    else {
      Serial.println("❌ MQTT still disconnected. Message not sent.");
    }
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
        do_reset(true);
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
  altitude = bme.readAltitude(SEALEVELPRESSURE_HPA) + ELEVATION_CORRECTION; // Altitude in meters
  humidity = bme.readHumidity();

#ifndef MY_DEBUG
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

void handleButtonPress(Button i) {
  static constexpr const char txt0[] PROGMEM = "handleButtonPress(): ";

  if (i >= BUTTON_X && i <= BUTTON_A) {
    Serial.print(txt0);
    Serial.print(F("wrong button value: "));
    Serial.print(i);
    Serial.println(F(". Exiting function!"));
    return;
  }
  switch (i) {
    case BUTTON_A:
    {
      //Serial.println(F("Button A pressed"));
      //serialPrintf(PSTR("\n%s A %s\n"), txts[0], txts[1]);
      myMsgType = tpah_sensor;
      Serial.println(F("changing to temperature, pressure, humidity sensor mode"));
      break;
    }
    case BUTTON_B:
    {
      myMsgType = lights_toggle;
      remote_led_is_on = !remote_led_is_on; // toggle the value
      Serial.print(F("remote light changed. Light = "));
      Serial.println((remote_led_is_on) ? "On" : "Off");
      break;
    }
    case BUTTON_X:
    case BUTTON_UP:
    {
      myMsgType = lights_color_increase;
      colorIndex++;
      if (colorIndex > colorIndexMax)
        colorIndex = colorIndexMin;  // wrap around
      Serial.print(F("colorIndex = "));
      Serial.println(colorIndex);
      //remote_led_is_on = true;
      break;
    }
    case BUTTON_Y:
    case BUTTON_DOWN:
    {
      myMsgType = lights_color_decrease;
      colorIndex--;
      if (colorIndex < 0)
        colorIndex = colorIndexMax; // wrap around
      Serial.print(F("colorIndex = "));
      Serial.println(colorIndex);
      //remote_led_is_on = true;
      break;
    }
    case BUTTON_LEFT:
    {
      // Change display color of Presto subscriber
      DispColorIndex--;
      myMsgType = lights_dclr_decrease;
      if (DispColorIndex < 0)
        DispColorIndex = DispColorIndexMax; // wrap around
#ifdef USE_QNH
      use_qnh = !use_qnh;// toggle qnh flag
      Serial.print(txt0);
      Serial.print(F("Get METAR switched: "));
      Serial.println(use_qnh ? "ON" : "OFF");
#endif
      break;
    }
    case BUTTON_RIGHT:
    {
      // Change display color of Presto subscriber
      DispColorIndex++;
      myMsgType = lights_dclr_increase;
      if (DispColorIndex > DispColorIndexMax)
        DispColorIndex = DispColorIndexMin;  // wrap around
      break;
    }
    case BUTTON_MINUS:
    {
      select_btn_idx++;
      if (select_btn_idx > select_btn_max)
        select_btn_idx = 0;
      break;
    }
    case BUTTON_PLUS:
    {
      do_reset(true);
      break; // This line will not be reached, but it's good practice to include it
    }
    default:
    {
      Serial.println(F("Unknown button pressed"));
    }
  }
  if (i == BUTTON_A || i == BUTTON_B || i == BUTTON_X || i == BUTTON_Y || i == BUTTON_LEFT || i == BUTTON_RIGHT  || i == BUTTON_UP || i == BUTTON_DOWN) { //} || btnMinus_pressed || btnPlus_pressed) {
    disp_msgType_chg();
    composeMsgTopic(myMsgType); // Prepare the MQTT topic based on the new message type (global variable msg_topic)
    delay(3000);
    canvas.fillScreen(ST77XX_BLACK);
    display.drawRGBBitmap(0, 0, canvas.getBuffer(), canvas_width, canvas_height);
  }
  else if (i == BUTTON_MINUS) {
    disp_topic_types();
    delay(3000);
    disp_btn_info();
    delay(3000);
    canvas.fillScreen(ST77XX_BLACK);
    display.drawRGBBitmap(0, 0, canvas.getBuffer(), canvas_width, canvas_height);
  }
  else {
    i = BUTTON_NONE; // Reset the button index to todo value
  }
}

void blink_a_led(padBtn &padLogic, bool all_leds = false) {
  static constexpr const char txt0[] PROGMEM = "blink_a_led(): ";
  uint8_t pad_idx = padLogic.padID;

#ifdef USE_CURRENT_STATES
#undef USE_CURRENT_STATES
#endif

#ifdef USE_CURRENT_STATES
  // Iterate over all current button states
  const auto& currentStates = pads[pad_idx]->getCurrentStates();

#ifdef MY_DEBUG
  Serial.print(txt0);
  for (const auto& [key, state] : currentStates) {
    Serial.print(key.c_str());
    Serial.print(": ");
    Serial.print(state);
    Serial.print(" | ");
  }
  Serial.println();
#endif
#else
  uint8_t state = padLogic.currentButtonState;
  std::string key = padLogic.key;
#endif

#ifdef USE_CURRENT_STATES
  for (const auto& [key, state] : currentStates) {
#endif

    if (key.empty()) {
      Serial.print(txt0);
      Serial.print(F("no key was pressed. Returning..."));
      return;
    } else {
      Serial.print(txt0);
      pads[pad_idx]->pr_PadID(); // Print pad ID

      uint8_t led_index = 0;

      // Map button name to LED index
      if      (key == "U") led_index = 1;  // UP
      else if (key == "L") led_index = 2;  // LEFT
      else if (key == "R") led_index = 3;  // RIGHT
      else if (key == "D") led_index = 4;  // DOWN
      else if (key == "M") led_index = 1;  // MINUS
      else if (key == "P") led_index = 4;  // PLUS
      else if (key == "X") led_index = 1;
      else if (key == "Y") led_index = 2;
      else if (key == "A") led_index = 3;
      else if (key == "B") led_index = 4;
      else {
        Serial.print(F("Unknown button: "));
        Serial.println(key.c_str());
        return;
        //continue;
      }

#ifndef MY_DEBUG
      Serial.print(F(", LED index: "));
      Serial.print(led_index, DEC);
#endif

      Serial.print(F(", blinking one LED for button: '"));
      Serial.print( (keyTokeyMod(key)).c_str() );
      Serial.println("'");

      // Blink logic
      pads[pad_idx]->clear_leds();
      delay(500);
      pads[pad_idx]->set_led(led_index, true);
      delay(500);
      pads[pad_idx]->clear_leds();
    }
#ifdef USE_CURRENT_STATES
  }
#endif

  // If no button was pressed and all_leds is true, blink all
  if (all_leds) {
    Serial.println(F("blinking all LEDs"));
    pads[pad_idx]->clear_leds();
    delay(500);
    pads[pad_idx]->set_leds(pads[pad_idx]->address_code());
    delay(500);
    pads[pad_idx]->clear_leds();
  }
}

std::string keyTokeyMod(std::string key) {
  std::string key_mod = keyAliases.count(key) ? keyAliases[key] : key;
  return key_mod;
}

bool ckForButtonPress() {
  static constexpr const char txt0[] PROGMEM = "ckForButtonPress(): ";
  bool retval = false;
  bool btnChanged = false;
  std::string key;
  std::string key2;
  std::string key_mod;
  uint8_t no_qwstpad = 0;
  for (uint8_t i = 0; i < CURRENT_MAX_PADS; i++) {
    bool use_qwstpad = padLogic[i].use_qwstpad;
    if (!use_qwstpad) {
      no_qwstpad++;
      if (no_qwstpad >= CURRENT_MAX_PADS) {
        Serial.print(txt0);
        pads[i]->pr_PadID();
        Serial.print(F(", no qwstpad available"));
        return retval;
      }
      continue;
    }
#ifdef MY_DEBUG
    Serial.print(txt0);
    pads[i]->pr_PadID();
    Serial.print(F(", address = 0x"));
    Serial.print(pads[i]->getAddress(), HEX);
    Serial.print(F(", use_qwstpad = "));
    Serial.println(use_qwstpad ? "true" : "false");
#endif

    pads[i]->update();  // needed for pollEvents

#ifdef READ_FROM_BUTTONS2
#undef READ_FROM_BUTTONS2
#endif

#ifdef READ_FROM_BUTTONS2
    std::map<std::string, bool> button_states = pads[i]->read_buttons2();
    for (const auto& [key2, value] : button_states) {
      if (value > 0) {
        Serial.print(txt0);
        pads[i]->pr_PadID();
        Serial.print(F(", button_states from ->read_buttons2(), key_mod: \""));
        Serial.print((keyTokeyMod(key2)).c_str());
        Serial.print(F("\", value: "));
        Serial.println(value);
      }
    }
#endif

    std::vector<ButtonEvent> keyEvent = pads[i]->pollEvents();
    size_t EventSz = keyEvent.size();
#ifdef MY_DEBUG
    verifyPadConfig(i);
#endif

#ifdef MY_DEBUG
    Serial.print(txt0);
    pads[i]->pr_PadID();
    Serial.print(F(", EventSz = "));
    Serial.println(EventSz);
#endif
    if (EventSz > 0) {
      padLogic[i].buttons_old = padLogic[i].buttons; // save current buttens state
      // Serial.print("Event count: ");
      // Serial.println(EventSz);
      for (const ButtonEvent& event : keyEvent) {
        key = event.key;
        btnChanged = pads[i]->buttonChanged(key);
#ifdef MY_DEBUG
        Serial.print(txt0);
        pads[i]->pr_PadID();
        Serial.print(F(", btnChanged = "));
        Serial.println(btnChanged ? "true" : "false");
#endif
        if (btnChanged) {
#ifdef MY_DEBUG
          Serial.print(txt0);
          pads[i]->pr_PadID();
          Serial.print(F(", button state changed for: '"));
          Serial.print( (keyTokeyMod(padLogic[i].key)).c_str() );
          Serial.print(F("', button: "));
          Serial.println(event.type == PRESSED ? "PRESSED" : "RELEASED");
#endif
          if (event.type == PRESSED) {
            unsigned long currentTime = millis();
            int8_t btn_idx = pads[i]->getFirstPressedButtonBitIndex();
#ifdef MY_DEBUG
            Serial.print(txt0);
            pads[i]->pr_PadID();
            Serial.print(F(", btn_idx = "));
            Serial.println(btn_idx);
#endif
            if (btn_idx != -1) {
              if ((currentTime - padLogic[i].lastDebounceTime) > debounceDelay) { // && padLogic.currentButtonState[btn_idx]) {
                // Only handle out of debounceDelay
                retval = true;
                padLogic[i].key = key;
                padLogic[i].btn_idx = btn_idx;
                uint16_t buttons_tmp = pads[i]->getButtonBitfield(false, false);
#ifdef MY_DEBUG
                Serial.print(txt0);
                pads[i]->pr_PadID();
                Serial.print(F(", buttons rcvd fm getButtonBitfield: "));
                printBitfield(buttons_tmp);
                Serial.println();
#endif
                padLogic[i].buttons = buttons_tmp;
                //padLogic[i].buttons = pads[i]->getButtonBitfield(false, false); // do not buttons, example: 01000 00000 00000
                padLogic[i].buttonPressed = true;
                padLogic[i].lastDebounceTime = currentTime;
                padLogic[i].lastButtonState = padLogic[i].currentButtonState; // store the "old" currentButtonState
                padLogic[i].currentButtonState = true; // set the currentButtonState
#ifdef MY_DEBUG
                Serial.print(txt0);
                Serial.println(F("going to call blink_a_led() ..."));
#endif
                blink_a_led(padLogic[i], false); // Blink an individual LED
#ifdef MY_DEBUG
                Serial.print(F("ckForButtonPress(): Button: "));
                Serial.print(btn_idx);
                Serial.print(F(" = \'"));
                Serial.print(key_mod.c_str());
                Serial.print(F("\', pressed at time: "));
                Serial.println(currentTime);
#endif
                return retval;
              }
            }
            else
              padLogic[i].btn_idx = btn_idx; // set to -1
          }
        }
      }
    }
  }
  return retval;
}

void clr_pad_stru(uint8_t PadNr) {
  padBtn empty; // Default-initialized struct
  if (PadNr >= 0 && PadNr < CURRENT_MAX_PADS) {
    padLogic[PadNr] = empty;
    padLogic[PadNr].padID = PadNr; // Restore ID
    if (PadNr == 0)
      padLogic[PadNr].address = DEFAULT_ADDRESS;
    else if (PadNr == 1)
      padLogic[PadNr].address = ALT_ADDRESS_1;
    else if (PadNr == 2)
      padLogic[PadNr].address = ALT_ADDRESS_2;
    else if (PadNr == 3)
      padLogic[PadNr].address = ALT_ADDRESS_3;
    if (pads[PadNr]->isConnected())
      padLogic[PadNr].use_qwstpad = true;
    else 
      padLogic[PadNr].use_qwstpad = false;
    padLogic[PadNr].key = "";
    padLogic[PadNr].btn_idx = -1;
    padLogic[PadNr].logic = pads[PadNr]->getLogicType();
  }
}

// Helper function for show_pad_stru() and ckForbuttonPress()
void printBitfield(uint16_t value) {
  Serial.print(F("0b"));
  for (int i = 15; i >= 1; i--) {  // Skip bit 0
    Serial.print((value >> i) & 1);
    if (i == 12 || i == 6) Serial.print(" ");  // Grouping: [15–12] [11–6] [5–1]
  }
}

const __FlashStringHelper* padLabels[] = {
  F("padID:              "),
  F("use_qwstpad:        "),
  F("address:            0x"),
  F("logic:              "),
  F("buttons:            "),
  F("buttons_old:        "),
  F("key:                \""),
  F("btn_idx:            "),
  F("buttonPressed:      "),
  F("lastButtonState:    "),
  F("currentButtonState: "),
  F("lastDebounceTime:   ")
};

void show_pad_stru(uint8_t PadNr) {
  if (PadNr >= 0 && PadNr < CURRENT_MAX_PADS) {
    pads[PadNr]->pr_PadID();
    Serial.println(F(", contents pad structure: "));
    for (uint8_t i = 0; i < 12; i++) {
      Serial.print(padLabels[i]);

      switch (i) {
        case 0: // padID
          Serial.println(padLogic[PadNr].padID);
          break;

        case 1: // use_qwstpad
          Serial.print(padLogic[PadNr].use_qwstpad);
          Serial.print(F(" = "));
          Serial.println(padLogic[PadNr].use_qwstpad ? "true" : "false");
          break;

        case 2: // address
          Serial.println(padLogic[PadNr].address, HEX);
          break;

        case 3: // logic
          Serial.print(padLogic[PadNr].logic);
          Serial.print(F(" = "));
          switch (padLogic[PadNr].logic) {
            case 0: Serial.println(F("ACTIVE_HIGH")); break;
            case 1: Serial.println(F("ACTIVE_LOW")); break;
            default: Serial.println(F("UNKNOWN")); break;
          }
          break;

        case 4: // buttons
          printBitfield(padLogic[PadNr].buttons);
          Serial.println();

          break;

        case 5: // buttons_old
          printBitfield(padLogic[PadNr].buttons_old);
          Serial.println();

          break;

        case 6: // key
          Serial.print(padLogic[PadNr].key.c_str());
          Serial.println(F("\""));
          break;

        case 7: // btn_idx
          Serial.println(padLogic[PadNr].btn_idx);
          break;

        case 8: // buttonPressed
          Serial.println(padLogic[PadNr].buttonPressed);
          break;

        case 9: // lastButtonState
          Serial.println(padLogic[PadNr].lastButtonState);
          break;

        case 10: // currentButtonState
          Serial.println(padLogic[PadNr].currentButtonState);
          break;

        case 11: // lastDebounceTime
          Serial.println(padLogic[PadNr].lastDebounceTime);
          break;
      }
    }
    Serial.println(F("------------------------------"));
  }
}

const std::vector<int> BUTTON_PINS = {1, 2, 3, 4, 5, 11, 12, 13, 14, 15};
const std::vector<int> LED_PINS = {6, 7, 9, 10};
// Pin 8 is excluded

void verifyPadConfig(uint8_t PadNr) {
    if (!pads[PadNr]) {
        Serial.println("Pad pointer is null.");
        return;
    }
    pads[PadNr]->update();
    uint8_t i2cAddr = pads[PadNr]->getAddress();  // Assuming you have this method
    int padID = pads[PadNr]->getpadIDFromAddress(i2cAddr);
    padConfig* config = pads[PadNr]->getConfig();    // Assuming this returns a pointer to PadConfig

    Serial.println("----- Pad Diagnostic -----");
    pads[PadNr]->pr_PadID();
    Serial.println();

    Serial.print("I2C Address: 0x");
    Serial.println(i2cAddr, HEX);

    Serial.print("Logic Level: ");
    Serial.println(config->logic == ACTIVE_LOW ? "ACTIVE_LOW" : "ACTIVE_HIGH");

    Serial.println("Button Pin Mapping:");
    for (const auto& [name, pin] : config->buttonPins) {
        Serial.print("  ");
        Serial.print(name.c_str());
        Serial.print(" → Pin ");
        Serial.println(pin);
    }
    Serial.println("🔘 Button States:");
    for (const auto& [name, pin] : config->buttonPins) {
        bool rawState = pads[PadNr]->readRawPin(pin);  // Assuming this reads the digital pin directly
        bool interpretedState = pads[PadNr]->isButtonPressed(name); // Presuming this applies logic level

        Serial.print("  ");
        Serial.print(name.c_str());
        Serial.print(": Raw=");
        Serial.print(rawState ? "HIGH" : "LOW");
        Serial.print(", Interpreted=");
        Serial.println(interpretedState ? "PRESSED" : "RELEASED");
    }
    Serial.println("💡 LED States:");
    for (int pin : LED_PINS) {
        bool state = pads[PadNr]->readRawPin(pin);
        Serial.print("  Pin ");
        Serial.print(pin);
        Serial.print(": ");
        Serial.println(state ? "OFF" : "ON");
    }
    Serial.println("--------------------------\n");
}

void backlite_toggle() {
  if (backLite) {
      backLite = false;
      digitalWrite(TFT_BACKLITE, LOW); // Switch off
  }
  else {
      backLite = true;
      digitalWrite(TFT_BACKLITE, HIGH); // Switch off
  }
}

// ------------- IF USE KEEP-ALIVE SYSTEM and LAST-WILL --------------------------

bool mqtt_connect_fail()
{
  bool stop = false;
  uint8_t mqtt_err_code = mqttClient.connectError();

  switch (mqtt_err_code) {
    case -2:  // refused
    {
      Serial.println(F("❌ MQTT Connection refused."));
      stop = true;
      break;
    }
    case -1:  // timeout
    {
      Serial.println(F("❌ MQTT Connection timed-out."));
      stop = true;
      break;
    }
    case 3:
    {
      Serial.println(F("❌ MQTT Server not available."));
      stop = true;
      break;
    }
    case 5: // = Connection refused. Client is not authorized
    {
      Serial.println(F("❌ MQTT Client not authorized."));
      stop = true;
      break;
    }
    default:
    {
      stop = true;
      break;
    }
  }
  return stop;
}

const char* will_topic = "will";
const char* will_payload = "offline";
uint8_t qos = 1;
bool retain = true;

void setupMQTTClient() {
  // Set client ID, credentials, etc.
  mqttClient.setId(MQTT_CLIENT_ID);

  /*
  // Optional keepalive interval
  mqttClient.setKeepAliveInterval(90); // was: 60

  // Begin Will message
  if (mqttClient.beginWill(will_topic, strlen(will_payload), retain, qos)) {
    mqttClient.print(will_payload); // Write the payload
    if(!mqttClient.endWill())
      Serial.print(F("❌ failed call to mqttClient.endWill()"));  // Finish Will message
  } else {
    Serial.println("⚠️ Failed to begin Will message!");
  }
  */
  // Now connect
  Serial.println("🔌 Connecting to MQTT...");
  if (mqttClient.connect(broker, 1883)) {
    Serial.println("✅ Connected to MQTT broker");
  } else {
    bool dummy = mqtt_connect_fail();
  }
}

// ------------- END OF - IF USE KEEP-ALIVE SYSTEM and LAST-WILL --------------------------

void setup() 
{
  static constexpr const char txt0[] PROGMEM = "setup(): ";
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

  pinMode(TFT_BACKLITE, OUTPUT);

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
    Serial.print(F("Version: 0x"));
    Serial.println(lc_bat.getICversion(), HEX);
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
  // TB.theWire->setClock(100000);
  TB.printI2CBusScan();

  Wire.begin();

  Wire.setClock(100000); // Optional: slow down I2C

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
    do_reset(true);
  }

  if (!handle_bme280())
  {
    Serial.println("❌ Initiating BME280 failed");
    Serial.println("Check wiring. Going into an endless loop...");
    while (true)
      delay(5000);
  }

#if defined(SECONDARY_I2C_PORT)
  //Wire1.begin(SDA1, SCL1, 100000);
  Serial.print("Secondary I2C port (Wire1) ");
  TB.theWire = SECONDARY_I2C_PORT;
  TB.theWire->setPins(SDA1, SCL1);
  TB.printI2CBusScan();
  TB.theWire->begin();
#endif

  Wire1.begin(SDA1, SCL1, 100000);

  pads[0] = new QwstPad(SECONDARY_I2C_PORT, DEFAULT_ADDRESS, true);
  pads[1] = new QwstPad(SECONDARY_I2C_PORT, ALT_ADDRESS_1, true);
  //pads[2] = new QwstPad(SECONDARY_I2C_PORT, ALT_ADDRESS_2, true);
  //pads[3] = new QwstPad(SECONDARY_I2C_PORT, ALT_ADDRESS_3, true);

  uint16_t pad1address;
  Serial.print(F("Maximum number of QwSTPads: "));
  Serial.println(CURRENT_MAX_PADS);
  for (int i = 0; i < CURRENT_MAX_PADS; ++i) {
    bool isConnected = pads[i]->isConnected();
    uint16_t pAddress = pads[i]->getAddress();
    pads[i]->pr_PadID();
    Serial.print(F(", I2C address: 0x"));
    Serial.print(pads[i]->getAddress(), HEX);
    Serial.print(F(", padID: "));
    padLogic[i].padID = pads[i]->getpadIDFromAddress(pads[i]->getAddress()); //+1; // adjust for human readable 1...4
    Serial.print(padLogic[i].padID);
    padLogic[i].address = pAddress;
    if (isConnected) {  
      if (i == 0) {
        pad1address == pAddress;
        Serial.println(F(". Pad is connected"));
        padLogic[i].address = pAddress;
        padLogic[i].use_qwstpad = true;
        padLogic[i].logic = pads[i]->getLogicType();
        NUM_PADS++;
      }
      else if (i > 0) {
        // It happened that a pad with padID > 0 had the same address as the one with padID 0.
        // so we introduced pad1address to compare
        if (pad1address != pAddress) {
          Serial.println(F(". Pad is connected"));
          padLogic[i].address = pAddress;
          padLogic[i].use_qwstpad = true;
          padLogic[i].logic = pads[i]->getLogicType();
          NUM_PADS++;
        }
        else {
          padLogic[i].address = 0;
          padLogic[i].use_qwstpad = false;
          padLogic[i].logic = -1;
        }
      }
    }
    else {
      Serial.println(F(". Pad is not connected"));
      padLogic[i].address = 0;
      padLogic[i].use_qwstpad = false;
    }
  }
  Serial.print("Number of connected pads: ");
  Serial.println(NUM_PADS);

  // Initialize pads
  for (int j = 0; j < NUM_PADS; ++j) {
    if (padLogic[j].use_qwstpad) {
      pads[j]->begin();
#ifdef MY_DEBUG
      Serial.print(F("Pad "));
      Serial.print(j+1);
      Serial.print(F(" initialized with address: 0x"));
      Serial.println(pads[j]->getAddress(), HEX);
#endif
    }
  }
  for (uint8_t i = 0; i < NUM_PADS; i++) {
      Serial.print(txt0);
      pads[i]->pr_PadID();
      Serial.print(F(", use_qwstpad = "));
      Serial.println(padLogic[i].use_qwstpad ? "true" : "false");
  }
#ifdef MY_DEBUG
  pads[0]->printAllPadConfigs(); // Any pad instance can call it
#endif
  bool qwst_debug_test = false;
  
  if (qwst_debug_test) {
    // Qwstpad debugging features (from MS Copilot)
    //pads[1]->debugPrintStates()();
    uint16_t buttons;
    for (int j = 0; j < CURRENT_MAX_PADS; ++j) {
      if (padLogic[j].use_qwstpad) {
        /*
        pads[j]->update();
        pads[j]->pr_PadID();
        Serial.print(F(", LED states: "));
        Serial.println(pads[j]->get_led_states(), BIN);
        pads[j]->pr_PadID();
        Serial.print(F(", BUTTON states: "));
        buttons = pads[j]->getButtonBitfield(false, false); // do not print the bitfield and do not print it fancy
        printBitfield(buttons);
        Serial.println();
        */
        verifyPadConfig(j);
      }
    }
  }

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
      bool use_mqtt_keepalive_system = false;

      if (use_mqtt_keepalive_system) {
        setupMQTTClient();
      }
      else {
        bool mqtt_connected = false;
        bool show_broker_ip = false;

        mqttClient.setId(MQTT_CLIENT_ID);  // Set the client ID to identify your device
        Serial.print(F("MQTT client ID: "));
        serialPrintf(PSTR("\"%s\"\n"), MQTT_CLIENT_ID);

        for (uint8_t i=0; i < 10; i++)
        {
          if (mqttClient.connect(broker, port))
          {
            mqtt_connected = true;
            Serial.print(F("✅ MQTT You're connected to "));
            serialPrintf(PSTR("%s broker %s:%s\n"), (use_broker_local) ? "local" : "remote", (show_broker_ip) ? broker : "___.___._.___", String(port).c_str());
            // set the message receive callback
            mqttClient.onMessage(onMqttMessage);
            mqttClient.subscribe(topic1);
            mqttClient.subscribe(topic2);
            Serial.print(txt0);
            Serial.print(F("subscribed to topic(s): "));
            serialPrintf(PSTR("%s, %s\n"), topic1, topic2);
            break;
          } else 
          {
            if (mqtt_connect_fail()) {
              //serialPrintf(PSTR("❌ MQTT connection to broker failed! Error code = %s\n"), String(mqtt_err_code).c_str() );        
              delay(1000);
            }
          }
        }
        if (!mqtt_connected)
        {
          Serial.print(F("❌ MQTT Unable to connect to broker in LAN. Going into infinite loop..."));
          while (true)
            delay(5000);
        }

      }
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

  //if (!isItDisplayBedtime())
  disp_intro(true);
  delay(3000);
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
  serialPrintf(PSTR("%sMQTT message send interval = %d minute%s\n"), 
          txt0, interval_in_mins, interval_in_mins <= 1 ? "" : "s");
  bool dummy = false;
  bool btn_pressed = false;
  bool send_mqtt_msg = false;
  unsigned long currentTime;
  
  unsigned long previousMillis = 0;
  const unsigned long interval = 3000;
  int screenState = 0; // 0 = info, 1 = sensor

  #ifdef USE_QNH
  int qnh_fetch_cnt = 0;
  // int qnh_fetch_limit = 5; // moved to secrets.h - see global variable
  unsigned long lastQNHUpdate = 0;
  const unsigned long qnhInterval = 12 * 3600000; // 12 hours in milliseconds
#endif

  while (true)
  {
  #ifdef USE_QNH
    if (start) {
      Serial.print(txt0);
      Serial.print(F("Get METAR: "));
      Serial.println(use_qnh ? "OFF" : "ON");
    }
#endif
    btn_pressed = false;
    send_mqtt_msg = false;
    clr_buttons(0, true); // Clear all button press info
    /*
    // If the gamepad, for one or another reason is not connected
    for (int i = 0; i < CURRENT_MAX_PADS; ++i) {
      if (!padLogic[i].use_qwstpad) {
        bool isConnected = pads[i]->isConnected();
        if (isConnected)  // gamepad QT found, connect to it
          padLogic[i].use_qwstpad = true;
      }
    }
    */
    if (ckForButtonPress()) { // Check for button presses and handle them
      for (int i = 0; i < CURRENT_MAX_PADS; ++i) {
        if (padLogic[i].use_qwstpad) {
          btn_pressed = padLogic[i].buttonPressed;
          if (btn_pressed) {
#ifndef MY_DEBUG
            Serial.print(txt0);
            pads[i]->pr_PadID();            
            Serial.print(F(", button "));
            Serial.print( (keyTokeyMod(padLogic[i].key)).c_str() );
            Serial.print(F(", btn_idx = "));
            Serial.print(padLogic[i].btn_idx);
            Serial.println(F(", pressed. Going to handle it..."));
#endif
            handleButtonPress(static_cast<Button>(padLogic[i].btn_idx));
          }
          //if (i == CURRENT_MAX_PADS-1 && btn_pressed)
          if (btn_pressed)
            break;
        }
      }
    }
    // call poll() regularly to allow the library to send MQTT keep alive which
    // avoids being disconnected by the broker
    mqttClient.poll();

#ifdef USE_QNH
    if (use_qnh) {
      if (qnh_fetch_cnt < qnh_fetch_limit) {
        if (start || millis() - lastQNHUpdate > qnhInterval) {
          qnh = fetchQNH(); // qnh is a global variable
          lastQNHUpdate = millis();
          Serial.print(txt0);
          Serial.print("Updated QNH: ");
          Serial.print(qnh);
          Serial.println(F(" mB"));
          qnh_fetch_cnt++;
          // Update display or log it
        }
      } else {
        Serial.print(txt0);
        Serial.println(F("fetchQNH count limit reached!"));
      }
    }
#endif
    unsigned long ntp_curr_t = millis();
    ntp_elapsed_t = ntp_curr_t - ntp_start_t;
    if (start || ntp_curr_t - ntp_start_t >= ntp_interval_t)
    {
      ntp_start_t = ntp_curr_t;
      rtc_sync();
//#ifdef MY_DEBUG
      printFreeMemory();
//#endif 
    }

    if (!ck_timeIsValid())
      rtc_sync(); // Sync the RTC with the NTP server if the time is not valid

    mqtt_curr_t = millis();
    mqtt_elapsed_t = mqtt_curr_t - mqtt_start_t;

    if (start || btn_pressed ||  mqtt_elapsed_t >= mqtt_interval_t) 
    { 
      start = false;
      send_mqtt_msg = true;
      
      // save the last time a message was sent
      mqtt_start_t = mqtt_curr_t;

      uint8_t try_cnt = 0;
      uint8_t try_cnt_max = 10;
#ifdef USE_DEBUG
      Serial.print(txt0);
#endif
      for (int i = 0; i < CURRENT_MAX_PADS; ++i) {
        if (padLogic[i].use_qwstpad) {
#ifdef USE_DEBUG
          pads[i]->pr_PadID();
          Serial.print(F(", button pressed = "));
          Serial.print(btn_pressed);
          if (i < CURRENT_MAX_PADS-1)
            Serial.print(F(", "));
          else
            Serial.println();
#endif
          if (send_mqtt_msg) {
            bool send_result = send_msg();
            while (!send_result) {
              send_result = send_msg();
              try_cnt++;
              if (try_cnt >= try_cnt_max)
                break;
              delay(50);
            }
            if (send_result)
              mqttMsgID_old = mqttMsgID; // copy
          }

#ifdef USE_DEBUG
            Serial.print(txt0);
            pads[i]->pr_PadID();
            Serial.println(F(", clearing the padLogic stucture"));
#endif
            clr_pad_stru(i);  // Clear the structure from this Pad
          
#ifdef USE_DEBUG
            Serial.print(txt0);
            pads[i]->pr_PadID();
            Serial.println(F(", padLogic stucture after clearing"));
            show_pad_stru(i);
#endif
            // After the other type of messages have been sent
            // reset to the default message type
            myMsgType = tpah_sensor;
            composeMsgTopic(myMsgType); // Prepare the MQTT topic based on the new message type (global variable msg_topic)
          }
        }
      }
    //}
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
        if (!ckForButtonPress()) {  // Check and handle gamepad keypresses first
          // If the display is not asleep, show a goodnight message
          disp_goodnight();
          delay(5000); // Show the text for 5 seconds
          // Clear the display
          canvas.fillScreen(ST77XX_BLACK);
          display.drawRGBBitmap(0, 0, canvas.getBuffer(), canvas_width, canvas_height);
          if (backLite)
            backlite_toggle(); // switch off the TFT backLite
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
        if (!backLite)
          backlite_toggle(); // switch on the backLite
        digitalWrite(TFT_I2C_POWER, HIGH);
        if (!ckForButtonPress()) {  // Check and handle gamepad keypresses first
          // disp_goodmorning();
          greeting_handler();
          delay(5000); // Show the text for 5 seconds
          // Clear the display
          canvas.fillScreen(ST77XX_BLACK);
          display.drawRGBBitmap(0, 0, canvas.getBuffer(), canvas_width, canvas_height);
          displayIsAsleep = false; // reset the displayIsAsleep flag
        }
      }
      if (!ckForButtonPress()) {
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
      // Clear status
      // clr_buttons(i);
    }
  }
}

