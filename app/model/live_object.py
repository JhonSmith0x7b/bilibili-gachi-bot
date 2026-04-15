from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl


class PendantInfo(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    desc: Optional[str] = None

class Pendants(BaseModel):
    frame: Optional[PendantInfo] = None

class RoomInfo(BaseModel):
    uid: Optional[int] = None
    room_id: Optional[int] = None
    short_id: Optional[int] = None
    title: Optional[str] = None
    cover: Optional[str] = None
    tags: Optional[str] = None
    background: Optional[str] = None
    description: Optional[str] = None
    live_status: Optional[int] = None
    live_start_time: Optional[int] = None
    area_id: Optional[int] = None
    area_name: Optional[str] = None
    parent_area_id: Optional[int] = None
    parent_area_name: Optional[str] = None
    keyframe: Optional[str] = None
    is_studio: Optional[bool] = None
    pendants: Optional[Pendants] = None
    online: Optional[int] = None

class OfficialInfo(BaseModel):
    role: Optional[int] = None
    title: Optional[str] = None
    desc: Optional[str] = None
    is_nft: Optional[int] = None

class AnchorBaseInfo(BaseModel):
    uname: Optional[str] = None
    face: Optional[str] = None
    gender: Optional[str] = None
    official_info: Optional[OfficialInfo] = None

class AnchorLiveInfo(BaseModel):
    level: Optional[int] = None
    score: Optional[int] = None
    rank: Optional[str] = None

class AnchorInfo(BaseModel):
    base_info: Optional[AnchorBaseInfo] = None
    live_info: Optional[AnchorLiveInfo] = None
    relation_info: Optional[Dict[str, Any]] = None
    medal_info: Optional[Dict[str, Any]] = None

class NewsInfo(BaseModel):
    uid: Optional[int] = None
    ctime: Optional[str] = None
    content: Optional[str] = None

class LikeInfoV3(BaseModel):
    total_likes: Optional[int] = None
    click_block: Optional[bool] = None
    guild_emo_text: Optional[str] = None
    hand_icons: Optional[List[str]] = None
    dm_icons: Optional[List[str]] = None

class PopularRankInfo(BaseModel):
    rank: Optional[int] = None
    rank_name: Optional[str] = None
    url: Optional[str] = None

class SwitchInfo(BaseModel):
    close_guard: Optional[bool] = None
    close_gift: Optional[bool] = None
    close_online: Optional[bool] = None
    close_danmaku: Optional[bool] = None

class ModuleControlInfos(BaseModel):
    display_right_interaction_modules: Optional[bool] = None
    cmd_list: Optional[List[str]] = None

# --- 主模型 ---

class BilibiliLiveRoomData(BaseModel):
    room_info: Optional[RoomInfo] = None
    anchor_info: Optional[AnchorInfo] = None
    news_info: Optional[NewsInfo] = None
    rankdb_info: Optional[Dict[str, Any]] = None
    area_rank_info: Optional[Dict[str, Any]] = None
    tab_info: Optional[Dict[str, Any]] = None
    voice_join_info: Optional[Dict[str, Any]] = None
    switch_info: Optional[SwitchInfo] = None
    new_switch_info: Optional[Dict[str, int]] = None
    super_chat_info: Optional[Dict[str, Any]] = None
    like_info_v3: Optional[LikeInfoV3] = None
    popular_rank_info: Optional[PopularRankInfo] = None
    module_control_infos: Optional[ModuleControlInfos] = None
    
    # 允许包含未定义的额外字段（可选）
    model_config = {"extra": "ignore"}
