"""JsonStore 的通用能力：config 默认值解析 + 按 key 删除。

两个都是各 Store 原本各写一份的样板，验证收敛后行为不变。

运行（在项目根目录）:
	.venv\\Scripts\\python.exe -m pytest test/test_json_store.py -q
"""

from __future__ import annotations

import json

import config

from storage.json_store import JsonStore, config_default


class _Store(JsonStore):
	"""最小可用子类：只补一个写入口，方便验证基类行为。"""

	def put(self, key: str, info: dict) -> None:
		with self._lock:
			self._items[str(key)] = info
			self._persist()


def test_config_default_reads_config_when_none() -> None:
	assert config_default(None, "FILE_CACHE_TTL_DAYS") == config.FILE_CACHE_TTL_DAYS
	assert config_default(
		None, "APPLY_COOLDOWN_HOURS") == config.APPLY_COOLDOWN_HOURS


def test_config_default_keeps_explicit_values() -> None:
	"""0 是合法值（不冷却 / 立即过期），不能被当成「没传」而回落到 config。"""
	assert config_default(0, "FILE_CACHE_TTL_DAYS") == 0
	assert config_default(0.5, "FILE_CACHE_TTL_DAYS") == 0.5


def test_remove_deletes_and_persists(tmp_path) -> None:
	path = tmp_path / "generic.json"
	store = _Store(path)
	store.put("a", {"v": 1})
	store.put("b", {"v": 2})

	assert store.remove("a") is True
	assert store.remove("a") is False
	assert "b" in store._items

	raw = json.loads(path.read_text(encoding="utf-8"))
	assert "a" not in raw["items"]
	assert "b" in raw["items"]
