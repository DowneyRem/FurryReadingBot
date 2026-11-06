from __future__ import annotations

from sources.base import Novel, NovelSource
from sources.linpx import client, parse


class LinpxSource(NovelSource):
	name = "linpx"

	def can_handle(self, text: str) -> bool:
		return parse.is_linpx_link(text)

	async def fetch(self, text: str) -> Novel:
		novel_id = parse.extract_novel_id(text)
		if not novel_id:
			raise ValueError("无法从文本中解析 Linpx/Pixiv 小说 ID")
		data = await client.get_novel(novel_id)
		return parse.json_to_novel(data)