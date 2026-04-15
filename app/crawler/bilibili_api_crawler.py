import logging
import asyncio
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import random
from bilibili_api import live, Credential
from config import get_live_room_group_bindings
from model import BilibiliLiveRoomData, Message


@dataclass
class RoomLiveState:
    status: str = "offline"
    current_live_id: Optional[str] = None
    last_live_id: Optional[str] = None
    last_status_change_at: float = 0.0
    last_push_attempt_at: float = 0.0
    retry_count: int = 0


class BilibiliApiCrawler:
    def __init__(self):
        self.room_states: Dict[str, RoomLiveState] = {}
        self.room_group_bindings = get_live_room_group_bindings()
        self.bilibili_room_ids = list(self.room_group_bindings.keys())
        self.request_timeout = float(os.environ.get("BILIBILI_API_TIMEOUT", "6"))
        self.max_retries = int(os.environ.get("BILIBILI_API_MAX_RETRIES", "3"))
        self.retry_base_delay = float(os.environ.get("BILIBILI_API_RETRY_DELAY", "1"))
        self.credential = Credential(
            buvid3 = os.environ.get("BILIBILI_BUVID3", "96F51D3A-AF11-5C4F-9ECE-A1F42BD2509117059infoc")
            )
        
        if not self.bilibili_room_ids:
            error = "No Bilibili room bindings configured."
            logging.error(error)
            raise Exception(error)
        
        from bilibili_api import select_client, request_settings
        select_client("curl_cffi")
        request_settings.set("impersonate", "chrome131")
        request_settings.set_trust_env(False)
        request_settings.set_proxy("")
        request_settings.set_timeout(self.request_timeout)
        logging.info(f"BilibiliApiCrawler initialized for Room IDs: {self.bilibili_room_ids}")

    async def async_init(self):
        logging.info("Initializing BilibiliApiCrawler room states...")
        for i, room_id in enumerate(self.bilibili_room_ids):
            if i > 0:
                await asyncio.sleep(random.uniform(2, 5))
            state = self.room_states.setdefault(room_id, RoomLiveState())
            try:
                live_data = await self.fetch_live_room_info(room_id)
                if live_data and live_data.room_info:
                    room_info = live_data.room_info
                    current_live_id = self._build_live_id(room_info)
                    if room_info.live_status == 1 and current_live_id:
                        self._transition_to_pending(state, room_id, current_live_id, reason="startup_live_detected")
                        continue
                self._transition_to_offline(state, room_id, reason="startup_offline")
            except Exception as e:
                logging.error(f"Error initializing state for Room {room_id}: {e}")
                self._transition_to_offline(state, room_id, reason="startup_error")

    async def get_new(self) -> Optional[Tuple[str, str, Message]]:
        for i, room_id in enumerate(self.bilibili_room_ids):
            if i > 0:
                await asyncio.sleep(random.uniform(2, 5))
            state = self.room_states.setdefault(room_id, RoomLiveState())
            try:
                live_data = await self.fetch_live_room_info(room_id)
                logging.debug(f"Fetched live data for Room {room_id}: {live_data}")
                if not live_data or not live_data.room_info:
                    continue

                room_info = live_data.room_info
                if room_info.live_status != 1:
                    self._transition_to_offline(state, room_id, reason="live_ended")
                    continue

                current_live_id = self._build_live_id(room_info)
                if not current_live_id:
                    logging.warning(f"Skip Room {room_id}: missing live identifier.")
                    continue

                if state.current_live_id != current_live_id:
                    self._transition_to_pending(state, room_id, current_live_id, reason="new_live_detected")
                elif state.status == "live_pushed":
                    continue

                message = self.parse_live_info(live_data)
                if not message or not message.content:
                    continue

                state.last_push_attempt_at = time.time()
                state.retry_count += 1
                logging.info(f"Pending live notification detected for Room {room_id}: {current_live_id}")
                return room_id, current_live_id, message
            except Exception as e:
                logging.error(f"Error fetching live info for Room {room_id}: {e}")
        return None

    def mark_notified(self, room_id: str, live_id: str) -> None:
        state = self.room_states.setdefault(room_id, RoomLiveState())
        if state.current_live_id != live_id:
            logging.warning(
                "Marked room %s as notified with mismatched live_id. current=%s incoming=%s",
                room_id,
                state.current_live_id,
                live_id,
            )
            state.current_live_id = live_id

        state.status = "live_pushed"
        state.last_live_id = live_id
        state.last_status_change_at = time.time()
        logging.info(
            "Marked live notification as sent for Room %s: %s (retry_count=%s)",
            room_id,
            live_id,
            state.retry_count,
        )

    def _build_live_id(self, room_info) -> str:
        return str(room_info.live_start_time or room_info.room_id or "")

    def _transition_to_pending(
        self,
        state: RoomLiveState,
        room_id: str,
        live_id: str,
        reason: str,
    ) -> None:
        previous_status = state.status
        previous_live_id = state.current_live_id
        state.status = "live_pending"
        state.current_live_id = live_id
        state.last_status_change_at = time.time()
        state.last_push_attempt_at = 0.0
        state.retry_count = 0
        logging.info(
            "Room %s state transition: %s/%s -> %s/%s (%s)",
            room_id,
            previous_status,
            previous_live_id,
            state.status,
            state.current_live_id,
            reason,
        )

    def _transition_to_offline(self, state: RoomLiveState, room_id: str, reason: str) -> None:
        if state.status == "offline" and state.current_live_id is None:
            return

        previous_status = state.status
        previous_live_id = state.current_live_id
        state.status = "offline"
        state.current_live_id = None
        state.last_status_change_at = time.time()
        state.last_push_attempt_at = 0.0
        state.retry_count = 0
        logging.info(
            "Room %s state transition: %s/%s -> %s/%s (%s)",
            room_id,
            previous_status,
            previous_live_id,
            state.status,
            state.current_live_id,
            reason,
        )

    async def fetch_live_room_info(self, room_id: str) -> Optional[BilibiliLiveRoomData]:
        for attempt in range(1, self.max_retries + 1):
            try:
                live_object = live.LiveRoom(room_id, self.credential)
                raw_data = await live_object.get_room_info()
                return BilibiliLiveRoomData.model_validate(raw_data)
            except Exception as e:
                if attempt >= self.max_retries:
                    logging.error(
                        f"Request failed for room {room_id} after {attempt} attempts: {e}"
                    )
                    break

                delay = self.retry_base_delay * attempt
                logging.warning(
                    f"Request failed for room {room_id} on attempt {attempt}/{self.max_retries}: {e}. "
                    f"Retrying in {delay:.1f}s."
                )
                await asyncio.sleep(delay)
        return None

    def parse_live_info(self, data: BilibiliLiveRoomData) -> Message:
        try:
            r = data.room_info
            a = data.anchor_info.base_info if data.anchor_info else None
            
            if not r:
                return ""
            message = Message()
            uname = a.uname if a else "未知主播"
            title = r.title or "无标题"
            room_id = r.room_id or "未知ID"
            cover = r.cover or ""
            
            msg = f"【直播提醒】\n"
            msg += f"主播: {uname}\n"
            msg += f"标题: {title}\n"
            msg += f"链接: https://live.bilibili.com/{room_id}\n"
            message.content = msg
            if cover:
                message.image = cover
            return message
        except Exception as e:
            logging.warning(f"Error parsing live info model: {e}")
            return ""
