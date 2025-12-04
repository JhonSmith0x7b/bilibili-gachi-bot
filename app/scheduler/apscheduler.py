from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from tg import TgBot
import asyncio
from crawler import PyWrightCrawler
import os
import logging


class BotPushScheduler():

    def __init__(self, bot_instance: TgBot):
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(
            self.push_schedule_task,
            trigger=IntervalTrigger(minutes=int(os.environ['CRAWL_INTERVAL_MIN'])),
            args=[bot_instance],
            id="push_message_job",
            replace_existing=True
        )
        self.crawler = PyWrightCrawler()
        self.pre_fail = ""
        

    def push_schedule_task(self, bot_instance: TgBot):
        message = self.crawler.get_new()
        if self.pre_fail == "" or message is None or message == '':
            logging.info("No new messages to push.")
        else:
            message = f"{self.pre_fail}\n{message}"
            logging.info(f"Pushing message: {message}")
            result = asyncio.run(bot_instance.send_push_message(message))
            if not result:
                self.pre_fail = message
            else:
                self.pre_fail = ""


    def start(self) -> None:
        self.scheduler.start()
