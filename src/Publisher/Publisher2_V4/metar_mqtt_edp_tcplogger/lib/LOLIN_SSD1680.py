# 2025-09-14 10h44 utc+1
# Translated from the LOLIN_EPD Arduino library.
# Translations by MS Copilot.
# Trying to use in MicroPython with a Pimoroni Pico LiPo 2XL W board and a Lolin EPD 2.13" display.
#
import time

my_debug = False

# Color definitions
EPD_BLACK = 'BLACK'
EPD_WHITE = 'WHITE'
EPD_RED = 'RED'
EPD_INVERSE = 'INVERSE'

class SSD1680:
    def __init__(self, width, height, spi, dc, rst, cs, busy=None):
        self.width = width
        self.height = height
        self.spi = spi
        self.dc = dc
        self.rst = rst
        self.cs = cs
        self.busy = busy
        self._height_8bit = (height + 7) & ~7

        self._buffer_bw = bytearray(self.width * self._height_8bit // 8)
        self._buffer_red = bytearray(self.width * self._height_8bit // 8)

    def begin(self, reset=True):
        if reset:
            self.rst.value(0)
            time.sleep_ms(200)
            self.rst.value(1)
            time.sleep_ms(200)
        self.read_busy()
        # Send init commands here
        
    def send_command(self, command):
        self.dc.value(0)
        self.cs.value(0)
        self.spi.write(bytes([command]))
        self.cs.value(1)

    def send_data(self, data):
        self.dc.value(1)
        self.cs.value(0)
        self.spi.write(bytes([data]))
        self.cs.value(1)
        
    def set_rotation(self, rotation):
        self.rotation = rotation  # 0, 90, 180, 270

    def draw_pixel(self, x, y, color):
        if self.rotation == 90:
            x, y = y, self.width - x - 1
        elif self.rotation == 180:
            x = self.width - x - 1
            y = self.height - y - 1
        elif self.rotation == 270:
            x, y = self.height - y - 1, x
        # ... rest of draw_pixel logic ...

        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return

        addr = (x * self._height_8bit + y) // 8
        bit = 1 << (7 - y % 8)

        if color == EPD_RED:
            self._buffer_red[addr] |= bit
        elif color == EPD_WHITE:
            self._buffer_bw[addr] |= bit
            self._buffer_red[addr] &= ~bit
        elif color == EPD_BLACK:
            self._buffer_bw[addr] &= ~bit
            self._buffer_red[addr] &= ~bit
        elif color == EPD_INVERSE:
            self._buffer_bw[addr] ^= bit
            
   
    def display(self):
        self.send_command(0x24)  # Write BW RAM
        for b in self._buffer_bw:
            self.send_data(b)

        self.send_command(0x26)  # Write RED RAM
        for r in self._buffer_red:
            self.send_data(r)

        self.update()


    def update(self):
        self.send_command(0x22)  # Display Update Control
        self.send_data(0xF7)
        self.send_command(0x20)  # Activate Display Update
        self.read_busy()


    # bool param added by @Paulskpt
    # if clr_to_white is True then buffer cleared with White color
    def clear_buffer(self, clr_bw_to_white: bool = False):
        fill_val = 0xFF if clr_bw_to_white else 0x00
        if my_debug:
            print(f"LOLIN_SSD1680.clear_buffer(): param clr_bw_to_write = {clr_bw_to_white}, fill_val = 0x{fill_val:02x}")
        for i in range(len(self._buffer_bw)):
            self._buffer_bw[i] = fill_val
        for i in range(len(self._buffer_red)):
            self._buffer_red[i] = 0x00 # No red yet
        if my_debug:
            print(f"self._buffer_bw[:10] = {self._buffer_bw[:10]}")
    def clear_display(self):
        self.clear_buffer()
        self.display()
        time.sleep_ms(100)
        self.display()


    def deep_sleep(self):
        self.send_command(0x10)  # Enter deep sleep
        self.send_data(0x01)
        time.sleep_ms(100)


    def fill_buffer(self, black_img, red_img):
        self._buffer_bw[:] = black_img
        self._buffer_red[:] = red_img

    def read_busy(self):
        while self.busy and self.busy.value() == 1:
            time.sleep_ms(100)
