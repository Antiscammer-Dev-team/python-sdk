from collections.abc import Awaitable, Callable
from typing import Any, Optional, Union
from inspect import isawaitable
from urllib import parse
from aiohttp import web

RawCallback = Callable[[web.Request], Awaitable[web.StreamResponse]]
OnVoteCallback = Callable[["Vote"], Any]
OnVoteDecorator = Callable[[OnVoteCallback], RawCallback]


class Vote:
    """A dispatched Top.gg vote event."""

    __slots__ = ("receiver_id", "voter_id", "is_server", "is_test", "is_weekend", "query")

    def __init__(self, json: dict[str, Any]) -> None:
        self.receiver_id = int(json.get("bot", json.get("guild")))
        self.voter_id = int(json["user"])
        self.is_server = "guild" in json
        self.is_test = json["type"] == "test"
        self.is_weekend = bool(json.get("isWeekend"))

        query_str = json.get("query")
        self.query = {
            k: v[0] for k, v in parse.parse_qs(parse.urlsplit(query_str).query).items()
        } if query_str else {}

    def __repr__(self) -> str:
        return f"<Vote receiver_id={self.receiver_id} voter_id={self.voter_id}>"


class Webhooks:
    """
    Receive events from the Top.gg servers.

    :param auth: The default password to use.
    :param port: The default port to use.
    """

    __slots__ = ("__app", "__server", "__default_auth", "__default_port", "__running")

    def __init__(self, auth: Optional[str] = None, port: Optional[int] = None) -> None:
        self.__app = web.Application()
        self.__server = None
        self.__default_auth = auth
        self.__default_port = port
        self.__running = False

    def __repr__(self) -> str:
        return f"<Webhooks app={self.__app!r} running={self.running}>"

    def on_vote(
        self,
        route: str,
        auth: Optional[str] = None,
        callback: Optional[OnVoteCallback] = None
    ) -> Union[OnVoteCallback, OnVoteDecorator]:
        if not isinstance(route, str):
            raise TypeError("Missing route argument.")

        effective_auth = auth or self.__default_auth
        if not effective_auth:
            raise TypeError("Missing password.")

        def decorator(inner_callback: OnVoteCallback) -> RawCallback:
            async def handler(request: web.Request) -> web.Response:
                if request.headers.get("Authorization") != effective_auth:
                    return web.Response(status=401, text="Unauthorized")

                result = inner_callback(Vote(await request.json()))
                if isawaitable(result):
                    await result

                return web.Response(status=200, text="OK")

            self.__app.router.add_post(route, handler)
            return handler

        if callback:
            decorator(callback)
            return callback

        return decorator

    async def start(self, port: Optional[int] = None) -> None:
        if self.running:
            return

        port = port or self.__default_port
        if port is None:
            raise TypeError("Missing port.")

        runner = web.AppRunner(self.__app)
        await runner.setup()

        self.__server = web.TCPSite(runner, "0.0.0.0", port)
        await self.__server.start()

        self.__running = True

    async def close(self) -> None:
        if not self.running:
            return

        await self.__server.stop()
        self.__running = False

    @property
    def running(self) -> bool:
        return self.__running

    @property
    def app(self) -> web.Application:
        return self.__app

    async def __aenter__(self) -> "Webhooks":
        await self.start()
        return self

    async def __aexit__(self, *_: Any, **__: Any) -> None:
        await self.close()
