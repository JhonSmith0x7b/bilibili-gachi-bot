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
        interval_min = int(os.environ.get('CRAWL_INTERVAL_MIN', 10))
        self.bot_instance.app.job_queue.run_repeating(
            self.push_schedule_task,
            interval=interval_min * 60,
            first=interval_min * 60,
            name="push_message_job"
        )

    async def push_schedule_task(self, context: typing.Any = None):
        pending_notification = await self.crawler.get_new()
        if not pending_notification:
            logging.info("Push task completed. No new live notification.")
            return

        room_id, live_id, message = pending_notification
        result = await self.bot_instance.send_push_message(room_id, message)
        if result:
            self.crawler.mark_notified(room_id, live_id)
            logging.info(f"Push task completed. Notification sent for room {room_id}.")
            return

        logging.warning(f"Push task failed for room {room_id}. Cache mark skipped.")


    def start(self) -> None:
        # Schedule the init task to run once when the bot starts
        self.bot_instance.app.job_queue.run_once(self.init_task, when=1)
