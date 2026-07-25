import json
import logging
import os
import random
import asyncio
from typing import Dict, List, Optional, Tuple
import re

from bilibili_api import user, Credential
from common.dynamic_binding import get_dynamic_uid_group_bindings
from common.storage import SQLiteStorage
from model import Message
from common.credential import CredentialManager



class BilibiliDynamicCrawler:
    def __init__(self):
        self.uid_group_bindings = get_dynamic_uid_group_bindings()
        self.uids = list(self.uid_group_bindings.keys())
        
        self.request_timeout = float(os.environ.get("BILIBILI_API_TIMEOUT", "15.0"))
        self.max_retries = int(os.environ.get("BILIBILI_API_MAX_RETRIES", "3"))
        self.retry_base_delay = float(os.environ.get("BILIBILI_API_RETRY_DELAY", "2"))
        
        db_path = os.path.join(os.environ.get("DATA_DIR", "./data"), "bilibili_bot.db")
        self.storage = SQLiteStorage(db_path=db_path)
        
        sessdata_key = "BILIBILI_DYNAMIC_SESSDATA" if os.environ.get("BILIBILI_DYNAMIC_SESSDATA", "").strip() else "BILIBILI_SESSDATA"
        buvid3_key = "BILIBILI_DYNAMIC_BUVID3" if os.environ.get("BILIBILI_DYNAMIC_BUVID3", "").strip() else "BILIBILI_BUVID3"
        self.cred_manager = CredentialManager(storage=self.storage, env_key=sessdata_key, buvid3_key=buvid3_key)
        self.credential = self.cred_manager.get_credential()

        
        from bilibili_api import select_client, request_settings
        select_client("curl_cffi")
        request_settings.set("impersonate", "chrome131")
        request_settings.set_trust_env(False)
        request_settings.set_proxy("")
        request_settings.set_timeout(self.request_timeout)
        
        logging.info(f"BilibiliDynamicCrawler initialized for UIDs: {self.uids}")

    async def async_init(self):
        logging.info("Initializing BilibiliDynamicCrawler cache from DB...")
        if not self.uids:
            return
            
        for i, uid in enumerate(self.uids):
            for attempt in range(1, self.max_retries + 1):
                try:
                    # Stagger to protect from rate limits / anti-crawler
                    if i > 0 and attempt == 1:
                        await asyncio.sleep(random.uniform(8, 12))
                    
                    attempt_index = self.cred_manager.current_index
                    self.credential = self.cred_manager.get_credential()
                    u = user.User(uid=int(uid), credential=self.credential)
                    res = await u.get_dynamics_new()
                    cards = res.get("items", [])
                    
                    for card_info in cards[:3]:
                        dynamic_id = card_info.get("id_str")
                        if dynamic_id and not self.storage.get_dynamic(uid, dynamic_id):
                            self.storage.create_dynamic(uid, dynamic_id)
                            logging.info(f"Marked existing dynamic {dynamic_id} for UID {uid} during init.")
                    break
                except Exception as e:
                    self.credential = self.cred_manager.rotate(attempt_index)
                    if attempt >= self.max_retries:
                        logging.error(f"❌【动态初始化拉取失败】UID {uid} 连续重试 {attempt} 次及自动切换凭证后仍无法获取: {e}。已终止初始化！")
                        break
                    delay = self.retry_base_delay * attempt
                    logging.warning(f"⚠️【动态接口初始化异常】UID {uid} 请求报错 (尝试 {attempt}/{self.max_retries}): {e}。已触发 SESSDATA 切换，将在 {delay:.1f} 秒后使用新凭证重试！")
                    await asyncio.sleep(delay)

        logging.info("BilibiliDynamicCrawler cache initialized.")

    async def get_new(self) -> List[Tuple[str, Message]]:
        if not self.uids:
            return []

        results = []
        for i, uid in enumerate(self.uids):
            for attempt in range(1, self.max_retries + 1):
                try:
                    # Stagger to protect from rate limits / anti-crawler
                    if i > 0 and attempt == 1:
                        await asyncio.sleep(random.uniform(8, 12))
                    
                    attempt_index = self.cred_manager.current_index
                    self.credential = self.cred_manager.get_credential()
                    u = user.User(uid=int(uid), credential=self.credential)
                    res = await u.get_dynamics_new()
                    cards = res.get("items", [])
                    
                    if not cards:
                        break
                    
                    # Check top 3 to be safe, reversed (from oldest to newest)
                    for card_info in reversed(cards[:3]):
                        dynamic_id = card_info.get("id_str")
                        if not dynamic_id:
                            continue
                            
                        # Check if already processed
                        if self.storage.get_dynamic(uid, dynamic_id):
                            continue
                        
                        message = self._parse_dynamic(card_info)
                        
                        if message:
                            results.append((uid, message))
                            # Save to DB to prevent double push
                            self.storage.create_dynamic(uid, dynamic_id)
                            logging.info(f"New dynamic detected for UID {uid}: {dynamic_id}")
                    break
                except Exception as e:
                    self.credential = self.cred_manager.rotate(attempt_index)
                    if attempt >= self.max_retries:
                        logging.error(f"❌【动态监控拉取失败】UID {uid} 连续重试 {attempt} 次及自动切换凭证后仍无法成功请求: {e}。已终止当前重试循环！")
                        break
                    delay = self.retry_base_delay * attempt
                    logging.warning(f"⚠️【动态更新拉取异常】UID {uid} 请求报错 (尝试 {attempt}/{self.max_retries}): {e}。已触发 SESSDATA 轮询切换，将在 {delay:.1f} 秒后使用新凭证重试！")
                    await asyncio.sleep(delay)

                
        return results

    def _extract_all_images(self, item: Dict) -> List[str]:
        images = []
        modules = item.get("modules", {})
        module_dynamic = modules.get("module_dynamic", {})
        major = module_dynamic.get("major", {}) if module_dynamic else {}
        
        if major:
            m_type = major.get("type")
            if m_type == "MAJOR_TYPE_OPUS":
                pics = major.get("opus", {}).get("pics") or []
                for p in pics:
                    if p.get("url"):
                        images.append(p.get("url"))
            elif m_type == "MAJOR_TYPE_DRAW":
                pics = major.get("draw", {}).get("items") or []
                for p in pics:
                    if p.get("src"):
                        images.append(p.get("src"))
                    elif p.get("url"):
                        images.append(p.get("url"))
            elif m_type == "MAJOR_TYPE_ARCHIVE":
                pic = major.get("archive", {}).get("pic")
                if pic:
                    images.append(pic)
            elif m_type == "MAJOR_TYPE_ARTICLE":
                covers = major.get("article", {}).get("covers") or []
                images.extend(covers)

        if item.get("type") == "DYNAMIC_TYPE_FORWARD":
            orig = item.get("orig")
            if orig:
                orig_images = self._extract_all_images(orig)
                images.extend(orig_images)
                
        res = []
        for img in images:
            if img:
                if img.startswith("//"):
                    img = "https:" + img
                res.append(img)
                break
        return res

    def _parse_dynamic(self, item: Dict) -> Optional[Message]:
        message = Message()
        dynamic_id = item.get("id_str")
        if not dynamic_id:
            return None
            
        dynamic_url = f"https://t.bilibili.com/{dynamic_id}"
        
        modules = item.get("modules", {})
        author_info = modules.get("module_author", {})
        uname = author_info.get("name", "未知主播")
        header = f"{uname} ⚡"
        
        dyn_type = item.get("type")
        module_dynamic = modules.get("module_dynamic", {})
        
        desc_text = ""
        if module_dynamic and module_dynamic.get("desc"):
            desc_text = module_dynamic.get("desc", {}).get("text", "").strip()
            
        major = module_dynamic.get("major", {}) if module_dynamic else {}
        major_type = major.get("type") if major else None
        
        opus_text = ""
        if major_type == "MAJOR_TYPE_OPUS":
            opus_text = major.get("opus", {}).get("summary", {}).get("text", "").strip()
            
        self_text = desc_text or opus_text
        
        images = self._extract_all_images(item)
        
        if dyn_type == "DYNAMIC_TYPE_FORWARD":
            text = f"{header}\n\n{self_text}\n"
            orig = item.get("orig")
            if orig:
                orig_modules = orig.get("modules", {})
                orig_author = orig_modules.get("module_author", {})
                orig_uname = orig_author.get("name", "未知用户")
                
                orig_dyn = orig_modules.get("module_dynamic", {})
                orig_desc = orig_dyn.get("desc", {}).get("text", "").strip() if (orig_dyn and orig_dyn.get("desc")) else ""
                orig_major = orig_dyn.get("major", {}) if orig_dyn else {}
                orig_major_type = orig_major.get("type") if orig_major else None
                
                orig_self_text = orig_desc
                if orig_major_type == "MAJOR_TYPE_OPUS":
                    orig_self_text = orig_self_text or orig_major.get("opus", {}).get("summary", {}).get("text", "").strip()
                
                if orig.get("type") == "DYNAMIC_TYPE_AV":
                    archive = orig_major.get("archive", {})
                    v_title = archive.get("title", "")
                    bvid = archive.get("bvid", "")
                    video_url = f"https://www.bilibili.com/video/{bvid}" if bvid else "无链接"
                    text += f"\n➡️ 转发自 {orig_uname} 的视频:\n标题: {v_title}\n链接: {video_url}\n"
                elif orig.get("type") == "DYNAMIC_TYPE_ARTICLE":
                    article = orig_major.get("article", {})
                    a_title = article.get("title", "")
                    article_id = article.get("id")
                    article_url = f"https://www.bilibili.com/read/cv{article_id}" if article_id else "无链接"
                    text += f"\n➡️ 转发自 {orig_uname} 的专栏:\n标题: {a_title}\n链接: {article_url}\n"
                else:
                    text += f"\n➡️ 转发自 {orig_uname} :\n{orig_self_text}\n"
                    
        elif dyn_type == "DYNAMIC_TYPE_AV":
            archive = major.get("archive", {})
            title = archive.get("title", "")
            bvid = archive.get("bvid", "")
            video_url = f"https://www.bilibili.com/video/{bvid}" if bvid else "无链接"
            text = f"{header}\n新视频!!!\n标题: {title}\n链接: {video_url}\n"
            
        elif dyn_type == "DYNAMIC_TYPE_ARTICLE":
            article = major.get("article", {})
            title = article.get("title", "").strip()
            article_id = article.get("id")
            article_url = f"https://www.bilibili.com/read/cv{article_id}" if article_id else "无链接"
            text = f"{header}\n新专栏!!!\n标题: {title}\n链接: {article_url}\n"
            
        elif dyn_type in ("DYNAMIC_TYPE_DRAW", "DYNAMIC_TYPE_WORD"):
            text = f"{header}\n\n{self_text}\n"
            
        else:
            if self_text:
                text = f"{header}\n\n{self_text}\n"
            else:
                text = f"{header}\n新内容!!!\n请点击链接查看详情\n"
                
        text += f"\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🔗动态详情: {dynamic_url}"
        text = re.sub(r'\[[^\]]+\]', ' ', text)
        message.content = text
        if images:
            message.images = images
            
        return message
