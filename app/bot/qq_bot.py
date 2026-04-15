import asyncio
import os
import logging
import httpx
from config import get_live_room_group_bindings
from model import Message


class NapcatJobQueue:
    def __init__(self, loop):
        self.loop = loop

    def run_repeating(self, callback, interval, first=None, name=None):
        async def task():
            if first:
                await asyncio.sleep(first)
            while True:
                try:
                    await callback(None)
                except Exception as e:
                    logging.error(f"Task {name} error: {e}")
                await asyncio.sleep(interval)
        self.loop.create_task(task())

    def run_once(self, callback, when=None):
        async def task():
            if when:
                await asyncio.sleep(when)
            try:
                await callback(None)
            except Exception as e:
                logging.error(f"Task error: {e}")
        self.loop.create_task(task())


class MockApp:
    def __init__(self, loop):
        self.job_queue = NapcatJobQueue(loop)


class NapcatBot:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.app = MockApp(self.loop)   
        self.base_url = os.environ.get('NAPCAT_API_BASE_URL', 'http://127.0.0.1:3000').rstrip('/')
        self.token = os.environ.get('NAPCAT_API_TOKEN', '')
        self.room_group_bindings = get_live_room_group_bindings()
        
        logging.info(f"Loaded Napcat bindings for {len(self.room_group_bindings)} room(s).")

    async def send_push_message(self, room_id: str, message: Message) -> bool:
        group_targets = self.room_group_bindings.get(room_id, [])
        if not group_targets:
            logging.warning(f"No bound Napcat group IDs configured for room {room_id}. Skipping push message.")
            return True
            
        success = True
        async with httpx.AsyncClient() as client:
            headers = {
                "Content-Type": "application/json"
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
                
            for group_target in group_targets:
                segments = []
                if group_target["at_all"]:
                    segments.append({"type": "at", "data": {"qq": "all"}})
                if message.image:
                    segments.append({"type": "image", "data": {"file": message.image}})
                segments.append({"type": "text", "data": {"text": message.content[:500]}})

                payload = {
                    "message_type": "group",
                    "group_id": group_target["group_id"],
                    "message": segments,
                }
                try:
                    response = await client.post(f"{self.base_url}/send_msg", json=payload, headers=headers)
                    if response.status_code != 200:
                        logging.error(f"Napcat send failed: {response.status_code} {response.text}")
                        success = False
                except Exception as e:
                    logging.error(f"Failed to send message to group {group_target['group_id']} for room {room_id}: {e}")
                    success = False
        return success

    def run(self) -> None:
        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            logging.info("Napcat bot stopped.")
        finally:
            self.loop.close()
