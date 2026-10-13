// Defines for sketch
#define SECRET_SSID "<Your WiFi SSID>"
#define SECRET_PASS "<Your WiFi PASSWORD>"

#define REGION_EUROPE  // Choose the one you need, or create your own
// #define REGION_USA

#ifdef REGION_EUROPE // Europe/Lisbon
  #define SECRET_TZ_DST_ID "WEST"
  #define SECRET_TIMEZONE_DST_OFFSET "1"
  #define SECRET_TZ_STD_ID "WET"
  #define SECRET_TIMEZONE_STD_OFFSET "0"
#elif defined(REGION_USA)  // America/New_York
  #define SECRET_TZ_DST_ID "EDT"
  #define SECRET_TIMEZONE_DST_OFFSET "-4"
  #define SECRET_TZ_STD_ID "EST"
  #define SECRET_TIMEZONE_STD_OFFSET "-5"
#endif

#define SECRET_USE_BROKER_LOCAL "1"  // We usa a local MQTT broker
#define SECRET_NTP_SERVER1 "1.pt.pool.ntp.org" // Your favorite NTP server
#define SECRET_MQTT_BROKER "5.196.78.28" // test.mosquitto.org"
#define SECRET_MQTT_BROKER_LOCAL1 "192.168._.__"  // if you have a local mosquitto broker app on (desktop) PC ___
#define SECRET_MQTT_BROKER_LOCAL2 "192.168._.___"  // if you have a local mosquitto broker app on a Raspberry Pi CM5
#define SECRET_MQTT_PORT "1883"
#define SECRET_MQTT_TOPIC_PREFIX_SENSORS "sensors"
#define SECRET_MQTT_TOPIC_PREFIX_LIGHTS "lights"
#define SECRET_MQTT_TOPIC_PREFIX_TODO "todo"
#define SECRET_MQTT_PUBLISHER "Feath"
#define SECRET_MQTT_CLIENT_ID "Adafruit_Feather_ESP32S3TFT"
#define SECRET_MQTT_SYS_TOPIC1 "$SYS/broker/clients/connected"
#define SECRET_MQTT_SYS_TOPIC2 "$SYS/broker/clients/disconnected"
#define SECRET_MQTT_TOPIC_SUFFIX_SENSORS "ambient"
#define SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_TOGGLE "toggle"
#define SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_COLOR_DECREASE "color_dec"
#define SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_COLOR_INCREASE "color_inc"
#define SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_DCLR_DECREASE "dclr_dec"
#define SECRET_MQTT_TOPIC_SUFFIX_LIGHTS_DCLR_INCREASE "dclr_inc"
#define SECRET_MQTT_TOPIC_SUFFIX_METAR "metar"
#define SECRET_MQTT_TOPIC_SUFFIX_TODO "todo"
#define SECRET_DISPLAY_AWAKETIME "7"
#define SECRET_DISPLAY_SLEEPTIME "23"
#define SECRET_METAR_TAF_API_KEY "<Your metar-taf.com API KEY>"
#define SECRET_METAR_FETCH_LIMIT "5"  // Only if you need to limit your "expenses" of bought credtis

