from lib.sdcard import SDCard
from machine import Pin, SPI
import os, sys

PIN_SD_SCK  = Pin.board.GP34
PIN_SD_MOSI = Pin.board.GP35
PIN_SD_MISO = Pin.board.GP36
PIN_SD_CS   = Pin.board.GP39

# Setup for SD Card
sd_spi = SPI(0,
            sck=Pin(PIN_SD_SCK,   Pin.OUT),
            mosi=Pin(PIN_SD_MOSI, Pin.OUT),
            miso=Pin(PIN_SD_MISO, Pin.OUT))

sd = SDCard(sd_spi, Pin(PIN_SD_CS))

try:
    os.mount(sd, "/sd")
    print("SDCard mounted")
    #return True
except OSError as exc:
    print("mounting SDCard failed")
    sys.print_exception(exc)
    #return False


