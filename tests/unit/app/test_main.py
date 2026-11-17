"""Unit tests for main.py."""

import logging
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import Request, Response
from starlette.responses import StreamingResponse

from ols import config

# needs to be setup there before is_user_authorized is imported
config.ols_config.authentication_config.module = "k8s"

from ols.app.main import log_requests_responses  # noqa: E402  # pylint: disable=C0413


def _build_request(
    path: str = "/v1/query",
    body: bytes = b'{"query":"hello"}',
    headers: list[tuple[bytes, bytes]] | None = None,
    client: tuple[str, int] | None = ("127.0.0.1", 54321),
) -> Request:
    """Build an ASGI HTTP Request object for middleware unit tests."""
    raw_headers = (
        headers
        if headers is not None
        else [
            (b"content-type", b"application/json"),
            (b"authorization", b"Bearer secret"),
        ]
    )
    scope: dict[str, Any] = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": raw_headers,
        "client": client,
    }
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_log_requests_responses_non_streaming_debug() -> None:
    """Test debug logging middleware with a non-streaming Response."""
    config.reload_from_yaml_file("tests/config/test_app_endpoints.yaml")
    request = _build_request()

    async def call_next(_req: Request) -> Any:
        return Response(
            content=b'{"ok":true}',
            status_code=201,
            headers={"X-Custom-Header": "preserved"},
            media_type="application/json",
        )

    with patch("ols.app.main.logger") as mock_logger:
        mock_logger.isEnabledFor.return_value = True
        wrapped = await log_requests_responses(request, call_next)
        chunks = [chunk async for chunk in wrapped.body_iterator]

    assert isinstance(wrapped, StreamingResponse)
    assert chunks == [b'{"ok":true}']
    assert wrapped.status_code == 201
    assert wrapped.headers["x-custom-header"] == "preserved"
    assert wrapped.media_type == "application/json"
    mock_logger.isEnabledFor.assert_called_once_with(logging.DEBUG)
    assert any(
        call.args
        and call.args[0] == "Response to %s:%d Body chunk: %s}"
        and call.args[3] == '{"ok":true}'
        for call in mock_logger.debug.call_args_list
    )


@pytest.mark.asyncio
async def test_log_requests_responses_streaming_debug() -> None:
    """Test debug logging middleware with an async StreamingResponse."""
    config.reload_from_yaml_file("tests/config/test_app_endpoints.yaml")
    request = _build_request(body=b"", client=None)

    async def body_stream() -> AsyncGenerator[bytes, None]:
        yield b"data: part-1\n\n"
        yield b"data: part-2\n\n"

    async def call_next(_req: Request) -> StreamingResponse:
        return StreamingResponse(
            body_stream(),
            status_code=200,
            media_type="text/event-stream",
        )

    with patch("ols.app.main.logger") as mock_logger:
        mock_logger.isEnabledFor.return_value = True
        wrapped = await log_requests_responses(request, call_next)
        chunks = [chunk async for chunk in wrapped.body_iterator]

    assert chunks == [b"data: part-1\n\n", b"data: part-2\n\n"]
    assert wrapped.status_code == 200
    assert wrapped.media_type == "text/event-stream"
    logged_chunks = [
        call.args[3]
        for call in mock_logger.debug.call_args_list
        if len(call.args) == 4 and call.args[0] == "Response to %s:%d Body chunk: %s}"
    ]
    assert logged_chunks == ["data: part-1\n\n", "data: part-2\n\n"]


@pytest.mark.asyncio
async def test_log_requests_responses_skips_when_debug_disabled() -> None:
    """Test middleware returns response untouched when DEBUG logging is disabled."""
    config.reload_from_yaml_file("tests/config/test_app_endpoints.yaml")
    request = _build_request()
    original_response = Response(content=b'{"ok":true}', status_code=201)

    async def call_next(_req: Request) -> Any:
        return original_response

    with patch("ols.app.main.logger") as mock_logger:
        mock_logger.isEnabledFor.return_value = False
        result = await log_requests_responses(request, call_next)

    assert result is original_response
    mock_logger.debug.assert_not_called()
