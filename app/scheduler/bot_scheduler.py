from crawler import BilibiliApiCrawler
from crawler.bilibili_dynamic_crawler import BilibiliDynamicCrawler
import os
import logging
import typing
import asyncio


class BotPushScheduler():

    def __init__(self, bot_instance: typing.Any):
        self.bot_instance = bot_instance
        self.enable_live = os.environ.get('ENABLE_LIVE_MONITOR', 'true').lower() == 'true'
        self.enable_dynamic = os.environ.get('ENABLE_DYNAMIC_MONITOR', 'true').lower() == 'true'
        
        if self.enable_live:
            crawler_type = os.environ.get('CRAWLER_TYPE', 'playwright').lower()
            if crawler_type == 'api':
                logging.info("Using BilibiliApiCrawler for live monitoring")
                self.crawler = BilibiliApiCrawler()
            else:
                logging.info("Using BilibiliApiCrawler for live monitoring")
                self.crawler = BilibiliApiCrawler()
        else:
            self.crawler = None
            logging.info("Live monitor is disabled.")
        
        if self.enable_dynamic:
            self.dynamic_crawler = BilibiliDynamicCrawler()
            logging.info("Dynamic monitor is enabled.")
        else:
            self.dynamic_crawler = None
            logging.info("Dynamic monitor is disabled.")
        
    async def init_task(self, context: typing.Any = None):
        if self.enable_live and self.crawler:
            logging.info("Initializing live crawler cache...")
            await self.crawler.async_init()
            logging.info("Live crawler cache initialized.")
            
        if self.enable_dynamic and self.dynamic_crawler:
            logging.info("Initializing dynamic crawler cache...")
            await self.dynamic_crawler.async_init()
            logging.info("Dynamic crawler cache initialized.")
        
        manager_group_id = os.environ.get("MANAGER_GROUP_ID")
        if manager_group_id:
            try:
                from model import Message
                msg = Message()
                
                status_msg = []
                if self.enable_live: status_msg.append("直播")
                if self.enable_dynamic: status_msg.append("动态")
                monitor_status = "和".join(status_msg) if status_msg else "无"
                
                msg.content = f"Bilibili Gachi Bot 已启动并开始监听{monitor_status}状态。"
                if hasattr(self.bot_instance, "send_group_message"):
                    await self.bot_instance.send_group_message(manager_group_id, msg)
                    logging.info(f"Startup message sent to manager group {manager_group_id}.")
            except Exception as e:
                logging.error(f"Failed to send startup message: {e}")

        if self.enable_live:
            interval_min = int(os.environ.get('CRAWL_INTERVAL_MIN', 10))
            self.bot_instance.app.job_queue.run_repeating(
                self.push_schedule_task,
                interval=interval_min * 60,
                first=interval_min * 60,
                name="push_message_job"
            )
        
        if self.enable_dynamic:
            interval_dynamic = int(os.environ.get('CRAWL_DYNAMIC_INTERVAL_MIN', 10))
            self.bot_instance.app.job_queue.run_repeating(
                self.dynamic_schedule_task,
                interval=interval_dynamic * 60,
                first=interval_dynamic * 60,
                name="dynamic_message_job"
            )

    async def push_schedule_task(self, context: typing.Any = None):
        if not self.enable_live or not self.crawler:
            return
        pending_notifications = await self.crawler.get_new()
        if not pending_notifications:
            logging.info("Push task completed. No new live notification.")
            return

        for room_id, live_id, message in pending_notifications:
            targets = self.crawler.room_group_bindings.get(room_id, [])
            if not targets:
                logging.warning(f"No bound group IDs configured for room {room_id}. Skipping push.")
                self.crawler.mark_notified(room_id, live_id)
                continue

            success = True
            for target in targets:
                group_id = target["group_id"]
                try:
                    if hasattr(self.bot_instance, "send_group_message"):
                        res = await self.bot_instance.send_group_message(group_id, message, at_all=target.get("at_all", False))
                        if not res:
                            success = False
                        else:
                            logging.info(f"Live notification sent for room {room_id} to group {group_id}.")
                        await asyncio.sleep(2)
                except Exception as e:
                    logging.error(f"Failed to send live notification for room {room_id} to group {group_id}: {e}")
                    success = False

            if success:
                self.crawler.mark_notified(room_id, live_id)
                logging.info(f"Push task completed. Notification sent for room {room_id}.")
            else:
                logging.warning(f"Push task failed for room {room_id}. Cache mark skipped.")

    async def dynamic_schedule_task(self, context: typing.Any = None):
        if not self.enable_dynamic or not self.dynamic_crawler:
            return
        new_dynamics = await self.dynamic_crawler.get_new()
        if not new_dynamics:
            logging.info("Dynamic push task completed. No new dynamic.")
            return

        for uid, message in new_dynamics:
            # We need to send dynamic message to multiple groups bound to this UID
            targets = self.dynamic_crawler.uid_group_bindings.get(uid, [])
            for target in targets:
                group_id = target["group_id"]
                try:
                    if hasattr(self.bot_instance, "send_group_message"):
                        await self.bot_instance.send_group_message(group_id, message, at_all=target.get("at_all", False))
                        logging.info(f"Dynamic sent for UID {uid} to group {group_id}.")
                        await asyncio.sleep(2)
                except Exception as e:
                    logging.error(f"Failed to send dynamic for UID {uid} to group {group_id}: {e}")


    def start(self) -> None:
        # Schedule the init task to run once when the bot starts
        self.bot_instance.app.job_queue.run_once(self.init_task, when=1)
