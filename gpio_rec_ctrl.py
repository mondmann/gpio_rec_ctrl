#!/usr/bin/python3 -u
import asyncio
import datetime
import os
import logging as log
from enum import Enum

from gpiozero import LED
from apgpio import GPIO

log.basicConfig(level=log.DEBUG)

# TODO: add config file
config = dict(
    led_number=8,
    button_number=7,
    bit_rate=128,  # lame --abr param
    max_recording_time=180,
    target_directory="/srv/gpiorec",
    block_size=4096,  # FIXME: use page size from "getconf PAGESIZE"
    device="hw:1"
)


class ButtonHandler:
    def __init__(self, callback, pin: int = config["button_number"], loop=None):
        self._button = GPIO(pin, loop)
        self.loop = loop
        self.callback = callback
        self.running = False

    async def run(self):
        self.running = True
        while self.running:
            log.debug(f"{type(self).__name__} waiting for button press...")
            state = await self._button.read_async()
            while not state == await self._button.read_async():
                pass
            await self.callback()
            await asyncio.sleep(1)  # bounce protection


class LedDriver:
    def __init__(self, scheme: str = "ready"):
        self.running = False
        self.led_schemes = {
            "ready": (2, 0.05, 0.1, 0.05),
            "busy": (0.2, 0.2),
            "record": (0.5, 2),
            "error": (0.05, 0.05),
        }
        self.scheme = scheme
        self._led = LED(config["led_number"])

    def stop(self):
        log.debug(f"{type(self).__name__} stopped")
        self.running = False

    async def run(self):
        self.running = True
        self._led.off()
        while self.running:
            for delay in self._scheme:
                if self._new_scheme:
                    self._led.off()
                    self._new_scheme = False
                    break
                await asyncio.sleep(delay)
                if self._new_scheme:
                    self._led.off()
                    self._new_scheme = False
                    break
                self._led.toggle()

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


class Subprocess:  # abstract
    def __init__(self):
        self.subprocess = None

    def stop(self):
        """ stops recording by sending a SIGTERM to arecord """
        if self.subprocess:
            log.debug(f"{type(self).__name__} terminating subprocess")
            self.subprocess.terminate()


class Recorder(Subprocess):
    def __init__(self, queue: asyncio.Queue):
        super(Recorder, self).__init__()
        self.queue = queue
        self.subprocess = None
        self.recording = False
        self.error = False

    async def run(self):
        log.debug(f"{type(self).__name__} set up recording")
        self.error = False
        self.recording = True
        self.subprocess = await asyncio.create_subprocess_exec(
            "arecord", f"-D{config['device']}", "--quiet", "--format=dat", "--file-type=raw",
            stdout=asyncio.subprocess.PIPE
        )
        log.debug(f"{type(self).__name__} started recording")

        while True:
            data = await self.subprocess.stdout.read(config['block_size'])
            self.queue.put_nowait(data)
            if not data:
                break  # end of data

        await self.subprocess.wait()
        # arecord seems to exit with 1 on signal TERM
        self.error = not 1 == self.subprocess.returncode
        log.log(log.ERROR if self.error else log.DEBUG,
                f"{type(self).__name__} subprocesses terminated (return code {self.subprocess.returncode} (expected 1)")
        self.recording = False


class Encoder(Subprocess):
    def __init__(self, queue: asyncio.Queue, target_directory: str):
        super(Encoder, self).__init__()
        self.queue = queue
        self.target_directory = target_directory
        self.subprocess = None
        self.error = False

    async def run(self):
        log.debug(f"{type(self).__name__} set up encoding")
        self.error = False
        outfilename = os.path.join(self.target_directory,
                                   datetime.datetime.now().replace(microsecond=0).isoformat()
                                   .replace('T', '--').replace(':', "-") + ".mp3")
        self.subprocess = await asyncio.create_subprocess_exec(
            f"lame", "-s", "48", "--quiet", "-r", "--abr", f"{config['bit_rate']}", "-", outfilename,
            stdin=asyncio.subprocess.PIPE
        )
        log.debug(f"{type(self).__name__} started encoding")

        while True:
            data = await self.queue.get()
            self.subprocess.stdin.write(data)
            await self.subprocess.stdin.drain()
            if not data:
                break  # end of data

        self.subprocess.stdin.close()
        await self.subprocess.stdin.wait_closed()
        await self.subprocess.wait()
        self.error = not 0 == self.subprocess.returncode
        log.log(log.ERROR if self.error else log.DEBUG,
                f"{type(self).__name__} subprocesses terminated (return code {self.subprocess.returncode}")


class StopTimer:
    """
        check for timeout and stop recording if necessary
    """

    def __init__(self, timeout, callback):
        self._timeout = timeout
        self._callback = callback
        self._task = asyncio.create_task(self._job())

    async def _job(self):
        await asyncio.sleep(self._timeout)
        if asyncio.iscoroutine(self._callback):
            await self._callback()
        else:
            self._callback()

    def cancel(self):
        self._task.cancel()


class State(Enum):
    IDLE = 0
    RECORDING = 1
    WRITING = 2
    ERROR = 42


class Controller:
    def __init__(self):
        self.led_driver = None
        self.button_handler = None
        self.recorder = None  # per recording object
        self.encoder = None   # per recording object
        self.stop_timer = None  # per recording object
        self.state = State.IDLE

    async def run(self):
        self.led_driver = LedDriver()  # running continuously
        # loop ist noch accessible in constructor!
        self.button_handler = ButtonHandler(self.handle_button_press, loop=asyncio.get_event_loop())
        await asyncio.gather(self.led_driver.run(), self.button_handler.run())

    async def do_recording(self):
        queue = asyncio.Queue()
        self.recorder = Recorder(queue)
        self.encoder = Encoder(queue, config['target_directory'])
        self.stop_timer = StopTimer(config['max_recording_time'], self.stop_recording)
        self.led_driver.scheme = "record"
        self.state = State.RECORDING
        await asyncio.gather(self.recorder.run(), self.encoder.run())
        if self.encoder.error or self.recorder.error:
            self.led_driver.scheme = "error"
            self.state = State.ERROR
        else:
            self.led_driver.scheme = "ready"
            self.state = State.IDLE
        if not queue.empty():
            log.error(f"{type(self).__name__} queue is not empty")
            self.led_driver.scheme = "error"
            self.state = State.ERROR

    def stop_recording(self):
        self.stop_timer.cancel()
        self.stop_timer = None
        self.recorder.stop()
        self.led_driver.scheme = "busy"
        self.state = State.WRITING
        # now wait for encoder to terminate

    async def handle_button_press(self):
        log.debug(f"{type(self).__name__} button press in state {self.state}")
        if self.state == State.ERROR:
            return  # ignore button in error state
        if self.state == State.IDLE:
            asyncio.create_task(self.do_recording())
        if self.state == State.RECORDING:
            self.stop_recording()
        if self.state == State.WRITING:
            return  # ignore until done


def main():
    log.info("starting...")
    asyncio.run(Controller().run())
    log.info("shutdown...")


if __name__ == "__main__":
    main()
