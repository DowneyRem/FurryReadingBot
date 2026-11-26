"""存储层：唯一的持久化层。

只有 ``storage/`` 读写 JSON（``JsonStore`` 统一原子写、热加载、锁、prune），
上层只调用语义方法（``is_blacklisted()`` / ``get_valid()`` / ``set_status()``），
换存储时只改这里，service 一行不用动。

``get_lists()`` 是进程内共享的名单实例：策略、申请、下载、审核
四处共用同一个对象，避免各自持有一份快照互相覆盖。
"""

from __future__ import annotations

from storage.author_list import ListManager, get_lists
from storage.black_request import (
	BlackRequestStore,
	get_black_requests,
)
from storage.fetch_cache import FetchCacheStore, get_fetch_cache
from storage.furry_request import (
	FurryRequestStore,
	get_furry_requests,
)
from storage.unknown_tags import UnknownTagStore, get_unknown_tags

__all__ = [
	"BlackRequestStore",
	"FetchCacheStore",
	"FurryRequestStore",
	"ListManager",
	"UnknownTagStore",
	"get_black_requests",
	"get_fetch_cache",
	"get_furry_requests",
	"get_lists",
	"get_unknown_tags",
]
