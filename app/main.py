import dotenv
dotenv.load_dotenv(override=True)
import logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
from tg import TgBot
from scheduler import BotPushScheduler
import os


def main() -> None:
    tg_bot = TgBot()
    bot_push_scheduler = BotPushScheduler(tg_bot)
    bot_push_scheduler.start()
    logging.info("Scheduler started.")
    logging.info("Starting Telegram bot...")
    tg_bot.run()


if __name__ == "__main__":
    main()
