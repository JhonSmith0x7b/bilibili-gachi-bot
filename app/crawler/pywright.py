from playwright.async_api import async_playwright
from bs4 import BeautifulSoup, Tag
import logging
import asyncio
from collections import deque
import os
from typing import Iterable, List
import traceback
import time


class PyWrightCrawler():

    def __init__(self):
        self.cache_dict = {}
        self.bilibili_uids = os.environ['BILIBILI_UIDS'].split(",")
        if len(self.bilibili_uids) == 0:
            error = "BILIBILI_UIDS is not set or empty."
            logging.error(error)
            raise Exception(error)
        for uid in self.bilibili_uids:
            result = asyncio.run(self.fetch_bilibili_dynamic_data(uid))
            self.cache_dict[uid] = deque(result, maxlen=30)
        logging.info(f"cache is \n{str(self.cache_dict)}")

    def get_new(self) -> str:
        re_messages = []
        for uid in self.bilibili_uids:
            result = asyncio.run(self.fetch_bilibili_dynamic_data(uid))
            new_data = [f"https://space.bilibili.com/{uid}/dynamic"]
            cache = self.cache_dict[uid]
            for row in result:
                if row is None or row in new_data or row in cache:
                    continue
                new_data.append(row)
                cache.append(row)
            if len(new_data) < 2:
                continue
            self.cache_dict[uid] = cache
            re_messages.append("\n-----------------\n".join(new_data))
            time.sleep(3)
        return "\n\n\n".join(re_messages)

    async def fetch_bilibili_dynamic_data(self, uid: str) -> List[str]:
        try:
            url = f"https://space.bilibili.com/{uid}/dynamic"
            async with async_playwright() as p:
                launch_options = {
                    "headless": True,
                    "args": [
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-extensions",
                        "--disable-infobars",
                        "--start-maximized"
                    ]
                }
                browser = await p.chromium.launch(**launch_options)
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1,
                    is_mobile=False,
                    has_touch=False,
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
                )
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    // disable WebGL
                    WebGLRenderingContext.prototype.getParameter = () => null;
                    WebGL2RenderingContext.prototype.getParameter = () => null;
                """)
                page = await context.new_page()
                await page.goto(url)
                await page.wait_for_load_state("networkidle")
                content = await page.content()
                await browser.close()
                # pick dynamic
                soup = BeautifulSoup(content, "html.parser")
                div_elements = soup.select(
                    "div.bili-dyn-list__items > div.bili-dyn-list__item")
                re_list = []
                for div in div_elements:
                    parts = []
                    content = self.pick_text(
                        div, "div.bili-rich-text__content")
                    parts.append(content)
                    card = self.pick_text(div, "div.dyn-card-opus__summary")
                    parts.append(card[:30])
                    video_title = self.pick_text(
                        div, "div.bili-dyn-card-video__title")
                    parts.append(video_title)
                    live_title = self.pick_text(
                        div, "div.bili-dyn-card-live__title"
                    )
                    if live_title is not None and live_title != "":
                        parts.append(f"LIVE! {live_title}")
                    re_list.append(" -- ".join(filter(str.strip, parts)))
                return re_list
        except Exception as e:
            logging.error(f"Error fetching Bilibili dynamic data: {e}")
            traceback.print_exc()
            return []
        finally: 
            try:
                await browser.close()
            except Exception as e:
                pass

    def pick_text(self, div: Tag, selector: str) -> str:
        text = div.select(selector)
        result = ""
        for row in text:
            row = row.get_text(strip=True)
            result += row
        return result
