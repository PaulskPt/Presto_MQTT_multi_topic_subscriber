""" Micropython classes for MQTT messages """
# mqtt_entities.py 
# Date: 2025-08-19 
# Created by Microsoft Copilot on defined request by
# Paulus Schulinck (Github handle: @PaulskPt)
#
# File to be used with micropython script:
# - mqtt_presto_v5.py 
#
# This file contains one main class:
# - MQTTEntity;
# and five subclassess:
# - SensorTPAH;
# - LightsToggle;
# - AmbientColors;
# - DisplayColors;
# - Metar

class MQTTEntity:
    def __init__(self, topic="", topicIdx=0, head=None, payload=None):
        self._topic = topic
        self._topicIdx = topicIdx
        self._head = head if head else {}
        self._payload = payload if payload else {}

    @property
    def topic(self):
        return self._topic
    
    @topic.setter
    def topic(self, value):
        if isinstance(value, str) and value:
            self._topic = value
    
    @property
    def topicIdx(self):
        return self._topicIdx
    
    @topicIdx.setter
    def topicIdx(self, value):
        if isinstance(value, int) and value:
            self._topicIdx = value

    # Example sensor_obj.head : {'ow': 'Feath', 'de': 'Lab','dc': 'BME280', 'sc': 'meas', 'vt': 'f', 't': 1755703794}
    @property
    def head(self):
        return self._head

    @head.setter
    def head(self, value):
        if isinstance(value, dict) and value:
            self._head = value

    @property
    def payload(self):
        return self._payload

    @payload.setter
    def payload(self, value):
        if isinstance(value, dict) and value:
            self._payload = value

# Example sensor_obj.payload: {'reads': {'t': {'u': 'C', 'mx': 50, 'mn': -10, 'v': 31.7},      # TEMPERATURE
#                                        'p': {'u': 'mB', 'mx': 1200, 'mn': 800, 'v': 1003.9}, # PRESSURE
#                                        'a': {'u': 'm', 'mx': 3000, 'mn': 0, 'v': 102.8},     # ALTITUDE
#                                        'h': {'u': '%', 'mx': 100, 'mn': 0, 'v': 51.5}        # HUMIDITY
#                                       }
#                             }
#
class SensorTPAH(MQTTEntity):
    def __init__(self, topic="sensors/Feath/ambient"):
        super().__init__(topic)
        self._temperature = None
        
    @property
    def temperature(self):
        return self._temperature

    @temperature.setter
    def temperature(self, value):
        if isinstance(value, float):
            self._temperature = value
#                                                      ⬇️
# Example: {'toggle': {'u': 'i', 'mx': 1, 'mn': 0, 'v': 1}}  # Swtich ambient LED lights ON
# Example: {'toggle': {'u': 'i', 'mx': 1, 'mn': 0, 'v': 0}}  # Switch ambient LED lights OFF
#                                                      ⬆️
class LightsToggle(MQTTEntity):
    def __init__(self, topic="lights/Feath/toggle"):
        super().__init__(topic)
        self._lights_toggle = False
        self._lights_toggle_old = False
        self._lights_toggle_ts = 0

    @property
    def lights_toggle(self):
        return self._lights_toggle

    @lights_toggle.setter
    def lights_toggle(self, value: int):
        if isinstance(value, bool):
            self._lights_toggle_old = self._lights_toggle
            self._lights_toggle = value       

# Example: {'colorInc': {'u': 'i', 'mx': 9, 'mn': 0, 'v': 3}}
# Example: {'colorDec': {'u': 'i', 'mx': 9, 'mn': 0, 'v': 2}}
class AmbientColors(MQTTEntity):
    def __init__(self, topic="lights/Feath/clr_inc"):
        super().__init__(topic)
        self._amb_color_current = 0
        self._amb_color_old = 0
        self._amb_color_changed = False

    def clear_amb_colors(self):
        self._amb_color_current = 0
        self._amb_color_old = 0
        self._amb_color_changed = False
        
    @property
    def amb_color(self) -> int:
        return self._amb_color_current

    @amb_color.setter
    def amb_color(self, value: int):
        if isinstance(value, int):
            self._amb_color_old = self._amb_color_current
            self._amb_color_current = value
    
    @property
    def amb_color_changed(self) -> bool:
        return self._amb_color_changed
    
    @amb_color_changed.setter
    def amb_color_changed(self, value: bool):
        if isinstance(value, bool):
            self._amb_color_changed = value

# Example: {'dclrInc': {'u': 'i', 'mx': 11, 'mn': 1, 'v': 10}}
# Example: {'dclrDec': {'u': 'i', 'mx': 11, 'mn': 1, 'v': 9}}
class DisplayColors(MQTTEntity):
    def __init__(self, topic="lights/Feath/dclr_inc"):
        super().__init__(topic)
        self._disp_color_current = 0
        self._disp_color_old = 0
        self._disp_color_changed = False
        self._disp_color_index = 0

    def clear_disp_colors(self):
        self._disp_color_current = 0
        self._disp_color_old = 0
        self._disp_color_changed = False
        
    @property
    def disp_color(self) -> int:
        return self._disp_color_current

    @disp_color.setter
    def disp_color(self, value: int):
        if isinstance(value, int):
            self._disp_color_old = self._disp_color_current
            self._disp_color_current = value
            
    @property
    def disp_color_changed(self)-> bool:
        return self._disp_color_changed
    
    @disp_color_changed.setter
    def disp_color_changed(self, value: bool):
        if isinstance(value, bool):
            self._disp_color_changed = value
            
    @property
    def disp_color_index(self) -> int:
        return self._disp_color_index
    
    @disp_color_index.setter
    def disp_color_index(self, value: int):
        if isinstance(value, int):
            self._disp_color_index = value

# Example: {"raw": "METAR LPPT 291930Z 34012KT CAVOK 30/10 Q1014"}
class Metar(MQTTEntity):
    def __init__(self, topic="weater/metar"):
        super().__init__(topic)
        self._metar = None
        
    @property
    def metar(self) -> dict:
        return self._metar

    @metar.setter
    def metar(self, value: dict):
        if isinstance(value, dict):
            self._metar = value

         