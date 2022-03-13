#
# apgpio - Linux Sysfs GPIO module for asyncio
#
# Copyright (C) 2016 by Artur Wroblewski <wrobell@riseup.net>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# https://gitlab.com/wrobell/apgpio/blob/master/apgpio.py

"""
Linux Sysfs GPIO module for asyncio.
"""

import asyncio
import os.path
from collections import deque
from functools import partial
import select

BUFFER_LEN = 100

path = partial(os.path.join, '/sys/class/gpio')
path_gpio = lambda gpio, *args: path('gpio{}'.format(gpio), *args)


class GPIO:
    """
    GPIO pin reader.

    :var gpio: GPIO pin number.
    """

    def __init__(self, gpio, loop=None):
        """
        Create GPIO pin reader.

        :param gpio: GPIO pin number.
        :param loop: Asyncio loop instance.
        """
        self.gpio = gpio
        self._loop = asyncio.get_event_loop() if loop is None else loop
        self._task = None
        self._buffer = deque([], BUFFER_LEN)
        self._error = None

        self._epoll = select.epoll()
        self._loop.add_reader(self._epoll.fileno(), self._process_event)

        if not os.path.exists(path_gpio(gpio)):
            write_gpio(path('export'), gpio)

        write_gpio(path_gpio(gpio, 'direction'), 'in')
        write_gpio(path_gpio(gpio, 'edge'), 'both')

        self._fd = open(path_gpio(gpio, 'value'), 'r')
        self._epoll.register(self._fd, select.POLLPRI)

    def read(self):
        """
        Read state of GPIO pin.

        Returns true when pin is high and false when it is low.
        """
        self._fd.seek(0)
        return self._fd.read(1)[0] == '1'

    async def read_async(self):
        """
        Read state of GPIO pin.

        The method is a coroutine. It waits until state of pin changes.

        Returns true when pin is high and false when it is low.
        """
        self._task = self._loop.create_future()
        if self._error:
            self._task.set_exception(self._error)
        elif self._buffer:
            self._task.set_result(self._buffer.popleft())
        return await self._task

    def close(self):
        """
        Close GPIO pin reader.
        """
        self._loop.remove_reader(self._fd)
        self._epoll.close()
        self._fd.close()
        write_gpio(path('unexport'), self.gpio)

    def _process_event(self):
        """
        Process epoll event.
        """
        buffer = self._buffer
        task = self._task
        awaited = task and not task.done()

        try:
            self._epoll.poll(0)  # avoid blocking
            self._fd.seek(0)
            data = self._fd.read()
            value = data[0] == '1'
        except Exception as ex:
            if awaited:
                task.set_exception(ex)
            return

        # if buffer is non-empty, process data through buffer
        if awaited and buffer:
            # pop item first, so we do not add value to already full
            # buffer
            item = buffer.popleft()
            buffer.append(value)
            task.set_result(item)
        elif awaited and not buffer:
            # no data in buffer, so put value as result of awaited
            # task immediately
            task.set_result(value)
        elif len(buffer) == BUFFER_LEN:
            assert not awaited
            self._error = DataError('Data buffer full')
        else:
            assert not awaited
            buffer.append(value)


class DataError(Exception):
    """
    Exception raised on data error like full buffer.
    """


def write_gpio(fn, value):
    """
    Write value to GPIO file.

    :param fn: File name.
    :param value: Value to write to the file.
    """
    with open(fn, 'w') as f:
        f.write(str(value))


__all__ = ['GPIO', 'DataError']

# vim: sw=4:et:ai
