# udp_rx.py
# by Paulus Schulinck (Github handle: @PaulskPt
# date: 2025-09-17
# License: MIT
# This MicroPython script is to be used with any UDP listener device in the LAN
# where is another device, for example a Pimoroni Pico LiPo 2XL W, that transmits its print() statements as UDP packets
#
import socket

udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.bind(('', 5005))

while True:
    data, addr = udp.recvfrom(512)  # Reduced buffer size
    if isinstance(data, bytes):
      dataStr = data.decode('utf-8')
      print(dataStr)
    else:
      print(f"[RAW] {repr(data)} from {addr}")
