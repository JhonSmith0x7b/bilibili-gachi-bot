import asyncio
import os
import logging
import httpx
from model import Message
from common.image_utils import process_image_for_bot


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
        self.client = httpx.AsyncClient()
        
        logging.info(f"Initialized Napcat bot.")

    async def send_group_message(self, group_id: str, message: Message, at_all: bool = False) -> bool:
        success = True
        headers = {
            "Content-Type": "application/json"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        segments = []
        if at_all:
            segments.append({"type": "at", "data": {"qq": "all"}})
        
        # Original single image support (Backward compatibility)
        if message.image:
            if message.image.startswith("http"):
                processed_image = await process_image_for_bot(message.image)
                segments.append({"type": "image", "data": {"file": processed_image}})
            else:
                segments.append({"type": "image", "data": {"file": message.image}})
        
        # New multi-image support
        if hasattr(message, "images") and message.images:
            for img_url in message.images:
                if not img_url: continue
                if img_url.startswith("http"):
                    processed_image = await process_image_for_bot(img_url)
                    segments.append({"type": "image", "data": {"file": processed_image}})
                else:
                    segments.append({"type": "image", "data": {"file": img_url}})

        segments.append({"type": "text", "data": {"text": message.content[:500]}})

        payload = {
            "message_type": "group",
            "group_id": group_id,
            "message": segments,
        }

        try:
            response = await self.client.post(f"{self.base_url}/send_msg", json=payload, headers=headers)
            if response.status_code != 200:
                logging.error(f"Napcat send_group_message failed: {response.status_code} {response.text}")
                success = False
        except Exception as e:
            logging.error(f"Failed to send message to group {group_id}: {e}")
            success = False
        return success

    def run(self) -> None:
        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            logging.info("Napcat bot stopped.")
        finally:
            self.loop.run_until_complete(self.client.aclose())
            self.loop.close()
