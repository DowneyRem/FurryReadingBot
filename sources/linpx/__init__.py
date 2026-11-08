from __future__ import annotations

import re
from pathlib import Path

from sources.base import Novel, Series, Author, NovelSource
from sources.linpx import client, parse
from sources.linpx.errors import LinpxParseError
from storage.file import safe_filename
from storage.file_async import save_text
from storage.zip_async import zip_path
from utils.timer import timer


out_dir = Path(__file__).resolve().parents[2] / "files" / "novels"


def format_novel_text(novel: Novel) -> str:
	"""生成写入文件的完整文本（头部信息 + 正文）。"""
	head_lines = [
		novel.title,
		f"作者：{novel.author_name}",
		f"链接：{novel.url}",
	]
	if novel.tags:
		tags = " ".join(f"#{t}" for t in novel.tags) if novel.tags else ""
		head_lines.append(f"标签：{tags}")
	if novel.caption:
		head_lines.append(f"简介：{novel.caption}")
	# if novel.series_title:
	# 	head_lines.append(f"系列：{novel.series_title}")
	head = "\n".join(head_lines)
	return f"{head}\n\n\n{novel.content}"


def format_chapter_title(chapter_title: str, series_title: str, index: int) -> str:
	"""生成章节标题：去掉与系列名重复的部分，并补上「第N章」。"""
	title = (chapter_title or "").strip()
	series = (series_title or "").strip()
	if series:
		replaced = title.replace(series, "").replace("-", "").strip()
		if len(replaced) >= 2:
			title = replaced
	if "第" not in title and "章" not in title:
		title = f"第{index}章 {title}"
	return title


def format_series_text(series, novels: list[Novel]) -> str:
	"""系列元信息 + 各章正文 → 完整 txt 字符串。"""
	head_lines = [
		series.title,
		f"作者：{series.author_name}",
		# f"链接：{series.url}",
		f"链接：{series.novel_url}",
	]
	if series.tags:
		tags = " ".join(f"#{t}" for t in series.tags) if series.tags else ""
		head_lines.append(f"标签：{tags}")
	if series.caption:
		head_lines.append(f"简介：{series.caption}")

	content = []
	for i, novel in enumerate(novels, start=1):
		title = novel.title
		# 可选：统一章节名
		# title = format_chapter_title(novel.title, series.title, i)
		content.append(title)
		content.append(novel.caption)
		content.extend(["", ""])
		content.append(novel.content)
		content.extend(["", "", ""])
	head = "\n".join(head_lines)
	contents = "\n".join(content)
	return f"{head}\n\n\n{contents}"


def is_real_series(series: Series) -> bool:
	count = 0
	arabic_pattern = re.compile(r'\d+')
	chinese_pattern = re.compile(r'[零一二三四五六七八九十百千万亿两〇壹贰叁肆伍陆柒捌玖拾佰仟萬]+')
	
	for title in series.novel_titles:
		arabic_matches = arabic_pattern.findall(title)
		chinese_matches = chinese_pattern.findall(title)
		count += len(arabic_matches) + len(chinese_matches)
	return count >= series.total * 0.75


class LinpxSource(NovelSource):
	name = "linpx"

	def can_handle(self, link: str) -> bool:
		return parse.is_linpx_link(link)

	async def fetch_novel(self, link: str) -> Novel:
		if link.isdigit():
			novel_id = link
		else:
			novel_id = parse.get_novel_id(link)
			if not novel_id:
				raise LinpxParseError("无法从文本中解析 Linpx 小说 ID", raw=link)
			
		data = await client.get_novel(novel_id)
		return parse.json_to_novel(data)
	
	
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
			series_id = parse.get_series_id(link)
			if not series_id:
				raise LinpxParseError("无法从文本中解析 Linpx 系列 ID", raw=link)
		
		data = await client.get_series(series_id)
		return parse.json_to_series(data)
	
	
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
			author_id = parse.get_author_id(link)
			if not author_id:
				raise LinpxParseError("无法从文本中解析 Linpx 作者 ID", raw=link)
		
		data = await client.get_author(author_id)
		return parse.json_to_author(data)
	
	
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
	
