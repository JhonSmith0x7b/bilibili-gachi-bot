from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl


class Message(BaseModel):
    content: Optional[str] = None
    image: Optional[str] = None