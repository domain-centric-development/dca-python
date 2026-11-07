from collections.abc import Callable
from typing import Any


class Router:
    """A stand-in for a web framework's router: get/post register a handler under a path."""

    def get(self, path: str) -> Callable[[Any], Any]:
        return lambda handler: handler

    def post(self, path: str) -> Callable[[Any], Any]:
        return lambda handler: handler


router = Router()
