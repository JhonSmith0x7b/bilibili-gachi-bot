import dotenv
dotenv.load_dotenv(override=True)
import logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
from scheduler import BotPushScheduler
import os
from bot import NapcatBot


def main() -> None:
    bot_type = os.environ.get('BOT_TYPE', 'napcat').lower()
    
    if bot_type == 'napcat':
        bot = NapcatBot()
    else:
        bot = NapcatBot()

    bot_push_scheduler = BotPushScheduler(bot)
    bot_push_scheduler.start()
    logging.info("Scheduler started.")
    logging.info(f"Starting {bot_type} bot...")
    bot.run()


if __name__ == "__main__":
    main()
