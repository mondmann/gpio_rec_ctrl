mport asyncio
import RPIO.GPIO as GPIO
import sys

loop = None

def message_manager_f():
    print ":P message_manager_f()"

def motion_sensor(self, message_manager_f):
    if loop is None:
        print(":(")
        return       # should not come to this
    # this enqueues a call to message_manager_f() 
    loop.call_soon_threadsafe(message_manager_f)

# this is the primary thread mentioned in Part 2
if __name__ == '__main__':
    try:
        # setup the GPIO
        GPIO.setwarnings(True)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(4, GPIO.IN) # adjust the PULL UP/PULL DOWN as applicable
        GPIO.add_event_detect(4, GPIO.RISING, callback=lambda x: self.motion_sensor(message_manager_f), bouncetime=500)

        # run the event loop
        loop = asyncio.get_event_loop()
        loop.run_forever()
        loop.close()
    except :
        print("Error:", sys.exc_info()[0])

    # cleanup
    GPIO.cleanup()
