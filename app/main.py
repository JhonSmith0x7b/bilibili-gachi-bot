import dotenv
dotenv.load_dotenv(override=True)
import logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
from scheduler import BotPushScheduler
import os


def main() -> None:
    bot_type = os.environ.get('BOT_TYPE', 'tg').lower()
    
    if bot_type == 'napcat':
        from bot.qq.bot import NapcatBot
        bot = NapcatBot()
    else:
        from bot.tg import TgBot
        bot = TgBot()

    bot_push_scheduler = BotPushScheduler(bot)
    bot_push_scheduler.start()
    logging.info("Scheduler started.")
    logging.info(f"Starting {bot_type} bot...")
    bot.run()


if __name__ == "__main__":
    main()
