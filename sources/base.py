from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Novel:
	novel_id: str
	novel_title: str
	series_id: str | None
	series_title: str | None
	author_id: str
	author_name: str
	
	caption: str
	content: str
	like_count: int
	read_count: int
	create_date: str
	tags: list[str] = field(default_factory=list)
	images: dict[str, Any] = field(default_factory=dict)

	source: str = ""
	url: str = ""
	raw: dict[str, Any] = field(default_factory=dict)
	
	# ----- 别名：兼容旧代码里的 .id / .title -----
	@property
	def id(self) -> str:
		return self.novel_id
	
	@property
	def title(self) -> str:
		return self.novel_title
	
	@id.setter
	def id(self, value: str) -> None:
		self.novel_id = value
	
	@title.setter
	def title(self, value: str) -> None:
		self.novel_title = value
	
	def __str__(self):
		return f"{self.title}\n作者：{self.author_name}\n标签：#{" #".join(self.tags).strip()}"
	def __repr__(self):
		return f"{self.source}Source({self.url})"


@dataclass
class Series:
	novel_id: str
	novel_title: str
	series_id: str | None
	series_title: str | None
	author_id: str
	author_name: str
	
	caption: str = ""
	tags: list[str] = field(default_factory=list)
	total: int = 0
	novel_ids: list[str] = field(default_factory=list)
	novel_titles: list[str] = field(default_factory=list)

	source: str = ""
	url: str = ""
	novel_url: str = ""
	raw: dict[str, Any] = field(default_factory=dict)
	
	# ----- 别名：兼容旧代码里的 .id / .title -----
	@property
	def id(self) -> str:
		return self.series_id
	
	@property
	def title(self) -> str:
		return self.series_title
	
	@id.setter
	def id(self, value: str) -> None:
		self.series_id = value
	
	@title.setter
	def title(self, value: str) -> None:
		self.series_title = value
	
	def __str__(self):
		return f"{self.title}\n作者：{self.author_name}\n标签：#{" #".join(self.tags).strip()}"
	def __repr__(self):
		return f"{self.source}Source({self.url})"


@dataclass
class Author:
	novel_id: str
	novel_title: str
	series_id: str | None
	series_title: str | None
	author_id: str
	author_name: str
	
	comment: str = ""
	image_url: str = ""
	tags: list[str] = field(default_factory=list)
	novel_ids: list[str] = field(default_factory=list)
	series_ids: list[str] = field(default_factory=list)
	
	source: str = ""
	url: str = ""
	novel_url: str = ""
	raw: dict[str, Any] = field(default_factory=dict)
	
	def __str__(self):
		return f"作者：{self.author_name}\n标签：#{" #".join(self.tags).strip()}"
	def __repr__(self):
		return f"{self.source}Source({self.url})"


class NovelSource(ABC):
	name: str

	@abstractmethod
	def can_handle(self, text: str) -> bool:
		"""文本/链接是否属于本源。"""

	@abstractmethod
	async def fetch_novel(self, text: str) -> Novel:
		"""拉取并解析为一篇 Novel（单篇）。"""

	@abstractmethod
	async def save_novel(self, text: str) -> Path:
		"""拉取单篇并保存为本地文件，返回文件路径。"""

	async def fetch_series(self, text: str) -> list[Novel]:
		raise NotImplementedError(f"{self.name} 暂不支持系列")

	async def fetch_author_novels(self, text: str) -> list[Novel]:
		raise NotImplementedError(f"{self.name} 暂不支持作者全部")
	
	
	# @abstractmethod
	# async def save_series(self, text: str) -> PathLike:
	# 	pass
	#
	# @abstractmethod
	# async def save_author_novels(self, text: str) -> PathLike:
	# 	pass