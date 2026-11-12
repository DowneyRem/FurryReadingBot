"""作者权限判定：把「名单 → 能不能下载 / 能不能申请」收口到一处。

当前只使用两份名单（`data/*.json`）：

| 名单 | 下载 | 申请加入兽人作者名单 |
|---|---|---|
| 黑名单 `black_authors.json` | ❌ 拒绝 | ❌ 禁止 |
| 兽人作者名单 `furry_authors.json` | ✅ 允许 | —（已在名单里） |
| 都不在 | ❌ 拒绝 | ✅ 允许 |

优先级：**黑名单 > 兽人作者名单**。两份名单同时命中时按黑名单处理。

授权白名单（`white_authors.json`）暂不参与判定：产品语义未定，
接进来之前 `ListManager.is_whitelisted()` 只是可用的存储能力。

本模块是纯判定：只读名单，不写任何东西，也不 import telegram，便于单测。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from storage import ListManager, get_lists


AuthorStatus = Literal["blacklisted", "furry", "unknown"]


@dataclass(frozen=True)
class AuthorDecision:
	"""一个作者在名单中的位置，以及由状态推导出的动作许可。

	`is_*` 是状态判断（展示层分支用），`can_*` 是动作许可（业务链用）；
	当前两组一一对应，改判定规则时两边都会跟着变。
	"""

	status: AuthorStatus
	author_id: str
	author_name: str

	@property
	def is_blacklisted(self) -> bool:
		"""状态判断：展示层据此不给任何申请入口。"""
		return self.status == "blacklisted"

	@property
	def is_furry(self) -> bool:
		"""状态判断：展示层据此决定回作者页还是申请页。"""
		return self.status == "furry"

	@property
	def can_download(self) -> bool:
		"""动作许可：只有兽人作者名单允许下载（等价于 `is_furry`）。"""
		return self.status == "furry"

	@property
	def can_apply(self) -> bool:
		"""只有两份名单都没收录的作者可以申请。"""
		return self.status == "unknown"


class AuthorPolicy:
	"""名单判定入口：`check()` 一次给出状态与许可。"""

	def __init__(self, list_manager: ListManager | None = None) -> None:
		self._list_manager = list_manager


	@property
	def list_manager(self) -> ListManager:
		if self._list_manager is None:
			self._list_manager = get_lists()
		return self._list_manager


	def check(self, author_id: str | int, author_name: str = "") -> AuthorDecision:
		"""按 黑名单 > 兽人作者名单 > 未收录 的顺序判定。

		`author_name` 传调用方已知的名字（例如刚抓到的作品作者名）；
		为空时回落到名单里的记录，再回落到作者 ID。
		"""
		manager = self.list_manager
		key = str(author_id)
		if manager.is_blacklisted(key):
			name = author_name or manager.blacklist.get_name(key) or key
			return AuthorDecision("blacklisted", key, name)
		if manager.is_furryauthor(key):
			name = author_name or manager.furrylist.get_name(key) or key
			return AuthorDecision("furry", key, name)
		return AuthorDecision("unknown", key, author_name or key)
