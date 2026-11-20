"""services/tag_service：留档装配 + 运营读写。

装配一次（`install_tag_archive()`）之后，模型构造时的未识别写法就会被记账；
运营补完 aliases 后可用 `forget_unknown_tags()` 按条销账。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

import services.tag_service as tag_service
import sources.tags as tags_module
from sources.tags import canonicalize_tags, normalize
from storage.unknown_tags import UnknownTagStore


@pytest.fixture(autouse=True)
def _isolated_store(
	tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[UnknownTagStore]:
	"""默认表换成临时文件，并完成装配；用例结束解除装配。"""
	store = UnknownTagStore(tmp_path / "unknown_tags.json")
	monkeypatch.setattr(tag_service, "get_unknown_tags", lambda: store)
	tag_service.install_tag_archive()
	try:
		yield store
	finally:
		tags_module.set_unknown_recorder(None)


def test_install_tag_archive_wires_recorder(_isolated_store: UnknownTagStore) -> None:
	canonicalize_tags(["未知A"])
	assert tag_service.unknown_tags() == {"未知A": 1}


def test_unknown_tags_can_be_forgotten_one_by_one(
	_isolated_store: UnknownTagStore,
) -> None:
	"""人工判断 + 补完 aliases 后按条销账，不用把整张表清空。"""
	canonicalize_tags(["未知A", "未知B"])
	assert set(tag_service.unknown_tags()) == {"未知A", "未知B"}

	assert tag_service.forget_unknown_tags(["未知A"]) == 1
	assert tag_service.unknown_tags() == {"未知B": 1}

	# 归一键也能删
	assert tag_service.forget_unknown_tags([normalize("未知B")]) == 1
	assert tag_service.unknown_tags() == {}


def test_clear_unknown_tags(_isolated_store: UnknownTagStore) -> None:
	canonicalize_tags(["未知A", "未知B"])
	assert tag_service.clear_unknown_tags() == 2
	assert tag_service.unknown_tags() == {}


def test_recorder_not_installed_keeps_sources_clean(
	monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
	"""没装配时不写盘（离线脚本 / 单测天然无副作用），只打 debug。"""
	store = UnknownTagStore(tmp_path / "unknown_tags.json")
	monkeypatch.setattr(tag_service, "get_unknown_tags", lambda: store)
	tags_module.set_unknown_recorder(None)

	assert canonicalize_tags(["未知A"]) == ["未知A"]
	assert tag_service.unknown_tags() == {}
