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
import signal
import functools

import yaml

from ccpublisher import api, publisher, fileobserver, profile, __version__

logger = logging.getLogger(__name__)


class Service:
    def __init__(self, config_file):
        logger.info(f"AMDX ccpublisher v{__version__.__version__} starting up")

        self._config = yaml.safe_load(open(config_file))

    async def run(self):
        loop = asyncio.get_running_loop()
        for signame in {"SIGINT", "SIGTERM"}:
            loop.add_signal_handler(
                getattr(signal, signame), functools.partial(self._shutdown, signame)
            )

        profiles_manager = profile.ProfilesManager(
            api_url=self._config["twc"]["api_url"],
            login=self._config["auth"]["username"],
            password=self._config["auth"]["password"],
        )
        await profiles_manager.fetch_all_profiles()

        publisher_ = publisher.Publisher(
            template=self._config["publisher"]["template"],
            auth=self._config["auth"],
            script=self._config["publisher"]["script"],
            max_tasks=self._config["publisher"]["queue_maxsize"],
        )
        publisher_.start()

        fileobserver_ = fileobserver.FileObserver(
            file_path=self._config["fileobserver"]["file_path"],
            backlog=self._config["fileobserver"]["backlog"],
        )
        fileobserver_.start()

        api_ = api.API(
            publisher=publisher_,
            fileobserver=fileobserver_,
            profiles_manager=profiles_manager,
            extra_context=self._config["extra_context"],
            listen_address=self._config["api"]["listen_address"],
            port=self._config["api"]["port"],
        )
        await api_.start()

        while True:
            await asyncio.sleep(1)

    def _shutdown(self, signame):
        logger.info(
            f"Caught signal {signame}, "
            f"cancelling {len(asyncio.all_tasks())} running tasks"
        )

        for task in asyncio.all_tasks():
            task.cancel()
