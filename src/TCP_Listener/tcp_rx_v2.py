#tcp_rx_v1.py
import socket
import time
my_debug = False
sock = socket.socket()
sock.bind(('', 12345))
sock.listen(1)
print("Listening for TCP connections...")

while True:
    try:
        conn, addr = sock.accept()
        if my_debug:
            print("Connected by", addr)

        buffer = ''
        while True:
            data = conn.recv(512)
            if not data:
                break

            text = data.decode('utf-8', errors='ignore')
            for char in text:
                buffer += char
                if char == '\n':
                    # print(f"[raw] {repr(text)}")
                    print(buffer.rstrip('\r\n'))
                    buffer = ''  # Reset for next line

        conn.close()
    except Exception as e:
        print("⚠️ Receiver error:", e)
