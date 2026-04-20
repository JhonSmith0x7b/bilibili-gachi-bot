import json
import logging
import os
import random
import asyncio
from typing import Dict, List, Optional, Tuple
from curl_cffi.requests import AsyncSession
from common.dynamic_binding import get_dynamic_uid_group_bindings
from common.storage import SQLiteStorage
from model import Message
import re


class BilibiliDynamicCrawler:
    def __init__(self):
        self.uid_group_bindings = get_dynamic_uid_group_bindings()
        self.uids = list(self.uid_group_bindings.keys())
        
        self.buvid3 = os.environ.get("BILIBILI_DYNAMIC_BUVID3", "")
        self.buvid4 = os.environ.get("BILIBILI_DYNAMIC_BUVID4", "")
        self.sessdata = os.environ.get("BILIBILI_DYNAMIC_SESSDATA", "")
        
        self.api_url = "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history"
        
        db_path = os.path.join(os.environ.get("DATA_DIR", "./data"), "bilibili_bot.db")
        self.storage = SQLiteStorage(db_path=db_path)
        
        logging.info(f"BilibiliDynamicCrawler initialized for UIDs: {self.uids}")

    async def async_init(self):
        logging.info("Initializing BilibiliDynamicCrawler cache from DB...")
        if not self.uids:
            return
            
        async with AsyncSession(impersonate="chrome131") as session:
            for uid in self.uids:
                try:
                    # Small stagger
                    await asyncio.sleep(random.uniform(1, 3))
                    
                    headers = {
                        "Referer": f"https://space.bilibili.com/{uid}/dynamic",
                        "Cookie": f"buvid3={self.buvid3}; buvid4={self.buvid4}; SESSDATA={self.sessdata}",
                    }
                    params = {"host_uid": uid}
                    
                    response = await session.get(self.api_url, params=params, headers=headers, timeout=15.0)
                    response.raise_for_status()
                    data = response.json()
                    
                    cards = data.get("data", {}).get("cards", [])
                    for card_info in cards[:3]:
                        desc = card_info.get("desc", {})
                        dynamic_id = desc.get("dynamic_id_str") or str(desc.get("dynamic_id", "")).strip()
                        
                        if dynamic_id and not self.storage.get_dynamic(uid, dynamic_id):
                            self.storage.create_dynamic(uid, dynamic_id)
                            logging.info(f"Marked existing dynamic {dynamic_id} for UID {uid} during init.")
                            
                except Exception as e:
                    logging.error(f"Error initializing dynamic state for UID {uid}: {e}")
        logging.info("BilibiliDynamicCrawler cache initialized.")

    async def get_new(self) -> List[Tuple[str, Message]]:
        if not self.uids:
            return []

        results = []
        async with AsyncSession(impersonate="chrome131") as session:
            for uid in self.uids:
                try:
                    # Small stagger
                    await asyncio.sleep(random.uniform(1, 3))
                    
                    headers = {
                        "Referer": f"https://space.bilibili.com/{uid}/dynamic",
                        "Cookie": f"buvid3={self.buvid3}; buvid4={self.buvid4}; SESSDATA={self.sessdata}",
                    }
                    params = {"host_uid": uid}
                    
                    response = await session.get(self.api_url, params=params, headers=headers, timeout=15.0)
                    response.raise_for_status()
                    data = response.json()
                    
                    cards = data.get("data", {}).get("cards", [])
                    if not cards:
                        continue
                    
                    # We only check the most recent dynamic for simplicity in each cycle
                    # or could check top 3 to be safe
                    for card_info in reversed(cards[:3]):
                        desc = card_info.get("desc", {})
                        dynamic_id = desc.get("dynamic_id_str") or str(desc.get("dynamic_id", "")).strip()
                        
                        if not dynamic_id:
                            continue
                            
                        # Check if already processed
                        if self.storage.get_dynamic(uid, dynamic_id):
                            continue
                        
                        # Parse dynamic content
                        try:
                            card_content = json.loads(card_info.get("card", "{}"))
                        except json.JSONDecodeError:
                            continue
                        
                        dyn_type = desc.get("type")
                        message = self._parse_dynamic(card_content, dyn_type, desc, dynamic_id)
                        
                        if message:
                            results.append((uid, message))
                            # Save to DB to prevent double push
                            self.storage.create_dynamic(uid, dynamic_id)
                            logging.info(f"New dynamic detected for UID {uid}: {dynamic_id}")
                            # Only push one new dynamic per UID per cycle to avoid flooding
                            
                except Exception as e:
                    logging.error(f"Error fetching dynamic for UID {uid}: {e}")
                    
        return results

    def _parse_dynamic(self, card_content: Dict, dyn_type: int, desc: Dict, dynamic_id: str) -> Optional[Message]:
        message = Message()
        text = ""
        images = self._extract_all_images(card_content, dyn_type)
        dynamic_url = f"https://t.bilibili.com/{dynamic_id}"
        
        user_info = desc.get("user_profile", {}).get("info", {})
        uname = user_info.get("uname", "未知主播")
        
        header = f"{uname} ⚡"

        if dyn_type == 2:
            # 图文或文本
            content = card_content.get("item", {}).get("description", "").strip()
            text = f"{header}\n\n{content}\n"
        elif dyn_type == 4:
            # 纯文字动态
            content = card_content.get("item", {}).get("content", "").strip()
            text = f"{header}\n\n{content}\n"
        elif dyn_type == 1:
            # 转发
            content = card_content.get("item", {}).get("content", "").strip()
            text = f"{header}\n\n{content}\n"
        elif dyn_type == 8:
            # 视频投稿
            title = card_content.get("title", "")
            bvid = desc.get("bvid", "")
            video_url = f"https://www.bilibili.com/video/{bvid}" if bvid else "无链接"
            text = f"{header}\n新视频!!!\n标题: {title}\n链接: {video_url}\n"
        elif dyn_type == 64:
            # 专栏投稿
            title = card_content.get("title", "").strip()
            article_id = card_content.get("id")
            article_url = f"https://www.bilibili.com/read/cv{article_id}" if article_id else "无链接"
            text = f"{header}\n新专栏!!!\n标题: {title}\n链接: {article_url}\n"
        else:
            text = f"{header}\n新什么!!!\n请点击链接查看详情\n"
        text += f"\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🔗动态详情: {dynamic_url}"
        text = re.sub(r'\[[^\]]+\]', '', text)
        message.content = text
        if images:
            message.images = images
            
        return message

    def _extract_all_images(self, card_content: Dict, dyn_type: int) -> List[str]:
        images = []
        if dyn_type == 2:
            pictures = card_content.get("item", {}).get("pictures") or []
            for p in pictures:
                if p.get("img_src"): images.append(p.get("img_src"))

        elif dyn_type == 64:
            image_urls = card_content.get("image_urls") or []
            images.extend(image_urls)

        elif dyn_type == 8:
            if card_content.get("pic"): images.append(card_content.get("pic"))

        elif dyn_type == 1:
            pictures = card_content.get("item", {}).get("pictures") or []
            for p in pictures:
                if p.get("img_src"): images.append(p.get("img_src"))

            origin = card_content.get("origin")
            if origin:
                try:
                    origin_content = json.loads(origin)
                    pictures = origin_content.get("item", {}).get("pictures") or []
                    if pictures:
                        for p in pictures:
                            if p.get("img_src"): images.append(p.get("img_src"))
                    elif origin_content.get("pic"):
                        images.append(origin_content.get("pic"))
                except:
                    pass
        
        # Correct // prefix
        res = []
        for img in images:
            if img:
                if img.startswith("//"):
                    img = "https:" + img
                res.append(img)
                break
        return res
