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

RPI4B = {'0' : {'name': 'RPI4B', 'ip' : '192.168.1.125', 'timeout': '1.0'}} # default dict

targets_timeouts = []

class TCPLogger:
    def __init__(self,
                 port: int = 12345,
                 targets=RPI4B,
                 use_tcp_logger: bool = True) -> None:

        self.port = port
        self.use_tcp_logger = use_tcp_logger
        self.TAG_CLS = "TCPLogger"
        TAG = ".__init__(): "
        if my_debug:
            sys.stdout.write(self.TAG_CLS + TAG + f"param targets = {targets}\n")
    
        # Normalize targets to a list
        if isinstance(targets, dict):
            self.targets = targets
            if my_debug:
                sys.stdout.write(self.TAG_CLS + TAG + f"self.targets = {self.targets}\n")
        else:
            sys.stdout.write(self.TAG_CLS + TAG + "parameter targets not of type dict.\n")
            raise RuntimeError
        
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
            le = len(self.targets)
            if my_debug:
                sys.stdout.write(self.TAG_CLS + TAG + f"len(self.targets) = {len(self.targets)}")
            for i in range(le):
                n = str(i)
                nm = self.targets[n]['name']
                ip = self.targets[n]['ip']
                to = int(float(self.targets[n]['timeout']))
                if my_debug:
                    sys.stdout.write(self.TAG_CLS + TAG + f"target name = \"{nm}\"\n")
                if not self.ping(ip):  # Check reachability of the target
                    sys.stdout.write(self.TAG_CLS + TAG + f"target {nm}, ip: {ip} not reachable\n")
                    continue # return # do it silently. No serial output
                try_cnt = 0
                sent = False
                while not sent and try_cnt < try_cnt_max:
                    try:
                        if self.use_tcp_logger:
                            ack = None
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(to)
                            sock.connect((ip, self.port))
                            if my_debug:
                                sys.stdout.write(self.TAG_CLS + TAG + f"[tcp_logger] Sending to {ip}: {repr(msg)}\n")
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
