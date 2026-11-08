from __future__ import annotations

from pathlib import Path

from sources.base import Novel, Series, Author, NovelSource
from sources.utils import is_real_series
from sources.format import format_novel_text, format_series_text

from sources.linpx import client
from sources.linpx.errors import LinpxParseError
from sources.linpx.parse import json_to_novel, json_to_series, json_to_author
from sources.linpx.urls import get_novel_id, get_series_id, get_author_id
from sources.linpx.urls import is_novel_link, is_series_link, is_author_link, is_linpx_link

from storage.file import safe_filename
from storage.file_async import save_text
from storage.zip_async import zip_path
from utils.timer import timer


out_dir = Path(__file__).resolve().parents[2] / "files" / "novels"


class LinpxSource(NovelSource):
	name = "linpx"

	def can_handle(self, link: str) -> bool:
		return is_linpx_link(link)


	async def fetch_novel(self, link: str) -> Novel:
		if link.isdigit():
			novel_id = link
		else:
			novel_id = get_novel_id(link)
			if not novel_id:
				raise LinpxParseError("无法从文本中解析 Linpx 小说 ID", raw=link)
			
		data = await client.get_novel(novel_id)
		return json_to_novel(data)
	
	
	async def save_novel(self, link: str, author: str="", series: str="") -> Path:
		"""拉取单篇并保存为 txt，返回文件路径。"""
		novel = await self.fetch_novel(link)
		text = format_novel_text(novel)
		path = out_dir / author / series /f"{safe_filename(novel.title)}.txt"
		path = await save_text(path, text)
		return path


	async def fetch_series(self, link: str) -> Series:
		if link.isdigit():
			series_id = link
		else:
			series_id = get_series_id(link)
			if not series_id:
				raise LinpxParseError("无法从文本中解析 Linpx 系列 ID", raw=link)
		
		data = await client.get_series(series_id)
		return json_to_series(data)
	
	
	async def save_series(self, link: str, author: str="") -> Path:
		series = await self.fetch_series(link)
		if is_real_series(series):
			return await self.save_series_txt(link, author)
		else:
			return await self.save_series_zip(link, author)
	
	
	async def save_series_txt(self, link: str, author: str="") -> Path:
		series = await self.fetch_series(link)
		novels = []
		for novel_id in series.novel_ids:
			novels.append(await self.fetch_novel(novel_id))
		
		text = format_series_text(series, novels)
		path = out_dir / author / f"{safe_filename(series.title)}.txt"
		path = await save_text(path, text)
		return path
	
	
	async def save_series_zip(self, link: str, author: str="") -> Path:
		series = await self.fetch_series(link)
		for novel_id in series.novel_ids:
			await self.save_novel(novel_id, author, series.series_title)
			
		path = Path(out_dir) / author / series.series_title
		if not author:
			path = await zip_path(path, delete=True)
		return path
	
	
	# @staticmethod
	async def fetch_author(self, link: str) -> Author:
		if link.isdigit():
			author_id = link
		else:
			author_id = get_author_id(link)
			if not author_id:
				raise LinpxParseError("无法从文本中解析 Linpx 作者 ID", raw=link)
		
		data = await client.get_author(author_id)
		return json_to_author(data)
	
	
	async def save_author(self, link: str) -> Path:
		author = await self.fetch_author(link)
		in_series_novel_ids = []
		for series_id in author.series_ids:
			series = await self.fetch_series(series_id)
			in_series_novel_ids.extend(series.novel_ids)
			await self.save_series(series_id, author.author_name)
		
		single_ids = list(set(author.novel_ids).difference(set(in_series_novel_ids)))
		for novel_id in single_ids:
			await self.save_novel(novel_id, author.author_name, "单篇")

		path = Path(out_dir) / author.author_name
		path = await zip_path(path)
		return path
	
