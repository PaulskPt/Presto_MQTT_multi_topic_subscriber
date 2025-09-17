# main.py

import os

fn = "metar_mqtt_epd_and_udp_logger.py"

if fn in os.listdir():
    try:
        import metar_mqtt_epd_and_udp_logger
        metar_mqtt_epd.go_epd()
    except Exception as e:
        print(f"⚠️  Error \"{e}\" while importing and running \"{fn}\"")
else:
    print(f"⚠️  file \"{fn}\" not found")

    
