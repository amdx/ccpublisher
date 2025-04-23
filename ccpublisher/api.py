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

import datetime
import enum
import logging
import json
from pathlib import Path
import dataclasses

import jinja2
from aiohttp import web
import aiohttp_apispec
import marshmallow
import marshmallow.validate
import aiohttp_jinja2


from ccpublisher import __version__

logger = logging.getLogger(__name__)


class TaskIdSchema(marshmallow.Schema):
    task_id = marshmallow.fields.Integer(
        description="Numeric ID of the task", required=True
    )


class ProfileIdSchema(marshmallow.Schema):
    profile_id = marshmallow.fields.String(
        description="ID of the profile", required=True
    )


class RefreshKindSchema(marshmallow.Schema):
    refresh = marshmallow.fields.String(
        validate=marshmallow.validate.OneOf(["known", "all"])
    )


class CustomEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, "__json_repr__"):
            return o.__json_repr__()
        elif dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        elif isinstance(o, datetime.datetime):
            return str(o)
        elif isinstance(o, enum.Enum):
            return o.name
        else:
            return super().default(o)


class API:
    def __init__(
        self,
        publisher,
        fileobserver,
        profiles_manager,
        extra_context,
        listen_address,
        port,
    ):
        self._publisher = publisher
        self._fileobserver = fileobserver
        self._profiles_manager = profiles_manager
        self._extra_context = extra_context
        self._listen_address = listen_address
        self._port = port
        self._site = None

        templates_path = Path(__file__).parent / "templates"
        static_path = Path(__file__).parent / "static"

        self._app = web.Application()
        r = self._app.router

        # UI
        r.add_get("/", self._redirect, allow_head=False)
        r.add_get("/ui", self._index, allow_head=False)
        r.add_static("/static", static_path, name="static")

        # Service
        r.add_get("/api/v1/status", self._get_full_status, allow_head=False)

        # Tasks
        r.add_get("/api/v1/tasks", self._get_tasks, allow_head=False)
        r.add_post("/api/v1/tasks", self._create_task)
        r.add_delete("/api/v1/tasks", self._remove_all_tasks)
        r.add_delete("/api/v1/tasks/{task_id}", self._remove_task)
        r.add_delete("/api/v1/current_task", self._terminate_current_task)

        # Profiles
        r.add_get("/api/v1/profiles", self._get_profiles, allow_head=False)

        # Log
        r.add_get("/api/v1/loglines", self._get_loglines, allow_head=False)

        aiohttp_apispec.setup_aiohttp_apispec(
            app=self._app,
            swagger_path="/api/v1/docs",
            static_path="/swagger",
            version=__version__.__version__,
            error_callback=self._on_validation_error,
        )
        self._app.middlewares.append(aiohttp_apispec.validation_middleware)
        self._app.middlewares.append(self._error_wrapper)

        aiohttp_jinja2.setup(
            app=self._app, loader=jinja2.FileSystemLoader(templates_path)
        )

        self._runner = web.AppRunner(self._app)

    async def start(self):
        logger.info(
            f"Starting API handler " f"listening on {self._listen_address}:{self._port}"
        )
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._listen_address, self._port)
        await self._site.start()

    @web.middleware
    async def _error_wrapper(self, request, handler):
        try:
            resp = await handler(request)
        except (
            web.HTTPFound,
            web.HTTPForbidden,
            web.HTTPConflict,
            web.HTTPNotFound,
            web.HTTPUnauthorized,
            web.HTTPNoContent,
            web.HTTPCreated,
        ):
            raise
        except Exception as e:
            if not hasattr(e, "handled"):
                logger.exception(e)
            self._report_error(e.__class__.__name__, str(e))
        else:
            return resp

    def _redirect(self, request):
        raise web.HTTPFound("/ui")

    def _resolve_rid(self, resource_id):
        return resource_id and self._profiles_manager.get_resource_name(resource_id)

    async def _get_status(self):
        return {
            "publisher": self._publisher.get_current_status(),
            "loglines": self._fileobserver.lines,
        }

    @aiohttp_jinja2.template("index.html")
    async def _index(self, request):
        await self._profiles_manager.refresh_known_profiles()

        return {
            "status": await self._get_status(),
            "profiles": self._profiles_manager.profiles,
            "extra_context": self._extra_context,
            "version": __version__.__version__,
        }

    @aiohttp_apispec.docs(
        tags=["service"],
        summary="Get the current status of the service",
        description="",
        responses={
            200: {"description": "Status report object returned"},
            500: {"description": "Server side error"},
        },
    )
    async def _get_full_status(self, request):
        return web.json_response(await self._get_status(), dumps=CustomEncoder().encode)

    @aiohttp_apispec.docs(
        tags=["tasks"],
        summary="Get a list of currently enqueued tasks",
        description="",
        responses={
            200: {"description": "List of enqueued tasks returned"},
            500: {"description": "Server side error"},
        },
    )
    async def _get_tasks(self, request):
        return web.json_response(
            self._publisher.get_enqueued_tasks(), dumps=CustomEncoder().encode
        )

    @aiohttp_apispec.docs(
        tags=["tasks"],
        summary="Enqueue a publishing task",
        description="",
        responses={
            201: {"description": "Task created"},
            404: {"description": "Resource not found"},
            500: {"description": "Server side error"},
        },
    )
    @aiohttp_apispec.request_schema(ProfileIdSchema)
    async def _create_task(self, request):
        profile_id = request["data"]["profile_id"]
        profile = self._profiles_manager.get_profile(profile_id)

        task_id = self._publisher.publish(profile)

        return web.json_response(
            {
                "profile_id": profile_id,
                "task_id": task_id,
            },
            status=web.HTTPCreated.status_code,
            dumps=CustomEncoder().encode,
        )

    @aiohttp_apispec.docs(
        tags=["tasks"],
        summary="Remove an enqueued task",
        description="",
        responses={
            204: {"description": "Successfully removed enqueued task"},
            404: {"description": "Task not found"},
            500: {"description": "Server side error"},
        },
    )
    @aiohttp_apispec.match_info_schema(TaskIdSchema)
    async def _remove_task(self, request):
        if self._publisher.remove_task(request["match_info"]["task_id"]):
            raise web.HTTPNoContent()
        else:
            raise web.HTTPNotFound()

    @aiohttp_apispec.docs(
        tags=["tasks"],
        summary="Remove all enqueued task",
        description="",
        responses={
            204: {"description": "Successfully removed all enqueued tasks"},
            500: {"description": "Server side error"},
        },
    )
    async def _remove_all_tasks(self, request):
        self._publisher.remove_all_tasks()
        raise web.HTTPNoContent()

    @aiohttp_apispec.docs(
        tags=["tasks"],
        summary="Terminate the currently running task",
        description="",
        responses={
            204: {"description": "Successfully terminated"},
            404: {"description": "No running task"},
            500: {"description": "Server side error"},
        },
    )
    def _terminate_current_task(self, request):
        if self._publisher.terminate_running_task():
            raise web.HTTPNoContent()
        else:
            raise web.HTTPNotFound()

    @aiohttp_apispec.docs(
        tags=["profiles"],
        summary="Get a list of profiles",
        description="",
        responses={
            200: {"description": "List of profiles"},
            500: {"description": "Server side error"},
        },
    )
    @aiohttp_apispec.querystring_schema(RefreshKindSchema)
    async def _get_profiles(self, request):
        refresh_kind = request["querystring"].get("refresh", None)
        if refresh_kind == "all":
            await self._profiles_manager.fetch_all_profiles()
        elif refresh_kind == "known":
            await self._profiles_manager.refresh_known_profiles()

        return web.json_response(
            self._profiles_manager.profiles, dumps=CustomEncoder().encode
        )

    @aiohttp_apispec.docs(
        tags=["loglines"],
        summary="Get a backlog of lines from the log",
        description="",
        responses={
            200: {"description": "Log entries returned"},
            500: {"description": "Server side error"},
        },
    )
    async def _get_loglines(self, request):
        return web.json_response(self._fileobserver.lines)

    def _on_validation_error(
        self, error, req, schema, error_status_code, error_headers
    ):
        logger.error(f"Schema validation failure: error={error.messages}")
        self._report_error(
            message="Request validation error",
            body=error.messages,
            headers=error_headers,
        )

    def _report_error(
        self, message, body, headers=None, exception=web.HTTPInternalServerError
    ):
        raise exception(
            body=json.dumps(
                {
                    "error": message,
                    "body": body,
                }
            ).encode(),
            headers=headers if headers else {},
            content_type="application/json",
        )
