import logging
import asyncio
import os
import time
import json
import random
from typing import Dict, List, Optional, Tuple
from bilibili_api import live, Credential
from common.live_binding import get_live_room_group_bindings
from model import BilibiliLiveRoomData, Message
from common.storage import SQLiteStorage


class BilibiliApiCrawler:
    def __init__(self):
        self.room_group_bindings = get_live_room_group_bindings()
        self.bilibili_room_ids = list(self.room_group_bindings.keys())
        self.request_timeout = float(os.environ.get("BILIBILI_API_TIMEOUT", "6"))
        self.max_retries = int(os.environ.get("BILIBILI_API_MAX_RETRIES", "3"))
        self.retry_base_delay = float(os.environ.get("BILIBILI_API_RETRY_DELAY", "1"))
        self.credential = Credential(
            buvid3 = os.environ.get("BILIBILI_BUVID3", "96F51D3A-AF11-5C4F-9ECE-A1F42BD2509117059infoc")
            )
        
        db_path = os.path.join(os.environ.get("DATA_DIR", "./data"), "bilibili_bot.db")
        self.storage = SQLiteStorage(db_path=db_path)

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
        logging.info("Initializing BilibiliApiCrawler room states from DB...")
        for i, room_id in enumerate(self.bilibili_room_ids):
            if i > 0:
                await asyncio.sleep(random.uniform(2, 5))
            try:
                live_data = await self.fetch_live_room_info(room_id)
                if live_data and live_data.room_info:
                    room_info = live_data.room_info
                    current_live_id = self._build_live_id(room_info)
                    if room_info.live_status == 1 and current_live_id:
                        # Check if session already recorded
                        session = self.storage.get_session(room_id, current_live_id)
                        if not session:
                            self.storage.create_session(
                                room_id=room_id,
                                live_id=current_live_id,
                                title=room_info.title or "",
                                cover=room_info.cover or "",
                                start_time=room_info.live_start_time or 0,
                                status="notified",  # Mark as notified on startup to prevent spam
                                extra=live_data.model_dump()
                            )
                            logging.info(f"Room {room_id} is currently live. Marked as already notified in DB.")
            except Exception as e:
                logging.error(f"Error initializing state for Room {room_id}: {e}")

    async def get_new(self) -> List[Tuple[str, str, Message]]:
        semaphore = asyncio.Semaphore(2)  # Limit concurrency to 2
        
        async def _process_room(room_id: str) -> Optional[Tuple[str, str, Message]]:
            async with semaphore:
                # Small stagger to avoid hitting API exactly at the same time
                await asyncio.sleep(random.uniform(0, 1))
                try:
                    live_data = await self.fetch_live_room_info(room_id)
                    logging.debug(f"Fetched live data for Room {room_id}: {live_data}")
                    if not live_data or not live_data.room_info:
                        return None

                    room_info = live_data.room_info
                    if room_info.live_status != 1:
                        # Mark active session as ended if offline
                        self.storage.mark_session_ended(room_id, int(time.time()))
                        return None

                    current_live_id = self._build_live_id(room_info)
                    if not current_live_id:
                        logging.warning(f"Skip Room {room_id}: missing live identifier.")
                        return None

                    session = self.storage.get_session(room_id, current_live_id)
                    if not session:
                        # New live session detected
                        self.storage.create_session(
                            room_id=room_id,
                            live_id=current_live_id,
                            title=room_info.title or "",
                            cover=room_info.cover or "",
                            start_time=room_info.live_start_time or 0,
                            status="pending",
                            extra=live_data.model_dump()
                        )
                        session = self.storage.get_session(room_id, current_live_id)

                    # 1. Check if already notified or failed
                    if session["status"] == "notified":
                        return None
                    if session["status"] in ("failed", "skipped"):
                        return None

                    # 2. Increment retry count in DB
                    retry_count = self.storage.increment_retry_count(room_id, current_live_id)
                    
                    # 3. Check for max retries to avoid head-of-line blocking
                    if retry_count > 3:
                        logging.warning(f"Room {room_id} exceeded retry limit for live {current_live_id}. Marking as failed.")
                        self.storage.update_session_status(room_id, current_live_id, "failed")
                        return None

                    message = self.parse_live_info(live_data)
                    if not message or not message.content:
                        return None

                    logging.info(f"New live detected for Room {room_id}: {current_live_id} (attempt {retry_count})")
                    return room_id, current_live_id, message
                except Exception as e:
                    logging.error(f"Error fetching live info for Room {room_id}: {e}")
                    return None

        tasks = [_process_room(room_id) for room_id in self.bilibili_room_ids]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]

    def mark_notified(self, room_id: str, live_id: str) -> None:
        self.storage.update_session_status(room_id, live_id, "notified")
        logging.info(f"Marked Room {room_id} as notified for live {live_id} in DB.")

    def _build_live_id(self, room_info) -> str:
        return str(room_info.live_start_time or room_info.room_id or "")

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

    def parse_live_info(self, data: BilibiliLiveRoomData) -> Optional[Message]:
        try:
            r = data.room_info
            a = data.anchor_info.base_info if data.anchor_info else None
            
            if not r:
                return None
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
