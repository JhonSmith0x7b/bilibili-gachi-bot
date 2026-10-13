"""独立 NapCat 群聊助手，不依赖 B 站机器人。"""

import asyncio
import json
import logging
import os
import signal
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from commands import COMMANDS, match_command

RECONNECT_DELAY = 5


@dataclass(frozen=True)
class Config:
    http_url: str
    ws_url: str
    api_token: str
    ws_token: str
    image_dir: Path
    cooldown: float = 5

    @classmethod
    def from_env(cls):
        api_token = os.environ.get("NAPCAT_API_TOKEN", "").strip()
        ws_token = os.environ.get("NAPCAT_WS_TOKEN", "").strip() or api_token
        if not api_token or not ws_token:
            raise ValueError("Configure NAPCAT_API_TOKEN and the NapCat WebSocket token")
        cooldown = float(os.environ.get("COMMAND_COOLDOWN_SECONDS", "5"))
        if not 0 <= cooldown < float("inf"):
            raise ValueError("COMMAND_COOLDOWN_SECONDS must be finite and nonnegative")
        return cls(
            http_url=os.environ.get("NAPCAT_API_BASE_URL", "http://napcat:3000").rstrip("/"),
            ws_url=os.environ.get("NAPCAT_WS_URL", "ws://napcat:3001"),
            api_token=api_token,
            ws_token=ws_token,
            image_dir=Path(os.environ.get("WEEKLY_IMAGE_DIR", "/data")),
            cooldown=cooldown,
        )


class Assistant:
    def __init__(self, config: Config, client: httpx.AsyncClient):
        self.config = config
        self.client = client
        self.seen: OrderedDict[tuple, None] = OrderedDict()
        self.last_sent: dict[tuple, float] = {}

    def remember(self, key: tuple):
        self.seen[key] = None
        if len(self.seen) > 4096:
            self.seen.popitem(last=False)

    async def handle(self, event: dict):
        match = match_command(event)
        if match is None:
            return
        prefix, text = match
        key = (str(event["self_id"]), str(event["group_id"]), str(event["message_id"]))
        if key in self.seen:
            return
        now = time.monotonic()
        self.last_sent = {k: t for k, t in self.last_sent.items() if now - t < self.config.cooldown}
        cooldown_key = (key[0], key[1], prefix)
        if cooldown_key in self.last_sent:
            self.remember(key)
            return
        try:
            message = await asyncio.to_thread(COMMANDS[prefix], text, self.config.image_dir)
            response = await self.client.post(
                self.config.http_url + "/send_group_msg",
                headers={"Authorization": f"Bearer {self.config.api_token}"},
                json={"group_id": event["group_id"], "message": message},
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get("status") != "ok" or result.get("retcode") != 0:
                logging.error("Command %s rejected by NapCat", prefix)
                return
        except (OSError, ValueError, httpx.HTTPError) as exc:
            # 不记录消息正文、图片数据、Token 或 HTTP 响应体。
            logging.error("Command %s failed (%s)", prefix, type(exc).__name__)
            return
        self.remember(key)
        self.last_sent[cooldown_key] = time.monotonic()
        logging.info("Command %s reply sent", prefix)


async def listen(config: Config, assistant: Assistant):
    while True:
        try:
            async with connect(
                config.ws_url,
                additional_headers={"Authorization": f"Bearer {config.ws_token}"},
                proxy=None,
                open_timeout=10,
                max_size=4 * 1024 * 1024,
            ) as websocket:
                logging.info("Connected to NapCat; listening for group mentions")
                async for raw in websocket:
                    try:
                        event = json.loads(raw)
                    except (ValueError, UnicodeError):
                        logging.warning("Ignored invalid event JSON")
                        continue
                    if isinstance(event, dict):
                        await assistant.handle(event)
                logging.error("NapCat WebSocket closed; reconnecting")
        except (OSError, TimeoutError, WebSocketException) as exc:
            logging.error("NapCat connection interrupted (%s)", type(exc).__name__)
        logging.info("Reconnecting in %s seconds", RECONNECT_DELAY)
        await asyncio.sleep(RECONNECT_DELAY)


async def main():
    config = Config.from_env()
    if not config.image_dir.is_dir():
        logging.warning("Weekly image directory missing; configure WEEKLY_IMAGE_DIR")
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, task.cancel)
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        await listen(config, Assistant(config, client))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
