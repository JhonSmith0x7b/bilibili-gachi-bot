import os
from telegram import Update
from telegram import ext
from util import SqlalchemyHelper, BotUser
import logging


class TgBot():

    def __init__(self):
        self.user_chat_ids = set()
        if os.environ.get('TG_API_BASE_URL') is not None:
            self.app = ext.ApplicationBuilder().token(
                os.environ['TG_BOT_TOKEN']).base_url(os.environ['TG_API_BASE_URL']).build()
        else:
            self.app = ext.ApplicationBuilder().token(
                os.environ['TG_BOT_TOKEN']).build()
        self.app.add_handler(ext.CommandHandler("update", self.update))
        self.sqlalchemy_helper = SqlalchemyHelper(os.environ['PG_URL'])
        all_users = self.sqlalchemy_helper.get_all_bot_user()
        for user in all_users:
            logging.info(f"Loaded user: {user.name}, chat_id: {user.chat_id}")
            self.user_chat_ids.add(user.chat_id)

    async def update(self, update: Update, context: ext.ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id  # type: ignore
        username = update.effective_user.id  # type: ignore
        bot_user = BotUser(
            name=username,
            chat_id=chat_id
        )
        re_message = ""
        if self.sqlalchemy_helper.add_bot_user(bot_user):
            re_message = "You have been registered successfully!"
            self.user_chat_ids.add(chat_id)
        else:
            re_message = "Registration failed. You might be already registered."
        await update.message.reply_text(re_message)  # type: ignore

    async def send_push_message(self, message: str) -> None:
        for chat_id in self.user_chat_ids:
            try:
                await self.app.bot.send_message(chat_id=chat_id, text=message[:500])
            except Exception as e:
                print(f"Failed to send message to {chat_id}: {e}")

    def run(self) -> None:
        self.app.run_polling()
