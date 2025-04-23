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
import datetime
import hashlib
from dataclasses import dataclass
import logging

import atwc


logger = logging.getLogger(__name__)


@dataclass
class StereoData:
    scope: str = None
    template_name: str = None


@dataclass
class CommitInfo:
    id: int = None
    author: str = None
    date: datetime.datetime = None
    message: str = None


@dataclass
class Resource:
    name: str
    id: str
    created: datetime.datetime = None
    modified: datetime.datetime = None
    category_path: str = None
    last_commit: CommitInfo = None


@dataclass
class Profile:
    id: str = None
    md: Resource = None
    cc: Resource = None
    stereo_data: StereoData = None
    is_stale: bool = True
    _manager = None

    async def refresh(self):
        await self._manager.refresh_profile(self)


class LockedError(Exception):
    pass


class ProfilesManager:
    CCPUB_STEREOTYPE_NAME = 'ccPublisher'

    def __init__(self, api_url, login, password):
        self._client = atwc.client.Client(
            api_url=api_url,
            login=login,
            password=password
        )
        self._profiles = []
        self._lock = asyncio.Lock()

    @property
    def profiles(self):
        return self._profiles

    def get_profile(self, profile_id):
        for profile in self._profiles:
            if profile.id == profile_id:
                return profile

        return None

    async def fetch_all_profiles(self):
        if self._lock.locked():
            raise LockedError('A refresh is already taking place')

        async with self._lock:
            logger.info('Fetching all profiles')
            profiles = []
            async with self._client.create_session():
                resource_browser = atwc.browsers.ResourceBrowser(self._client)
                await resource_browser.fetch()

                for md_resource in resource_browser.md_resources:
                    logger.info(f"Scanning MD resource: {md_resource['dcterms:title']}")
                    stereo_data = await self._get_ccpub_stereo_data(md_resource)
                    if stereo_data is None:
                        continue

                    profile = Profile()
                    profile._manager = self
                    await self._populate_profile(
                        md_resource, profile, resource_browser, stereo_data
                    )

                    profiles.append(profile)

            self._profiles = sorted(
                profiles,
                key=lambda p: (p.md.category_path + p.md.name).lower()
            )

            logger.info(f'Assembled {len(self._profiles)} profiles')

    async def refresh_known_profiles(self):
        profiles = []
        async with self._lock:
            async with self._client.create_session():
                resource_browser = atwc.browsers.ResourceBrowser(self._client)
                await resource_browser.fetch()

                for profile in self._profiles:
                    md_resource = self._find_resource(
                        resource_browser.md_resources, profile.md.name
                    )
                    await self._populate_profile(
                        md_resource, profile, resource_browser, None
                    )
                    profiles.append(profile)

        self._profiles = profiles

    async def refresh_profile(self, profile):
        async with self._lock:
            async with self._client.create_session():
                resource_browser = atwc.browsers.ResourceBrowser(self._client)
                await resource_browser.fetch()

                md_resource = self._find_resource(
                    resource_browser.md_resources, profile.md.name
                )

                stereo_data = await self._get_ccpub_stereo_data(md_resource)

                await self._populate_profile(
                    md_resource, profile, resource_browser, stereo_data
                )

    def _is_stale(self, md, cc):
        return bool(cc is None or md.modified > cc.modified)

    def _generate_id(self, name):
        return hashlib.md5(name.encode()).hexdigest()

    async def _populate_profile(self, md_resource, profile, resource_browser,
                                stereo_data):
        profile.md = await self._get_resource_data(
            resource_browser, md_resource
        )
        cc_resource = self._find_resource(
            resource_browser.cc_resources, profile.md.name
        )
        if cc_resource is None:
            logger.warning(f"MD Resource {md_resource['dcterms:title']} "
                "doesn't have an associated CC resource")

        profile.cc = await self._get_resource_data(
            resource_browser, cc_resource
        )

        if stereo_data is not None:
            profile.stereo_data = stereo_data

        profile.is_stale = self._is_stale(profile.md, profile.cc)
        profile.id = self._generate_id(profile.md.name)

    async def _get_resource_data(self, resource_browser, resource):
        if resource is None:
            return None

        created = datetime.datetime.fromtimestamp(resource['createdDate'])
        modified = datetime.datetime.fromtimestamp(resource['modifiedDate'])
        category_path = await resource_browser.get_category_path(resource)

        model_browser = atwc.browsers.ModelBrowser(self._client, resource)
        revision_info = await model_browser.get_revision_info()
        commit_info = CommitInfo(
            id=revision_info['ID'],
            author=revision_info['author'],
            date=datetime.datetime.fromtimestamp(revision_info['createdDate']),
            message=revision_info['description'],
        )

        return Resource(
            id=resource['ID'],
            name=self._strip_extension(resource['dcterms:title']),
            created=created,
            modified=modified,
            category_path=category_path,
            last_commit=commit_info
        )

    def _find_resource(self, resources, resource_name):
        for resource in resources:
            if self._strip_extension(
                    resource['dcterms:title']) == resource_name:
                return resource

        return None

    async def _get_ccpub_stereo_data(self, resource):
        model_browser = atwc.browsers.ModelBrowser(self._client, resource)

        model = await model_browser.get_model_root()

        if not await model_browser.find_stereotype(
                model, self.CCPUB_STEREOTYPE_NAME
        ):
            return None

        tagged_values = await model_browser.get_tagged_values(
            model, self.CCPUB_STEREOTYPE_NAME
        )

        if 'serviceEnabled' in tagged_values \
                and tagged_values['serviceEnabled'][0].lower() == 'false':
            return None

        scope_ids = atwc.utils.extract_ids(tagged_values['scope'])
        scope_elements = await model_browser.get_elements_batch(scope_ids)

        scope_qns = [
            await model_browser.get_qualified_name(scope['data'][1])
            for scope in scope_elements.values()
        ]
        scope_str = ';'.join(scope_qns)

        template_id = atwc.utils.extract_ids(tagged_values['template'])[0]
        template_element = await model_browser.get_element(template_id)
        template_name = template_element['kerml:esiData']['name']

        return StereoData(
            scope=scope_str,
            template_name=template_name,
        )

    def _strip_extension(self, resource_name):
        if resource_name[-7:] == '.MASTER':
            return resource_name[:-7]
        elif resource_name[-3:] == '.CC':
            return resource_name[:-3]
        else:
            return resource_name
