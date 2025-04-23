# ccpublisher - Cameo Collaborator's publishing service
# Copyright (C) 2022  Archimedes Exhibitions GmbH
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import asyncio
import logging
import enum
import os
from pathlib import Path

import aiofiles
import aionotify


logger = logging.getLogger(__name__)


class FileObserver:
    SKIP_FILESIZE_THRESHOLD = 1e06
    SKIP_PERCENT = 0.8

    class State(enum.Enum):
        INIT = enum.auto()
        CLOSED = enum.auto()
        OPENED = enum.auto()

    def __init__(self, file_path, backlog):
        self._file_path = Path(file_path)
        self._backlog = backlog
        self._state = self.State.INIT
        self._lines = []

        self._watcher = aionotify.Watcher()
        flags = (
            aionotify.Flags.MODIFY
            | aionotify.Flags.CREATE
            | aionotify.Flags.DELETE
            | aionotify.Flags.MOVED_FROM
        )
        self._watcher.watch(path=str(self._file_path.parent), flags=flags)
        logger.info(f"inotify set up to watch path: {self._file_path.parent}")

    @property
    def lines(self):
        return self._lines

    def start(self):
        return asyncio.create_task(self._observer_task(), name="File observer task")

    async def _observer_task(self):
        await self._watcher.setup(asyncio.get_running_loop())

        if self._file_path.exists():
            logfile = await self._open_file()
            self._state = self.State.OPENED
        else:
            logger.warning(
                f"File {self._file_path} does not exist, " f"delaying opening"
            )
            logfile = None

        while True:
            event = await self._watcher.get_event()
            logger.debug(
                f"inotify event: {event} " f"flags={aionotify.Flags.parse(event.flags)}"
            )

            if event.name == self._file_path.name:
                if (
                    aionotify.Flags.MODIFY & event.flags
                    and self._state == self.State.OPENED
                ):
                    while True:
                        line = await logfile.readline()
                        if not line:
                            break

                        self._add_line(line.strip())
                elif (
                    aionotify.Flags.DELETE & event.flags
                    or aionotify.Flags.MOVED_FROM & event.flags
                ) and self._state == self.State.OPENED:
                    logger.info("Closing file since it has been " "deleted or moved")
                    await logfile.close()
                    logfile = None
                    self._state = self.State.CLOSED
                elif aionotify.Flags.CREATE & event.flags and self._state in (
                    self.State.CLOSED,
                    self.State.INIT,
                ):
                    if self._state == self.State.CLOSED:
                        logger.info("Reopening file")
                    logfile = await self._open_file()
                    self._state = self.State.OPENED

    def _add_line(self, line):
        self._lines.append(line)
        self._lines = self._lines[-self._backlog :]

    async def _open_file(self):
        while True:
            try:
                f = await aiofiles.open(self._file_path, mode="r")

                size = os.stat(self._file_path).st_size
                if size > self.SKIP_FILESIZE_THRESHOLD:
                    target = int(size * self.SKIP_PERCENT)
                    logger.debug(f"Seeking to pos {target}")
                    await f.seek(target)
                else:
                    logger.debug("Churning the entire file")

                async for line in f:
                    self._add_line(line.strip())

                logger.info(f"File {self._file_path} opened successfully")

                return f
            except FileNotFoundError:
                await asyncio.sleep(0.5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    async def main():
        fo = FileObserver("/var/log/syslog", 5)
        fo.start()
        while True:
            await asyncio.sleep(1)

    asyncio.run(main())
