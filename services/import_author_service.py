"""用例：把 Linpx 推荐作者合并进兽人作者名单。

调用链：`/sync`
  → 本模块：`sources.linpx.client.get_fav_users()` 拉取（领域层只取数据）
  → 过滤（已收录 / 黑名单跳过）→ `AuthorListStore.add_many()` 落盘
  → `services/sync_service.py` 再执行 git 提交。

这是唯一的推荐作者入口：服务器定时任务只调 `script/sync_data.sh`，不经过这里，
所以自动同步不会联网，也不会碰名单。

分层说明：**抓取在 `sources/`，落盘在 `storage/`，这里只排顺序。**
所以本模块不 import `infra.http`、不拼 URL / headers。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from sources.linpx.client import get_fav_users
from sources.linpx.errors import LinpxNetworkError
from storage import ListManager, get_lists


logger = logging.getLogger(__name__)

# 导入时写入的 note；历史数据里的推荐作者也是这个值，保持一致
NOTE = "Linpx"
# 给 Telegram 看的一句话；接口细节只进日志，不刷进聊天
FETCH_ERROR = "Linpx 暂时无法访问"


@dataclass(frozen=True)
class ImportAuthorResult:
	"""一次推荐作者导入的结果；handler 据此拼提示文案。"""

	ok: bool
	total: int = 0
	skipped: int = 0
	new_authors: tuple[tuple[str, str], ...] = ()
	error: str = ""

	@property
	def added(self) -> int:
		"""本次新增的作者数。"""
		return len(self.new_authors)


def _pairs(data: list) -> Iterable[tuple[str, str]]:
	"""把接口返回的列表整理成 (作者 ID, 名字)；不合格的条目直接跳过。"""
	for item in data:
		if not isinstance(item, dict):
			continue
		author_id = str(item.get("id") or "").strip()
		if not author_id:
			continue
		yield author_id, str(item.get("name") or "").strip()


def merge_authors(data: list, lists: ListManager | None = None) -> ImportAuthorResult:
	"""把推荐作者数据合并进兽人作者名单。

	兽人作者名单里已有的作者跳过（不覆盖原 note）；黑名单作者也跳过——
	不该因为「Linpx 推荐」又被加回可下载名单。整批只落盘一次。
	"""
	manager = lists if lists is not None else get_lists()
	records = list(_pairs(data))

	fresh: list[tuple[str, str]] = []
	seen: set[str] = set()
	for author_id, name in records:
		if author_id in seen:
			continue
		seen.add(author_id)
		if manager.is_furryauthor(author_id) or manager.is_blacklisted(author_id):
			continue
		fresh.append((author_id, name))

	added = manager.furrylist.add_many(
		(author_id, name, NOTE) for author_id, name in fresh)
	logger.info(
		"合并 Linpx 推荐作者：共 %d 个，新增 %d 个，跳过 %d 个",
		len(records), added, len(records) - added)
	return ImportAuthorResult(
		True,
		total=len(records),
		skipped=len(records) - added,
		# add_many 只会跳过已存在的 key，顺序不变，所以前 added 条就是真正写入的
		new_authors=tuple(fresh[:added]),
	)


async def import_authors(lists: ListManager | None = None) -> ImportAuthorResult:
	"""在线拉取推荐作者并合并；网络异常返回失败结果，不抛异常。"""
	try:
		data = await get_fav_users()
	except LinpxNetworkError as exc:
		logger.warning("拉取 Linpx 推荐作者失败：%s", exc)
		return ImportAuthorResult(False, error=FETCH_ERROR)
	return merge_authors(data, lists)
