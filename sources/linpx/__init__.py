from __future__ import annotations
from pathlib import Path

from sources.base import Novel, Series, NovelSource
from sources.linpx import client, parse
from sources.linpx.errors import LinpxParseError
from storage.file import safe_filename
from storage.file_async import save_text


out_dir = Path(__file__).resolve().parents[2] / "files" / "novels"


def _format_novel_text(novel: Novel) -> str:
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
	return f"{head}\n\n{novel.content}"


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


	async def save_novel(self, link: str) -> Path:
		"""拉取单篇并保存为 txt，返回文件路径。"""
		novel = await self.fetch_novel(link)
		path = out_dir / f"{safe_filename(novel.title)}.txt"
		await save_text(path, _format_novel_text(novel))
		return Path(path)


	async def fetch_series(self, link: str) -> Series:
		if link.isdigit():
			series_id = link
		else:
			series_id = parse.get_series_id(link)
			if not series_id:
				raise LinpxParseError("无法从文本中解析 Linpx 系列 ID", raw=link)
		
		data = await client.get_series(series_id)
		return parse.json_to_series(data)
	
	
	async def save_series(self, link: str) -> Path:
		"""下载系列并合并保存为单个 txt，返回文件路径。"""
		content = []
		series = await self.fetch_series(link)
		
		for novel_id in series.novel_ids:
			novel = await self.fetch_novel(novel_id)
			content.append(novel.title)
			content.append(novel.caption)
			content.append(novel.content)
			content.extend(["", ""])
		
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
		
		head = "\n".join(head_lines)
		contents = "\n".join(content)
		data = f"{head}\n\n{contents}"
		
		path = out_dir / f"{safe_filename(series.title)}.txt"
		await save_text(path, data)
		return Path(path)

