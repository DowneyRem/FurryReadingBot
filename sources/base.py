from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Novel:
    """全平台统一小说模型。"""
    id: str
    title: str
    author_id: str
    author_name: str
    content: str
    tags: list[str] = field(default_factory=list)
    description: str = ""
    series_id: str | None = None
    series_title: str | None = None
    source: str = ""
    url: str = ""
    create_date: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class NovelSource(ABC):
    name: str

    @abstractmethod
    def can_handle(self, text: str) -> bool:
        """文本/链接是否属于本源。"""

    @abstractmethod
    async def fetch(self, text: str) -> Novel:
        """拉取并解析为一篇 Novel（单篇）。"""

    async def fetch_series(self, text: str) -> list[Novel]:
        raise NotImplementedError(f"{self.name} 暂不支持系列")

    async def fetch_author_novels(self, text: str) -> list[Novel]:
        raise NotImplementedError(f"{self.name} 暂不支持作者全部")