
import datetime
import subprocess
import os
import logging as log
from gpiozero import LED, Button
from time import sleep
from threading import Thread

log.basicConfig(level=log.DEBUG)

# TODO: add config file

led = LED(8)
button = Button(7)

max_recoding_time = 180 # min
bit_rate = 128 # lame --abr param
buffer_size = "150M" # mbuffer 

led_scheme = {
        "ready": (2,0.05,0.1,0.05),
        "busy": (0.2,0.2),
        "record": (0.5,2),
        }


class Led_driver:
    def __init__(self, scheme=led_scheme["ready"]):
        self.set_scheme(scheme)
        self.running = True

    def stop(self):
        log.debug(f"{type(self).__name__} stopped" )
        self.running = False

    def run(self):
        led.off()
        while self.running:
            for delay in self.scheme:
                if self.new_scheme: 
                    led.off()
                    self.new_scheme = False
                    break
                sleep(delay)
                if self.new_scheme: 
                    led.off()
                    self.new_scheme = False
                    break
                led.toggle()

    def set_scheme(self, scheme):
        log.debug(f"{type(self).__name__} scheme set to {scheme}")
        self._scheme = scheme
        self.new_scheme = True

    def get_scheme(self):
        return self._scheme

    scheme = property(fget=get_scheme, fset=set_scheme)


class Recorder:
    def __init__(self, target_directory=os.getcwd()):
        self.target_directory = target_directory
        self.recording = False
        self.wavrecord = self.buffer = self.lame = None

    def run(self): # blocking, use in Thread if necessary
        if self.recording:
            log.debug(f"{type(self).__name__} ignore start, already running")
            return # ignore graciously
        else:
            log.debug(f"{type(self).__name__} set up recording")
            outfilename = os.path.join(self.target_directory,
                    datetime.datetime.now().replace(microsecond=0).isoformat()
                    .replace('T', '--').replace(':', "-") + ".mp3")
            self.recording = True
            self.wavrecord = subprocess.Popen(
                    "arecord --quiet --fomat=dat --file-type=raw".split(),
                    stdout=subprocess.PIPE)
            self.buffer = subprocess.Popen(
                    f"mbuffer -q -m {buffer_size}".split(),
                    stdout=subprocess.PIPE,stdin=self.wavrecord.stdout) 
            self.lame = subprocess.Popen(
                    f"lame --quiet -r --abr {bit_rate} -".split() + [outfilename], 
                    stdin=self.buffer.stdout, stdout=subprocess.PIPE)
            self.wavrecord.stdout.close()  # Allow p1 to receive a SIGPIPE if p2 exits.
            output, err = self.lame.communicate()
            log.debug(f"{type(self).__name__} started recording")
            self.wavrecord.wait()
            self.buffer.wait()
            self.lame.wait()
            log.debug(f"{type(self).__name__} subprocesses terminated")
            self.recording = False

    def stop(self):
        """ stops recording by sendig a SIGTERM to arecord """
        log.debug(f"{type(self).__name__} terminating wavrecord")
        self.wavrecord.terminate()


led_driver = Led_driver()
led_thread = Thread(target=lambda : led_driver.run())
led_thread.start()

try:
    recording = False
    while True:
        log.debug("waiting for button press")
        button.wait_for_press()
        button.wait_for_release()
        log.debug("button pressed")
        if not recording: # start it
            log.debug("start recording...")
            recorder = Recorder() # FIXME: Path in Config
            recorder_thread = Thread(target=lambda : recorder.run())
            recorder_thread.start()
        else: # stop it
            log.debug("stop recording...")
            led_driver.scheme = led_scheme["busy"]
            recorder.stop()
            retval = recorder_thread.join() # FIXME check retval
        recording = not recording
        log.info("recording " + ("started" if recording else "stopped"))
        led_driver.scheme = led_scheme["record" if recording else "ready"]
        sleep(1)


except KeyboardInterrupt:
    led_driver.scheme = led_scheme["busy"]
    recorder.stop()
    recorder_thread.join()
    led_driver.stop()
    led_thread.join(3)
