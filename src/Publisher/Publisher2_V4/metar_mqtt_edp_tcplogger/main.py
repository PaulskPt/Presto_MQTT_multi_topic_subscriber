# main.py

import os

TAG = "main.py: "

do_tcp = True

if do_tcp:

    fn = "metar_mqtt_epd_tcplogger_v1.py"

    if fn in os.listdir():
        try:
            import metar_mqtt_epd_tcplogger_v1
            metar_mqtt_epd_tcplogger_v1.go_epd()
        except Exception as e:
            print(TAG+f"⚠️  Error \"{e}\" while importing and running \"{fn}\"")
    else:
        print(TAG+f"⚠️  file \"{fn}\" not found") 
else:
    fn = "metar_mqtt_epd_udplogger_v2.py"

    if fn in os.listdir():
        try:
            import metar_mqtt_epd_udplogger_v2
            metar_mqtt_epd_udplogger_v2.go_epd()
        except Exception as e:
            print(TAG+f"⚠️  Error \"{e}\" while importing and running \"{fn}\"")
    else:
        print(TAG+f"⚠️  file \"{fn}\" not found")
    
