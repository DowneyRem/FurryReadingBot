"""存储层：唯一的持久化层。

只有 ``storage/`` 读写 JSON（``JsonStore`` 统一原子写、热加载、锁、prune），
上层只调用语义方法（``is_blacklisted()`` / ``get_valid()`` / ``set_status()``），
换存储时只改这里，service 一行不用动。

``get_lists()`` 是进程内共享的名单实例：策略、申请、下载、审核
四处共用同一个对象，避免各自持有一份快照互相覆盖。
"""

from __future__ import annotations

from storage.author_list import ListManager, get_lists
from storage.blacklist_requests import (
	BlacklistRequestStore,
	get_blacklist_requests,
)

__all__ = [
	"BlacklistRequestStore",
	"ListManager",
	"get_blacklist_requests",
	"get_lists",
]
