"""标签接线：sources 层发现未识别写法 → data/unknown_tags.json。

`sources.tags` 只留一个回调位（`set_unknown_recorder`），本模块负责把它接到
`storage.unknown_tags`。启动时调一次 `install_tag_archive()`，之后
`Novel/Series/Author.__post_init__` 规范化标签时就会自动留档——
业务代码、新来源都不用再接第二处。
"""

from __future__ import annotations

from collections.abc import Iterable

from sources.tags import set_unknown_recorder
from storage.unknown_tags import get_unknown_tags


def install_tag_archive() -> None:
	"""把未识别写法的留档接到 data/unknown_tags.json（进程启动调用一次）。"""
	set_unknown_recorder(get_unknown_tags().record)


def unknown_tags(limit: int = 50) -> dict[str, int]:
	"""已留档的未识别标签：原样写法 → 作品数，按次数从多到少。"""
	return {str(item.text): int(item.count) for item in get_unknown_tags().top(limit)}


def clear_unknown_tags() -> int:
	"""清空未识别标签表（补完 aliases 后调用）；返回清掉的条数。"""
	return get_unknown_tags().clear()


def forget_unknown_tags(texts: Iterable[str]) -> int:
	"""按写法销账：补完 aliases 后精确删掉这些记录，返回删掉的条数。

	``texts`` 可以写原样写法（`unknown_tags()` 的键），也可以写归一后的写法。
	"""
	return get_unknown_tags().remove(texts)
