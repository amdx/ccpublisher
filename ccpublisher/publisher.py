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

import os
import signal
import logging
import asyncio
import tempfile
import enum
import time
from pathlib import Path
from dataclasses import dataclass, asdict

from jinja2 import Template

from ccpublisher import queue
from ccpublisher.profile import Profile

logger = logging.getLogger(__name__)


@dataclass
class PublisherTask:
    profile: Profile
    returncode: int = None
    stdout: str = None
    stderr: str = None
    start_time: float = 0
    end_time: float = 0

    @property
    def elapsed(self):
        if self.start_time and self.end_time == 0:
            return time.time() - self.start_time
        else:
            return self.end_time - self.start_time

    def __json_repr__(self):
        return {
            **asdict(self),
            **{a: getattr(self, a) for a in dir(self) if a[0] != "_"},
        }


class Publisher:
    class State(enum.Enum):
        INIT = enum.auto()
        IDLE = enum.auto()
        REFRESHING = enum.auto()
        RUNNING = enum.auto()

    def __init__(self, template, auth, script, max_tasks):
        self._queue = queue.RAQueue(max_tasks)
        self._template = Template(open(template).read())
        self._auth = auth
        self._script = Path(script)
        self._current_task = None
        self._process = None
        self._last_task = None
        self._proc_started_ts = 0
        self._state = self.State.INIT
        logger.info(f"Loaded template file {template}")

    def start(self):
        return asyncio.create_task(self._publisher_task(), name="Publisher task")

    def get_current_status(self):
        return {
            "state": self._state.name,
            "last_task": self._last_task,
            "current_task": self._current_task,
            "queue": self.get_enqueued_tasks(),
        }

    def get_enqueued_tasks(self):
        return [
            {"task_id": taskdata[0], "task": taskdata[1]}
            for taskdata in self._queue.entries
        ]

    def publish(self, profile):
        task = PublisherTask(profile=profile)
        return self._queue.put(task)

    def remove_task(self, task_id):
        try:
            self._queue.remove(task_id)
        except self._queue.NotFoundError:
            return False
        else:
            return True

    def remove_all_tasks(self):
        self._queue.clear()

    def terminate_running_task(self):
        if self._current_task:
            logger.info("Terminating current task")
            os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            return True
        else:
            return False

    async def _publisher_task(self):
        self._state = self.State.IDLE

        while True:
            task = await self._queue.get()

            try:
                await self._publish(task)
            except Exception as e:
                logger.error("Error while attempting to publish:")
                logger.exception(e)
            finally:
                self._state = self.State.IDLE

    async def _publish(self, task):
        self._proc_started_ts = time.time()
        self._current_task = task

        self._state = self.State.REFRESHING
        await task.profile.refresh()

        self._state = self.State.RUNNING

        context = {
            "profile": asdict(task.profile),
            "auth": self._auth,
        }
        logger.debug(f"Context: {context}")
        properties = self._template.render(context)

        with tempfile.TemporaryDirectory() as tmpdir:
            properties_file = Path(tmpdir) / "project.properties"
            f = open(properties_file, "w")
            f.write(properties)
            f.close()

            invocation = f"./{self._script.name} properties={properties_file}"
            logger.info("Running session")
            logger.info(f" {invocation}")

            self._current_task.start_time = time.time()

            # https://stackoverflow.com/questions/4789837/how-to-terminate-a-python-subprocess-launched-with-shell-true
            self._process = await asyncio.create_subprocess_shell(
                invocation,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._script.parent,
                env={"DISPLAY": ":0"},
                preexec_fn=os.setsid,
            )

            # TODO: add stream reader tasks
            stdout, stderr = await self._process.communicate()

            logger.info(
                f"rc={self._process.returncode} " f"stdout={stdout} stderr={stderr}"
            )

            self._current_task.returncode = self._process.returncode
            self._current_task.stderr = stderr.decode()
            self._current_task.stdout = stdout.decode()
            self._current_task.end_time = time.time()

            self._last_task = self._current_task
            self._current_task = None
            self._process = None

            logger.info("Session completed")
