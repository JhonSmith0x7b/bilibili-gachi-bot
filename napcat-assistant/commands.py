"""群聊指令：在 COMMANDS 中注册新的前缀和处理函数。"""

import base64
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable


# 固定规则：北京时间、文件名为 YYYYMMDD-YYYYMMDD、起止日期均包含。
WEEKLY_FILENAME = re.compile(r"([0-9]{8})-([0-9]{8})\.(png|jpg|jpeg|webp|gif)", re.IGNORECASE)
BEIJING_TIME = timezone(timedelta(hours=8))


def weekly_image(text: str, image_dir: Path) -> list[dict]:
    missing = [{"type": "text", "data": {"text": "未发现本周周表"}}]
    today = datetime.now(BEIJING_TIME).date()
    candidates = []
    try:
        for path in image_dir.iterdir():
            match = WEEKLY_FILENAME.fullmatch(path.name)
            if not match or not path.is_file():
                continue
            try:
                start = datetime.strptime(match[1], "%Y%m%d").date()
                end = datetime.strptime(match[2], "%Y%m%d").date()
            except ValueError:
                continue
            if start <= today <= end:
                candidates.append((start, end, path.name, path))
        if not candidates:
            return missing
        # 多张有效图片时，优先开始日期最新的，再按结束日期、文件名排序。
        image = max(candidates)[3].read_bytes()
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
        return missing
    if not image:
        return missing
    encoded = base64.b64encode(image).decode("ascii")
    return [{"type": "image", "data": {"file": f"base64://{encoded}"}}]


COMMANDS: dict[str, Callable[[str, Path], list[dict]]] = {
    "周表": weekly_image,
}


def match_command(event: dict) -> tuple[str, str] | None:
    if event.get("post_type") != "message" or event.get("message_type") != "group":
        return None
    self_id = event.get("self_id")
    if self_id is None or str(event.get("user_id")) == str(self_id):
        return None
    if event.get("group_id") is None or event.get("message_id") is None:
        return None
    segments = event.get("message")
    if not isinstance(segments, list):
        return None  # NapCat 必须配置 messagePostFormat=array。
    mentioned = False
    texts = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        data = segment.get("data") or {}
        if not isinstance(data, dict):
            continue
        if segment.get("type") == "at" and str(data.get("qq")) == str(self_id):
            mentioned = True
        elif segment.get("type") == "text" and isinstance(data.get("text"), str):
            texts.append(data["text"])
    if mentioned:
        text = "".join(texts).lstrip()
        for prefix in COMMANDS:
            if text.startswith(prefix):
                return prefix, text
    return None
