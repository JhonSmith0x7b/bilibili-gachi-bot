import os
import logging
from typing import Optional
from bilibili_api import Credential
from common.storage import SQLiteStorage



class CredentialManager:
    def __init__(self, storage: SQLiteStorage, env_key: str = "BILIBILI_SESSDATA", buvid3_key: str = "BILIBILI_BUVID3"):
        self.storage = storage
        self.env_key = env_key
        self.buvid3_key = buvid3_key
        
        # Parse comma-separated SESSDATA values from environment
        raw_sessdata = os.environ.get(env_key, "").strip()
        self.sessdata_pool = [s.strip() for s in raw_sessdata.split(",") if s.strip()]
        if not self.sessdata_pool:
            self.sessdata_pool = [""]
            
        self.buvid3 = os.environ.get(buvid3_key, "").strip()
        if not self.buvid3 and buvid3_key == "BILIBILI_DYNAMIC_BUVID3":
            self.buvid3 = os.environ.get("BILIBILI_BUVID3", "").strip()
        if not self.buvid3:
            self.buvid3 = "96F51D3A-AF11-5C4F-9ECE-A1F42BD2509117059infoc"
            
        # Retrieve last active index from SQLite storage
        self.storage_key = f"active_sessdata_index_{env_key}"
        saved_index = self.storage.get_config(self.storage_key)
        try:
            self.current_index = int(saved_index) if saved_index is not None else 0
        except ValueError:
            self.current_index = 0
            
        if self.current_index >= len(self.sessdata_pool) or self.current_index < 0:
            self.current_index = 0
            
        logging.info(
            f"🔑【凭证池加载完成】{env_key} 当前凭证池总数: {len(self.sessdata_pool)} 个 | 当前正在生效使用的凭证索引: [{self.current_index}]"
        )

    def get_credential(self) -> Credential:
        current_sessdata = self.sessdata_pool[self.current_index]
        return Credential(sessdata=current_sessdata, buvid3=self.buvid3)

    def rotate(self, failed_index: Optional[int] = None) -> Credential:
        if len(self.sessdata_pool) <= 1:
            logging.warning(
                f"⚠️【凭证切换提示】配置项 [{self.env_key}] 仅配置了 1 个 SESSDATA 凭证，触发切换无法轮询到新凭证！建议在 .env 中使用英文逗号配置多个备用值。"
            )
            return self.get_credential()
            
        # 如果传入了失败时的索引，且当前索引已经改变（说明已有其他并发任务完成了切换），则无需再次切换，直接复用当前最新凭证
        if failed_index is not None and failed_index != self.current_index:
            logging.warning(
                f"⚠️【协同凭证复用】[{self.env_key}] 检测到已有并发任务触发完轮询切换（旧索引 {failed_index} -> 新索引 {self.current_index}），当前请求自动协同协同复用新凭证！"
            )
            return self.get_credential()
            
        old_index = self.current_index
        self.current_index = (self.current_index + 1) % len(self.sessdata_pool)
        self.storage.set_config(self.storage_key, str(self.current_index))
        
        logging.warning(
            f"⚠️【触发凭证轮询切换】[{self.env_key}] 监控调用报错！已自动将 SESSDATA 从旧索引 [{old_index}] 切换至新备用凭证 [新索引 {self.current_index} / 共 {len(self.sessdata_pool)} 个]。"
            f"新位点已持久化至数据库，接下来的任务和后续调度均直接生效此凭证！"
        )
        return self.get_credential()


