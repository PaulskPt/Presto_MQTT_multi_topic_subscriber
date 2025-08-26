# See: import time, machine, sys
# reaction of @shariltumin on 2024-02-05
# discussion topic: How to print traceback of last unhandled exception when reaching MPY prompt 
class ERR(Exception):
   def __init__(self, n):
      super().__init__()
      self.n = n
      self.c = 0
   def log(self, error):
      self.c += 1
      if self.c < self.n:
         with open('/sd/mqtt_err_log.txt', 'a+') as f:
             f.write(f'{time.time()}: ')
             sys.print_exception(error, f)
      else:
         machine.soft_reset() # or whatever you need
         
import time, machine, sys

class ERR(Exception):
   def __init__(self, n):
      super().__init__()
      self.n = n
      self.c = 0
   def log(self, error):
      self.c += 1
      if self.c < self.n:
         with open('err.log', 'a+') as f:
             f.write(f'{time.time()}: ')
             sys.print_exception(error, f)
      else:
         machine.soft_reset() # or whatever you need