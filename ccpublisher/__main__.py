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
import click

from ccpublisher import service


logger = logging.getLogger(__name__)

LOG_FORMAT = '[{asctime}] {levelname:.4} {{{name}:{lineno}}} {message}'


@click.command()
@click.argument('config-file')
@click.option('-d', '--debug/--no-debug', default=False,
              help='Print debug messages')
def main(config_file, debug):
    logging.basicConfig(
        format=LOG_FORMAT,
        style='{',
        level=logging.DEBUG if debug else logging.INFO
    )

    if not debug:
        logging.getLogger('aiohttp.access').setLevel(logging.WARNING)

    service_ = service.Service(config_file)

    try:
        asyncio.run(service_.run(), debug=debug)
    except (KeyboardInterrupt, asyncio.exceptions.CancelledError):
        logger.info('Exiting')


if __name__ == '__main__':
    main()
