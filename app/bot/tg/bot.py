import os
from telegram import Update
from telegram import ext
import logging
import tenacity


class TgBot():

    def __init__(self):
        chat_ids_str = os.environ.get('TG_CHAT_IDS', '')
        self.user_chat_ids = {int(cid.strip()) for cid in chat_ids_str.split(',') if cid.strip().isdigit()}
        
        if os.environ.get('TG_API_BASE_URL') is not None:
            self.app = ext.ApplicationBuilder().token(
                os.environ['TG_BOT_TOKEN']).base_url(os.environ['TG_API_BASE_URL']).build()
        else:
            self.app = ext.ApplicationBuilder().token(
                os.environ['TG_BOT_TOKEN']).build()
        self.app.add_handler(ext.CommandHandler("update", self.update))

        logging.info(f"Loaded {len(self.user_chat_ids)} chat IDs from config.")

    async def update(self, update: Update, context: ext.ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id  # type: ignore
        re_message = f"Your chat ID is: {chat_id}\nPlease add it to TG_CHAT_IDS in your .env file to receive pushes."
        await update.message.reply_text(re_message)  # type: ignore

    @tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(2),
                    retry=tenacity.retry_if_result(lambda result: result is False), before_sleep=lambda retry_state: logging.warning(
        f"Push failed, retrying in 3s... (Attempt {retry_state.attempt_number})"
    ))
    async def send_push_message(self, message: str) -> bool:
        if not self.user_chat_ids:
            logging.warning("No TG_CHAT_IDS configured. Skipping push message.")
            return True
            
        for chat_id in self.user_chat_ids:
            try:
                await self.app.bot.send_message(chat_id=chat_id, text=message[:500])
            except Exception as e:
                logging.error(f"Failed to send message to {chat_id}: {e}")
                return False
        return True

    def run(self) -> None:
        self.app.run_polling()
