#!/usr/bin/python3 -u

import datetime
import subprocess
import os
import logging as log
from gpiozero import LED, Button
from time import sleep
from threading import Thread, Timer
from typing import Optional

log.basicConfig(level=log.INFO)

# TODO: add config file

led = LED(8)
button = Button(7)

max_recoding_time = 180 # min
bit_rate = 128 # lame --abr param
buffer_size = "150M" # mbuffer 
target_directory = '/srv/gpiorec/'


class Led_driver:
    def __init__(self, scheme="ready"):
        self.running = True
        self.led_schemes = {
        "ready": (2,0.05,0.1,0.05),
        "busy": (0.2,0.2),
        "record": (0.5,2),
        "error": (0.05,0.05),
        }
        self.set_scheme(scheme)

    def stop(self):
        log.debug(f"{type(self).__name__} stopped" )
        self.running = False

    def run(self):
        led.off()
        while self.running:
            for delay in self._scheme:
                if self._new_scheme: 
                    led.off()
                    self._new_scheme = False
                    break
                sleep(delay)
                if self._new_scheme: 
                    led.off()
                    self._new_scheme = False
                    break
                led.toggle()

    def set_scheme(self, scheme: str):
        if scheme not in self.led_schemes.keys():
            log.error(f"{type(self).__name__} invalid scheme " + scheme)
        else:
            log.debug(f"{type(self).__name__} scheme set to {scheme}")
            self._scheme = self.led_schemes[scheme]
            self._new_scheme = True
            self._scheme_name = scheme

    def get_scheme(self):
        return self._scheme_name

    scheme = property(fget=get_scheme, fset=set_scheme)


class Recorder:
    def __init__(self, target_directory=os.getcwd()):
        self.target_directory = target_directory
        self.recording = False
        self.error = False
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
                    "arecord --quiet --format=dat --file-type=raw".split(),
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
            self.error = not all([0 == x.returncode for x in [self.wavrecord, self.buffer, self.lame]])
            log.log(log.ERROR if self.error  else log.DEBUG,
                    f"{type(self).__name__} subprocesses terminated  (" +
                    f"record: {self.wavrecord.returncode}, " +
                    f"buffer: {self.buffer.returncode}, " +
                    f"lame: {self.lame.returncode})")
            self.recording = False

    def stop(self):
        """ stops recording by sendig a SIGTERM to arecord """
        log.debug(f"{type(self).__name__} terminating wavrecord")
        self.wavrecord.terminate()

class Watchdog:
    """
        compare state of led_driver with recorder (consistency check)
        check for timeout and stop recording 
    """
    def __init__(self, recorder: Optional[Recorder] = None, led_driver: Optional[Led_driver] = None, timeout=5400):
        self.recorder = recorder
        self.led_driver = led_driver
        self.timeout = timeout # in seconds
        self.start_time = None

    def run(self):
        if not self.recorder or not self.led_driver:
            log.warning(f"{type(self).__name__} " +
                    f"recorder {'registered' if self.recorder else 'missing'}, "+
                    f"led_driver {'registered' if self.led_driver else 'missing'}")
            return # nothing to do
                     
        pass # TODO

def main():
    log.info("starting...")
    led_driver = Led_driver()
    led_thread = Thread(target=lambda : led_driver.run())
    led_thread.start()

    watchdog = Watchdog(led_driver=led_driver)
    watchdog_thread = Thread(target=lambda : do_every(3, watchdog.run()))
    watchdog_thread.start()

    try:
        recording = False
        while True:
            log.debug("waiting for button press")
            button.wait_for_press()
            button.wait_for_release()
            log.debug("button pressed")
            if not recording: # start it
                log.debug("start recording...")
                recorder = Recorder(target_directory) 
                recorder_thread = Thread(target=lambda : recorder.run())
                recorder_thread.start()
            else: # stop it
                log.debug("stop recording...")
                led_driver.scheme = "busy"
                recorder.stop()
                retval = recorder_thread.join() # FIXME check retval
            recording = not recording
            log.info("recording " + ("started" if recording else "stopped"))
            led_driver.scheme = "record" if recording else "ready"
            sleep(1) # debounce
    except KeyboardInterrupt:
        led_driver.scheme = "busy"
        recorder.stop()
        recorder_thread.join()
        led_driver.stop()
        watchdog_thread.stop()
        led_thread.join(3)
        watchdog_thread.join(3)

# TODO: Watchdog Thread with
# - check for recording too long
# - check for recording stopped with error

if __name__ == "__main__": main()
