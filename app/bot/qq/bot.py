import asyncio
import os
import logging
import httpx


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
        group_ids_str = os.environ.get('NAPCAT_GROUP_IDS', '')
        self.group_ids = [gid.strip() for gid in group_ids_str.split(',') if gid.strip()]
        
        logging.info(f"Loaded {len(self.group_ids)} Napcat group IDs from config.")

    async def send_push_message(self, message: str) -> bool:
        if not self.group_ids:
            logging.warning("No NAPCAT_GROUP_IDS configured. Skipping push message.")
            return True
            
        success = True
        async with httpx.AsyncClient() as client:
            headers = {
                "Content-Type": "application/json"
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
                
            for group_id in self.group_ids:
                payload = {
                    "message_type": "group",
                    "group_id": group_id,
                    "message": [
                        {"type": "at", "data": {"qq": "all"}},
                        {"type": "text", "data": {"text": f" {message[:500]}"}}
                    ]
                }
                try:
                    response = await client.post(f"{self.base_url}/send_msg", json=payload, headers=headers)
                    if response.status_code != 200:
                        logging.error(f"Napcat send failed: {response.status_code} {response.text}")
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
            self.loop.close()