from crawler import BilibiliApiCrawler
import os
import logging
import typing


class BotPushScheduler():

    def __init__(self, bot_instance: typing.Any):
        self.bot_instance = bot_instance
        crawler_type = os.environ.get('CRAWLER_TYPE', 'playwright').lower()
        if crawler_type == 'api':
            logging.info("Using BilibiliApiCrawler")
            self.crawler = BilibiliApiCrawler()
        else:
            logging.info("Using BilibiliApiCrawler")
            self.crawler = BilibiliApiCrawler()        
        
    async def init_task(self, context: typing.Any = None):
        logging.info("Initializing crawler cache...")
        await self.crawler.async_init()
        logging.info("Crawler cache initialized. Starting scheduled push task.")
        
        manager_group_id = os.environ.get("MANAGER_GROUP_ID")
        if manager_group_id:
            try:
                from model import Message
                msg = Message()
                msg.content = "Bilibili Gachi Bot 已启动并开始监听直播状态。"
                if hasattr(self.bot_instance, "send_group_message"):
                    await self.bot_instance.send_group_message(manager_group_id, msg)
                    logging.info(f"Startup message sent to manager group {manager_group_id}.")
            except Exception as e:
                logging.error(f"Failed to send startup message: {e}")

        interval_min = int(os.environ.get('CRAWL_INTERVAL_MIN', 10))
        self.bot_instance.app.job_queue.run_repeating(
            self.push_schedule_task,
            interval=interval_min * 60,
            first=interval_min * 60,
            name="push_message_job"
        )

    async def push_schedule_task(self, context: typing.Any = None):
        pending_notifications = await self.crawler.get_new()
        if not pending_notifications:
            logging.info("Push task completed. No new live notification.")
            return

        for room_id, live_id, message in pending_notifications:
            result = await self.bot_instance.send_push_message(room_id, message)
            if result:
                self.crawler.mark_notified(room_id, live_id)
                logging.info(f"Push task completed. Notification sent for room {room_id}.")
            else:
                logging.warning(f"Push task failed for room {room_id}. Cache mark skipped.")


    def start(self) -> None:
        # Schedule the init task to run once when the bot starts
        self.bot_instance.app.job_queue.run_once(self.init_task, when=1)
