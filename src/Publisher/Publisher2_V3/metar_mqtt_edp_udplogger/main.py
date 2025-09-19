# main.py

import os

fn = "metar_mqtt_epd_udplogger_v2.py"

if fn in os.listdir():
    try:
        import metar_mqtt_epd_udplogger_v2
        metar_mqtt_epd_udplogger_v2.go_epd()
    except Exception as e:
        print(f"⚠️  Error \"{e}\" while importing and running \"{fn}\"")
else:
    print(f"⚠️  file \"{fn}\" not found")

    
