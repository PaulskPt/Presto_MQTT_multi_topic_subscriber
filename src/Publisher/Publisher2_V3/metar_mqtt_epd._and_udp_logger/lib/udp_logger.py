# udp_logger.py
# by Paulus Schulinck (Github handle: @PaulskPt)
# date 2025-09-17
# License: MIT
# Imported by metar_epd_and_udp_logger.py
import sys
import time

class UDPLogger:
    def __init__(self, sock, port: int=5005, broadcast_ip: str = '192.168.1.255', use_udp_logger: bool=True) -> None:
        self.sock = sock
        self.port = port
        self.ip = broadcast_ip
        self.use_udp_logger = use_udp_logger
        
    def write(self, msg):
      TAG = "UDPLogger.write(): "
      try_cnt = 0
      try_cnt_max = 3
      nr_sent = 0

      # Basic sanity checks
      if not self.sock:
          sys.stdout.write(TAG + "Socket is None. Skipping UDP send.\n")
          sys.stdout.write(f"{msg}\n")
          return

      if not isinstance(self.port, int) or not (0 < self.port < 65536):
          sys.stdout.write(TAG + f"Invalid port: {self.port}. Skipping UDP send.\n")
          sys.stdout.write(f"{msg}\n")
          return

      if not isinstance(self.ip, str) or len(self.ip.strip()) == 0:
          sys.stdout.write(TAG + "Invalid IP address. Skipping UDP send.\n")
          sys.stdout.write(f"{msg}\n")
          return

      # Convert int to str
      if isinstance(msg, int):
          msg = str(msg)

      if isinstance(msg, str) and len(msg.strip()) > 0:
          try:
              if self.use_udp_logger:
                  while nr_sent == 0:
                      nr_sent = self.sock.sendto(msg.encode(), (self.ip, self.port))
                      if nr_sent > 0:
                          break
                      time.sleep(0.1)
                      try_cnt += 1
                      if try_cnt >= try_cnt_max:
                          sys.stdout.write(TAG + f"UDP send failed after {try_cnt} attempts. Fallback to standard output.\n")
                          sys.stdout.write(f"{msg}\n")
                          break
                      else:
                          sys.stdout.write(TAG + f"UDP send attempt {try_cnt} failed, retrying...\n")
              sys.stdout.write(f"{msg}\n")
          except OSError as exc:
              errno = exc.args[0] if len(exc.args) > 0 else -1
              if errno == 101:
                  sys.stdout.write(TAG + "OSError: Network unreachable. Check WiFi connection.\n")
              elif errno == 113:
                  sys.stdout.write(TAG + "OSError: No route to host. Check UDP IP address and port.\n")
              else:
                  sys.stdout.write(TAG + f"UDP send error: {exc}\n")
                  sys.stdout.write(f"{msg}\n")
          except Exception as e:
              sys.stdout.write(TAG + f"Non-network exception in UDPLogger.write(): {e}\n")

    
    def flush(self): pass