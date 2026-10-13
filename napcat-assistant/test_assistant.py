import asyncio
import base64
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import httpx
from websockets.asyncio.server import serve

from commands import BEIJING_TIME, match_command, weekly_image
from main import Assistant, Config, listen


def event(text="周表", mention="123", message_id=1, group_id=456, **overrides):
    return {
        "post_type": "message", "message_type": "group", "self_id": 123,
        "user_id": 789, "message_id": message_id, "group_id": group_id,
        "message": [{"type": "at", "data": {"qq": mention}},
                    {"type": "text", "data": {"text": text}}],
        **overrides,
    }


class MatchingTests(unittest.TestCase):
    def test_prefix_and_real_mention(self):
        for text in ["周表", "  周表看看", "\n周表"]:
            with self.subTest(text=text):
                self.assertEqual(match_command(event(text))[0], "周表")
        for value in [event("看看周表"), event(mention="999"), event(mention="all"),
                      event(user_id=123), event(message_type="private"),
                      event(post_type="meta_event"), event(message_id=None),
                      event(message="[CQ:at,qq=123]周表"), event(self_id=None)]:
            self.assertIsNone(match_command(value))

    def test_trailing_mention_and_split_text(self):
        value = event()
        value["message"] = [
            {"type": "text", "data": {"text": "周"}},
            {"type": "text", "data": {"text": "表 "}},
            {"type": "at", "data": {"qq": 123}},
        ]
        self.assertEqual(match_command(value), ("周表", "周表 "))


class AssistantTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clock = patch("commands.datetime", wraps=datetime)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        self.clock.now.return_value = datetime(2026, 10, 13, tzinfo=BEIJING_TIME)
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "20261013-20261020.png"
        self.path.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1sAAAAASUVORK5CYII="
        ))
        self.requests = []
        self.response_body = {"status": "ok", "retcode": 0, "data": {"message_id": 99}}
        self.status = 200

        def respond(request):
            self.requests.append(request)
            return httpx.Response(self.status, json=self.response_body)

        self.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        self.config = Config("http://napcat:3000", "ws://napcat:3001", "api-secret",
                             "ws-secret", self.path.parent, cooldown=5)
        self.assistant = Assistant(self.config, self.client)

    async def asyncTearDown(self):
        await self.client.aclose()
        self.temp.cleanup()

    async def test_image_send_duplicate_and_group_cooldown(self):
        await self.assistant.handle(event())
        await self.assistant.handle(event())
        await self.assistant.handle(event(message_id=2))
        await self.assistant.handle(event(message_id=3, group_id=987))
        self.assertEqual(len(self.requests), 2)
        request = self.requests[0]
        self.assertEqual(request.headers["Authorization"], "Bearer api-secret")
        self.assertEqual(request.url.path, "/send_group_msg")
        payload = json.loads(request.content)
        self.assertEqual(payload["group_id"], 456)
        self.assertEqual(len(payload["message"]), 1)
        self.assertEqual(base64.b64decode(payload["message"][0]["data"]["file"][9:]),
                         self.path.read_bytes())

    async def test_business_and_http_failure_do_not_mark_success(self):
        self.response_body = {"status": "failed", "retcode": 1200}
        await self.assistant.handle(event())
        self.assertFalse(self.assistant.seen)
        self.assertFalse(self.assistant.last_sent)
        self.status = 500
        await self.assistant.handle(event())
        self.assertFalse(self.assistant.seen)
        self.status = 200
        self.response_body = {"status": "ok", "retcode": 0}
        await self.assistant.handle(event())
        self.assertEqual(len(self.assistant.seen), 1)

    async def test_missing_image_recovers_and_replacement_is_loaded(self):
        self.assistant.config = replace(self.config, cooldown=0)
        self.path.unlink()
        await self.assistant.handle(event())
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(json.loads(self.requests[-1].content)["message"],
                         [{"type": "text", "data": {"text": "未发现本周周表"}}])
        self.path.write_bytes(b"replacement-image")
        await self.assistant.handle(event(message_id=2))
        self.assertEqual(len(self.requests), 2)
        self.path.write_bytes(b"next-image")
        await self.assistant.handle(event(message_id=3, group_id=987))
        payload = json.loads(self.requests[-1].content)
        self.assertEqual(base64.b64decode(payload["message"][0]["data"]["file"][9:]), b"next-image")

    async def test_malformed_api_response_does_not_stop_listener(self):
        for result in [None, [], "unexpected"]:
            self.response_body = result
            await self.assistant.handle(event())
            self.assertFalse(self.assistant.seen)

    async def test_date_boundaries_and_beijing_timezone(self):
        for day, expected in [(12, "text"), (13, "image"), (20, "image"), (21, "text")]:
            with self.subTest(day=day):
                self.clock.now.return_value = datetime(2026, 10, day, tzinfo=BEIJING_TIME)
                result = weekly_image("周表", self.path.parent)
                self.assertEqual(result[0]["type"], expected)
                self.clock.now.assert_called_with(BEIJING_TIME)

    async def test_invalid_names_dates_and_missing_directory(self):
        self.path.unlink()
        for name in ["weekly.png", "20260230-20261020.png", "20261020-20261013.png",
                     "20261013-20261020.txt", "周表20261013-20261020.png"]:
            (self.path.parent / name).write_bytes(b"old")
        (self.path.parent / "20261013-20261020.jpg").mkdir()
        for directory in [self.path.parent, self.path.parent / "absent"]:
            self.assertEqual(weekly_image("周表", directory),
                             [{"type": "text", "data": {"text": "未发现本周周表"}}])
        await self.assistant.handle(event())
        self.assertEqual(json.loads(self.requests[-1].content)["message"][0]["data"]["text"],
                         "未发现本周周表")

    async def test_overlapping_ranges_choose_latest_start(self):
        (self.path.parent / "20261001-20261031.JPG").write_bytes(b"older")
        result = weekly_image("周表", self.path.parent)
        self.assertEqual(base64.b64decode(result[0]["data"]["file"][9:]), self.path.read_bytes())
        self.path.write_bytes(b"")
        self.assertEqual(weekly_image("周表", self.path.parent)[0]["type"], "text")

    async def test_websocket_events_auth_and_reconnect(self):
        connections = []
        delivered = asyncio.Event()

        async def server(socket):
            connections.append(socket.request.headers.get("Authorization"))
            await socket.send("not json")
            await socket.send(json.dumps({"post_type": "meta_event"}))
            # 第二次连接先重复上报，再发送一个不同群的新指令。
            await socket.send(json.dumps(event()))
            if len(connections) > 1:
                await socket.send(json.dumps(event(message_id=2, group_id=987)))
                while len(self.requests) < 2:
                    await asyncio.sleep(0.01)
                delivered.set()
                await socket.wait_closed()

        async with serve(server, "127.0.0.1", 0) as ws_server:
            port = ws_server.sockets[0].getsockname()[1]
            config = replace(self.config, ws_url=f"ws://127.0.0.1:{port}")
            with patch("main.RECONNECT_DELAY", 0.01):
                task = asyncio.create_task(listen(config, self.assistant))
                try:
                    await asyncio.wait_for(delivered.wait(), timeout=5)
                finally:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
        self.assertEqual(connections, ["Bearer ws-secret", "Bearer ws-secret"])
        self.assertEqual(len(self.requests), 2)


if __name__ == "__main__":
    unittest.main()
