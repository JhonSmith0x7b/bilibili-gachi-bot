from tg import TgBot
from crawler import PyWrightCrawler
import os
import logging
from telegram import ext


class BotPushScheduler():

    def __init__(self, bot_instance: TgBot):
        self.bot_instance = bot_instance
        self.crawler = PyWrightCrawler()
        self.pre_fail = ""
        
    async def init_task(self, context: ext.ContextTypes.DEFAULT_TYPE):
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

    async def push_schedule_task(self, context: ext.ContextTypes.DEFAULT_TYPE):
        message = await self.crawler.get_new()
        if self.pre_fail == "" and (message is None or message == ''):
            logging.info("No new messages to push.")
        else:
            if self.pre_fail:
                message = f"{self.pre_fail}\n{message}"
            logging.info(f"Pushing message: {message}")
            result = await self.bot_instance.send_push_message(message)
            if not result:
                logging.error("Failed to push message, will try again next time.")
                self.pre_fail = message
            else:
                self.pre_fail = ""

    def start(self) -> None:
        # Schedule the init task to run once when the bot starts
        self.bot_instance.app.job_queue.run_once(self.init_task, when=1)
