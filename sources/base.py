from __future__ import annotations

from os import PathLike
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
		text = [
			f"作者：{self.author_name} ({self.author_id})",
			f"小说：共{len(self.novel_ids)}篇，系列：共{len(self.series_ids)}篇",
			f"标签：#{" #".join(self.tags).strip()}",
		]
		return "\n".join(text)
	
	def __repr__(self):
		return f"{self.source}Source({self.url})"


class NovelSource(ABC):
	name: str

	@abstractmethod
	def can_handle(self, link: str) -> bool:
		"""文本/链接是否属于本源。"""

	@abstractmethod
	async def fetch_novel(self, link: str) -> Novel:
		"""拉取并解析为一篇 Novel（单篇）。"""

	@abstractmethod
	async def save_novel(self, link: str) -> Path:
		"""拉取单篇并保存为本地文件，返回文件路径。"""

	async def fetch_series(self, link: str) -> Series:
		pass
	
	# @abstractmethod
	async def save_series(self, link: str) -> PathLike:
		pass
	
	# @abstractmethod
	async def save_series_txt(self, link: str) -> PathLike:
		pass
	
	# @abstractmethod
	async def save_series_zip(self, link: str) -> PathLike:
		pass

	# @abstractmethod
	async def fetch_author(self, link: str) -> Author:
		pass
	
	# @abstractmethod
	async def save_author(self, link: str) -> PathLike:
		pass