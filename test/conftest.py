"""测试公共装配：标签词表统一用 `data.example/tags.toml`。

生产词表 `data/tags.toml` 在根仓库 `.gitignore` 里（属于私有数据仓），
全新克隆 / CI 未必有；测试固定用样例词表，标签断言才与环境无关。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import sources.tags as tags_module

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "data.example" / "tags.toml"


@pytest.fixture(autouse=True)
def example_vocabulary(monkeypatch: pytest.MonkeyPatch) -> None:
	"""把全仓 `get_vocabulary()` 固定到样例词表（模型层 __post_init__ 也走它）。"""
	if not EXAMPLE_PATH.exists():
		return
	vocab = tags_module.load_vocabulary(EXAMPLE_PATH)
	monkeypatch.setattr(tags_module, "get_vocabulary", lambda: vocab)
