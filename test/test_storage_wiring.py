"""storage 装配：名单单例 + 各使用方的默认注入。

背景见 `docs/06-未来架构.md` 第 3.2 节：不新建 `repositories/`，
`storage/` 就是仓储层；名单由 `get_lists()` 提供进程内唯一实例。

运行：.venv\\Scripts\\python.exe -m pytest test/test_storage_wiring.py -q
"""

from __future__ import annotations

from policy.author import AuthorPolicy
from services.apply_service import ApplyService
from services.download_service import DownloadService
from services.review_service import ReviewService
from storage import ListManager, get_lists


def test_get_lists_is_singleton() -> None:
	"""同一个进程里反复取到的是同一个对象。"""
	assert get_lists() is get_lists()


def test_get_lists_is_list_manager() -> None:
	assert isinstance(get_lists(), ListManager)


def test_consumers_share_default_lists() -> None:
	"""策略 / 申请 / 下载 / 审核的默认名单是同一个实例。"""
	manager = get_lists()
	assert AuthorPolicy().list_manager is manager
	assert ApplyService().list_manager is manager
	assert DownloadService().list_manager is manager
	assert ReviewService().list_manager is manager


def test_injected_manager_wins(tmp_path) -> None:
	"""显式注入优先于单例，测试仍可完全脱离真实 data/。"""
	own = ListManager(tmp_path)
	assert AuthorPolicy(own).list_manager is own
	assert ApplyService(list_manager=own).list_manager is own
	assert DownloadService(list_manager=own).list_manager is own
	assert ReviewService(list_manager=own).list_manager is own
