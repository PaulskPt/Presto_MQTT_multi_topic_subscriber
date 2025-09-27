# tcp_logger_v1.py
# Date: 2025-09-24
# by Paulus Schulinck (@PaulskPt)
# with assistance of Microsoft Copilot
# TCP version of UDPLogger with multi-target support

import sys
import socket
import time
import gc

my_debug = False

RPI4B = '192.168.1.125'

device_timeouts = {
    "192.168.1.69":  3.0, # Pico Plus 2W
    "192.168.1.81":  1.0, # RPICO32
    "192.168.1.125": 1.0  # RPi4B
}

class TCPLogger:
    def __init__(self,
                 port: int = 12345,
                 targets=RPI4B,
                 use_tcp_logger: bool = True) -> None:
        
        self.port = port
        self.use_tcp_logger = use_tcp_logger
        self.TAG_CLS = "TCPLogger"

        # Normalize targets to a list
        if isinstance(targets, str):
            self.targets = [targets]
        elif isinstance(targets, list):
            self.targets = targets
        else:
            self.targets = []

    def write(self, msg):
        TAG = ".write(): "
        try_cnt_max = 3

        if not self.targets or not isinstance(self.port, int) or not (0 < self.port < 65536):
            sys.stdout.write(self.TAG_CLS + TAG + "Invalid targets or port. Skipping TCP send.\n")
            sys.stdout.write(f"{msg}\n")
            return
        
        if not msg or (isinstance(msg, str) and len(msg.strip()) == 0):
            return

        if isinstance(msg, int):
            msg = str(msg)

        if isinstance(msg, str): # and len(msg.strip('\r\n')) > 0:
            for ip in self.targets:
                if not self.ping(ip):  # Check reachability of the target
                    sys.stdout.write(self.TAG_CLS + TAG + "target not reachable\n")
                    continue # return # do it silently. No serial output
                try_cnt = 0
                sent = False
                while not sent and try_cnt < try_cnt_max:
                    try:
                        if self.use_tcp_logger:
                            ack = None
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            #sock.settimeout(1.0) # Guardrail: short timeout
                            sock.settimeout(device_timeouts.get(ip, 2.0))  # default fallback
                            sock.connect((ip, self.port))
                            # sys.stdout.write(self.TAG_CLS + TAG + f"[tcp_logger] Sending to {ip}: {repr(msg)}\n")
                            sock.send(msg.encode()) # 'utf-8'))
                            sock.close()
                            sent = True
                            # break
                        else:
                            break
                    except OSError as exc:
                        tOS = "OSerror: "
                        tC  = "Connection "
                        errno = exc.args[0] if len(exc.args) > 0 else -1
                        if errno == 12:
                            sys.stdout.write(self.TAG_CLS + TAG + f"TCP send error to {ip}: memory error: {exc}\n")
                            gc.collect()
                            continue
                        if errno == 110:
                            sys.stdout.write(self.TAG_CLS + TAG + tOS + f"Timeout occurred.\n")
                        elif errno == 101:
                            sys.stdout.write(self.TAG_CLS + TAG + tOS + f"Network unreachable for {ip}.\n")
                        elif errno == 113:
                            sys.stdout.write(self.TAG_CLS + TAG + tOS + f"No route to host {ip}.\n")
                        elif errno == 111:
                            sys.stdout.write(self.TAG_CLS + TAG + tOS + tC + f"refused by {ip}.\n")
                        elif errno == 104:
                            sys.stdout.write(self.TAG_CLS + TAG + tOS + tC + f"reset by {ip}.\n")
                        else:
                            sys.stdout.write(self.TAG_CLS + TAG + f"TCP send error to {ip}: {exc}\n")
                        time.sleep(0.1)
                    except Exception as e:
                        sys.stdout.write(self.TAG_CLS + TAG + f"Non-network exception for {ip}: {e}\n")
                    try_cnt += 1
                    if try_cnt >= try_cnt_max:
                        sys.stdout.write(self.TAG_CLS + TAG + f"TCP send to {ip} failed after {try_cnt} attempts.\n")
            sys.stdout.write(f"{msg}\n")
            
    def ping(self, ip):
        TAG = ".ping(): "
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect((ip, self.port))
            sock.close()
            return True
        except:
            return False

    def flush(self): pass
