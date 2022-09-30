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


class RAQueue:
    class FullError(Exception):
        pass

    class NotFoundError(Exception):
        pass

    last_id = 0

    def __init__(self, max_size):
        self._max_size = max_size
        self._entries = []
        self._available = asyncio.Event()

    @property
    def entries(self):
        return self._entries

    @property
    def size(self):
        return len(self._entries)

    def put(self, item):
        if len(self._entries) == self._max_size:
            raise self.FullError()
        else:
            self.last_id += 1
            self._entries.append((self.last_id, item))
            self._available.set()

            return self.last_id

    def remove(self, task_id):
        tasks = self._entries[:]
        for element in tasks:
            if element[0] == task_id:
                self._entries.remove(element)
                return

        raise self.NotFoundError()

    def clear(self):
        self._entries = []
        self._available.clear()

    async def get(self):
        # This works around the possibility of a race condition when
        # the queue is cleared, preventing an error when popping()
        while True:
            await self._available.wait()
            if not self._entries:
                self._available.clear()
            else:
                break

        task_id, item = self._entries.pop(0)

        if not self._entries:
            self._available.clear()

        return item
