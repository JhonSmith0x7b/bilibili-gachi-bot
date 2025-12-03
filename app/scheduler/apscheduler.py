from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from tg import TgBot
import asyncio
from crawler import PyWrightCrawler


class BotPushScheduler():

    def __init__(self, bot_instance: TgBot):
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(
            self.push_schedule_task,
            trigger=IntervalTrigger(minutes=1),
            args=[bot_instance],
            id="push_message_job",
            replace_existing=True
        )
        self.crawler = PyWrightCrawler()
        

    def push_schedule_task(self, bot_instance: TgBot):
        message = self.crawler.get_new()
        asyncio.run(bot_instance.send_push_message(message))


    def start(self) -> None:
        self.scheduler.start()
