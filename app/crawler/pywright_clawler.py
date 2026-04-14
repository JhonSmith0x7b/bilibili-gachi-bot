from playwright.async_api import async_playwright, BrowserContext
from playwright_stealth import Stealth
from bs4 import BeautifulSoup, Tag
import logging
import asyncio
from collections import deque
import os
from typing import List
import traceback
import random


class PyWrightCrawler():

    def __init__(self):
        self.cache_dict = {}
        self.bilibili_uids = [uid.strip() for uid in os.environ['BILIBILI_UIDS'].split(",") if uid.strip()]
        if len(self.bilibili_uids) == 0:
            error = "BILIBILI_UIDS is not set or empty."
            logging.error(error)
            raise Exception(error)
        
        self.launch_options = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--disable-infobars"
            ]
        }
        self.context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "permissions": ["geolocation"],
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }

    async def async_init(self):
        logging.info("Initializing crawler cache for UIDs: %s", self.bilibili_uids)
        async with Stealth().use_async(async_playwright()) as p:
            browser = await p.chromium.launch(**self.launch_options)
            context = await browser.new_context(**self.context_options)
            try:
                queue = deque([(uid, 0) for uid in self.bilibili_uids])
                processed_count = 0
                while queue:
                    uid, retry_count = queue.popleft()
                    
                    if processed_count > 0:
                        delay = random.uniform(5, 10)
                        logging.info(f"Waiting {delay:.2f}s before processing UID {uid}...")
                        await asyncio.sleep(delay)
                    
                    result = await self.fetch_bilibili_dynamic_data(context, uid, retry_count)
                    processed_count += 1

                    if not result and retry_count < 1:
                        logging.warning(f"Failed to fetch {uid} during init, deferring to queue tail for retry 1.")
                        queue.append((uid, retry_count + 1))
                    else:
                        self.cache_dict[uid] = deque(result, maxlen=30)
                        
                logging.info(f"Cache initialized for {len(self.cache_dict)} UIDs.")
            except Exception as e:
                logging.error(f"Error during async_init: {e}")
                traceback.print_exc()
            finally:
                await browser.close()

    async def get_new(self) -> str:
        re_messages = []
        async with Stealth().use_async(async_playwright()) as p:
            browser = await p.chromium.launch(**self.launch_options)
            context = await browser.new_context(**self.context_options)
            try:
                queue = deque([(uid, 0) for uid in self.bilibili_uids])
                processed_count = 0
                
                while queue:
                    uid, retry_count = queue.popleft()
                    
                    if processed_count > 0:
                        delay = random.uniform(1, 10)
                        logging.info(f"Waiting {delay:.2f}s before processing UID {uid}...")
                        await asyncio.sleep(delay)
                    
                    result = await self.fetch_bilibili_dynamic_data(context, uid, retry_count)
                    processed_count += 1

                    if not result and retry_count < 1:
                        logging.warning(f"Failed to fetch {uid}, deferring to queue tail for retry 1.")
                        queue.append((uid, retry_count + 1))
                        continue

                    new_data = [f"https://space.bilibili.com/{uid}/dynamic"]
                    cache = self.cache_dict.get(uid, deque(maxlen=30))
                    added_new = False
                    for row in result:
                        if row is None or row in new_data or row in cache:
                            continue
                        new_data.append(row)
                        cache.append(row)
                        added_new = True
                    
                    if added_new:
                        self.cache_dict[uid] = cache
                        re_messages.append("\n-----------------\n".join(new_data))
                
                return "\n\n\n".join(re_messages)
            except Exception as e:
                logging.error(f"Error in get_new: {e}")
                traceback.print_exc()
                return ""
            finally:
                await browser.close()

    async def fetch_bilibili_dynamic_data(self, context: BrowserContext, uid: str, retry_count: int = 0) -> List[str]:
        page = None
        try:
            # If retry, go to main space first to simulate referral
            if retry_count > 0:
                page = await context.new_page()
                space_url = f"https://space.bilibili.com/{uid}"
                logging.info(f"Retrying {uid}: visiting space first {space_url}")
                await page.goto(space_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(random.uniform(2, 4))
                url = f"https://space.bilibili.com/{uid}/dynamic"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            else:
                url = f"https://space.bilibili.com/{uid}/dynamic"
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Resource Interception
            async def block_resources(route):
                if route.request.resource_type in ["image", "media", "font", "other"]:
                    await route.abort()
                else:
                    await route.continue_()
            
            await page.route("**/*", block_resources)
            
            # Wait for dynamic list to appear
            try:
                await page.wait_for_selector("div.bili-dyn-list__items", timeout=15000)
            except Exception:
                logging.warning(f"Timeout waiting for dynamic list for {uid} (Retry: {retry_count}).")
                # Even if selector fails, we attempt to get content in case it's a different layout
            
            # simulate human wait and small scroll
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await page.mouse.wheel(0, 500)
            
            # Small extra wait for content to populate
            await asyncio.sleep(1)
            
            content = await page.content()
            
            # pick dynamic
            soup = BeautifulSoup(content, "html.parser")
            div_elements = soup.select(
                "div.bili-dyn-list__items > div.bili-dyn-list__item")
            
            if not div_elements:
                logging.warning(f"No dynamic items found for {uid} (Retry: {retry_count}).")
                return []
                
            logging.info(f"Fetched {len(div_elements)} dynamics for {uid}.")
            re_list = []
            for div in div_elements:
                parts = []
                # content
                content_text = self.pick_text(div, "div.bili-rich-text__content")
                parts.append(content_text)
                # card opus
                card = self.pick_text(div, "div.dyn-card-opus__summary")
                parts.append(card[:30])
                # video title
                video_title = self.pick_text(div, "div.bili-dyn-card-video__title")
                parts.append(video_title)
                # live title
                live_title = self.pick_text(div, "div.bili-dyn-card-live__title")
                if live_title:
                    parts.append(f"LIVE! {live_title}")
                
                cleaned_parts = [p.strip() for p in parts if p and p.strip()]
                if cleaned_parts:
                    re_list.append(" -- ".join(cleaned_parts))
            return re_list
        except Exception as e:
            logging.error(f"Error fetching Bilibili dynamic data for {uid} (Retry: {retry_count}): {e}")
            return []
        finally: 
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    def pick_text(self, div: Tag, selector: str) -> str:
        elements = div.select(selector)
        return "".join([el.get_text(strip=True) for el in elements])
