from __future__ import annotations

import re
from pathlib import Path

from sources.base import Novel, NovelSource
from sources.linpx import client, parse
from storage.file_async import save_text


def _safe_filename(name: str, max_len: int = 80) -> str:
	name = (name or "untitled").strip()
	name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
	name = re.sub(r"\s+", " ", name).strip(" ._")
	if not name:
		name = "untitled"
	return name[:max_len]


def _format_novel_text(novel: Novel) -> str:
	"""生成写入文件的完整文本（头部信息 + 正文）。"""
	tags = " ".join(f"#{t}" for t in novel.tags) if novel.tags else ""
	head_lines = [
		novel.title,
		f"作者：{novel.author_name}",
		f"链接：{novel.url}",
	]
	if tags:
		head_lines.append(f"标签：{tags}")
	if novel.description:
		head_lines.append(f"简介：{novel.description}")
	if novel.series_title:
		head_lines.append(f"系列：{novel.series_title}")
	head = "\n".join(head_lines)
	return f"{head}\n\n{novel.content}"


class LinpxSource(NovelSource):
	name = "linpx"

	def can_handle(self, text: str) -> bool:
		return parse.is_linpx_link(text)

	async def fetch_novel(self, text: str) -> Novel:
		novel_id = parse.extract_novel_id(text)
		if not novel_id:
			raise ValueError("无法从文本中解析 Linpx/Pixiv 小说 ID")
		data = await client.get_novel(novel_id)
		return parse.json_to_novel(data)

	async def save_novel(self, text: str) -> Path:
		"""拉取单篇并保存为 txt，返回文件路径。"""
		novel = await self.fetch_novel(text)
		out_dir = Path(__file__).resolve().parents[2] / "down" / "novels"
		out_dir.mkdir(parents=True, exist_ok=True)
		filename = f"{_safe_filename(novel.title)}_{novel.id}.txt"
		path = out_dir / filename
		await save_text(path, _format_novel_text(novel))
		return Path(path)
