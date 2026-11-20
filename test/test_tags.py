"""标签词表：归一 / 拆分 / 上级闭包 / 匹配与排序 / 校验。

两份词表各有一条守门用例：词表改坏（errors 非空）时 CI 直接红。
运行：python -m pytest test/test_tags.py -q
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

import sources.tags as tags_module
from sources.tags import (
	DEFAULT_PATH,
	Vocabulary,
	canonicalize_tags,
	display_tags,
	get_vocabulary,
	load_vocabulary,
	normalize,
	set_unknown_recorder,
)
from storage.unknown_tags import UnknownTagStore

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_PATH = ROOT / "data.example" / "tags.toml"

# 最小词表：原子 / 复合 / 多级上级 / 跨组，够覆盖全部规则
BASE: dict = {
	"Gay": {"group": "orientation", "order": 20, "aliases": ["BL", "男同"]},
	"Furry": {"group": "species", "order": 10, "aliases": ["兽人", "獸人"]},
	"GayFurry": {
		"group": "orientation",
		"order": 30,
		"parts": ["Gay", "Furry"],
		"aliases": ["ケモホモ", "Gay Furry"],
	},
	"Transformation": {"group": "plot", "order": 50},
	"Transfur": {
		"group": "plot",
		"order": 60,
		"parents": ["Transformation", "Furry"],
		"aliases": ["兽化"],
	},
	"TransfurFurry": {"group": "plot", "order": 65, "parts": ["Transfur", "Furry"]},
	"R18": {"group": "rating", "order": 5, "aliases": ["R-18"]},
	"R18G": {"group": "rating", "order": 6, "parents": ["R18"], "aliases": ["R18-G"]},
	"CBT": {"group": "act", "order": 70, "parents": ["R18G"], "aliases": ["虐屌"]},
}


def make_vocab(records: dict | None = None, **meta) -> Vocabulary:
	"""组一份词表：meta 默认 schema=2 / casefold / split，可按关键字覆盖。"""
	data: dict = {"meta": {"schema": 2, "match": "casefold", "parts_mode": "split"}}
	data["meta"].update(meta)
	data.update(BASE)
	data.update(records or {})
	return Vocabulary(data)


def errors_of(records: dict | None = None, **meta) -> list[str]:
	return make_vocab(records, **meta).errors


def has_error(errors: list[str], needle: str) -> bool:
	return any(needle in error for error in errors)


# ---------- 归一 ----------
def test_normalize_fullwidth_hash_and_case() -> None:
	assert normalize("Ｒ１８") == "r18"
	assert normalize("#Gay Furry") == "gay furry"
	assert normalize("  gay   furry  ") == "gay furry"
	assert normalize("獸人") == "獸人"  # 简繁不互转：要覆盖就写进 aliases


# ---------- 拆分与闭包 ----------
def test_compound_splits_to_atoms_without_parents() -> None:
	vocab = make_vocab()
	assert vocab.resolve("GayFurry") == {"Gay", "Furry"}
	# split 模式：拆出来的原子不再继承上级
	assert vocab.resolve("TransfurFurry") == {"Transfur", "Furry"}


def test_compound_inherit_mode_keeps_parents() -> None:
	vocab = make_vocab(parts_mode="inherit")
	assert vocab.resolve("TransfurFurry") == {"Transfur", "Transformation", "Furry"}


def test_atomic_tag_adds_parent_closure() -> None:
	vocab = make_vocab()
	assert vocab.resolve("CBT") == {"CBT", "R18G", "R18"}
	assert vocab.resolve("Transfur") == {"Transfur", "Transformation", "Furry"}


def test_resolve_never_returns_compound() -> None:
	vocab = make_vocab()
	compounds = {
		name for name, rec in vocab.tags.items() if isinstance(rec, dict) and rec.get("parts")
	}
	for name in vocab.tags:
		assert not (vocab.resolve(name) & compounds)


# ---------- 匹配 ----------
def test_whole_string_alias_wins_over_split() -> None:
	vocab = make_vocab()
	assert vocab.resolve_one("Gay Furry") == ["GayFurry"]
	assert vocab.resolve_one("ケモホモ") == ["GayFurry"]


def test_resolve_one_splits_on_separators() -> None:
	vocab = make_vocab()
	assert vocab.resolve_one("gay/furry") == ["Gay", "Furry"]
	assert vocab.resolve_one("R18,獸人") == ["R18", "Furry"]
	assert vocab.resolve_one("gay/gay") == ["Gay"]  # 重复段去重


def test_resolve_one_requires_every_piece() -> None:
	vocab = make_vocab()
	assert vocab.resolve_one("gay/完全未知") is None


def test_resolve_all_sorts_by_group_then_order() -> None:
	vocab = make_vocab()
	tokens, rest = vocab.resolve_all(["cbt", "gay furry"])
	assert tokens == ["Gay", "Furry", "R18", "R18G", "CBT"]
	assert rest == []


def test_resolve_all_keeps_residual_separately() -> None:
	vocab = make_vocab()
	tokens, rest = vocab.resolve_all(["兽化", "完全未知", ""])
	assert tokens == ["Furry", "Transformation", "Transfur"]
	assert rest == ["完全未知", ""]


# ---------- 缓存安全 ----------
def test_resolve_returns_a_copy() -> None:
	"""返回的是副本：调用方改返回值不能污染内部缓存。"""
	vocab = make_vocab()
	tokens = vocab.resolve("CBT")
	tokens.add("HACKED")
	assert vocab.resolve("CBT") == {"CBT", "R18G", "R18"}


def test_recursion_does_not_poison_cache() -> None:
	"""递归中途（带防环栈）的局部结果不能写进缓存。

	旧实现会把 `_resolve(..., stack)` 的截断结果永久缓存下来，
	之后所有 resolve("GayFurry") 都少一个 Furry。
	"""
	vocab = make_vocab()
	assert vocab._resolve("GayFurry", ("Furry",)) == {"Gay"}
	assert vocab.resolve("GayFurry") == {"Gay", "Furry"}


def test_recursion_does_not_poison_cache_in_inherit_mode() -> None:
	vocab = make_vocab(parts_mode="inherit")
	vocab._resolve("TransfurFurry", ("Furry",))
	assert vocab.resolve("TransfurFurry") == {"Transfur", "Transformation", "Furry"}


def test_invalid_record_does_not_crash_resolve() -> None:
	"""结构非法的记录只报 ERROR，解析路径不能抛 AttributeError。"""
	vocab = Vocabulary(
		{"meta": {"schema": 2, "match": "casefold", "parts_mode": "split"}, "Bad": "oops"}
	)
	assert vocab.errors
	assert vocab.resolve("Bad") == set()
	assert vocab.resolve_one("bad") is None


# ---------- 进程内入口与未识别标签 ----------
@pytest.fixture(autouse=True)
def _isolated_unknown_store(tmp_path: Path) -> Iterator[UnknownTagStore]:
	"""未识别标签的留档：每条用例换成临时表，绝不写仓库里的 data/。"""
	store = UnknownTagStore(tmp_path / "unknown_tags.json")
	set_unknown_recorder(store.record)
	try:
		yield store
	finally:
		set_unknown_recorder(None)


def archived(store: UnknownTagStore) -> dict[str, int]:
	"""留档表 → {原样写法: 作品数}。"""
	return {str(item.text): int(item.count) for item in store.top(0)}


def test_display_tags_orders_and_limits() -> None:
	vocab = make_vocab()
	assert display_tags(["cbt"], vocab=vocab) == ["R18", "R18G", "CBT"]
	assert display_tags(["cbt"], vocab=vocab, limit=None) == ["R18", "R18G", "CBT"]
	assert display_tags(["cbt", "gay furry"], vocab=vocab, limit=2) == ["Gay", "Furry"]
	assert display_tags(None, vocab=vocab) == []


def test_display_tags_keeps_unknown_tags() -> None:
	"""未识别的写法原样追加在规范标签之后。"""
	vocab = make_vocab()
	assert display_tags(["cbt", "完全未知"], vocab=vocab) == [
		"R18", "R18G", "CBT", "完全未知"]
	# 去前导 # / 全角归一是展示需要，大小写保持来源原样
	assert display_tags(["＃NewTag", "#Other"], vocab=vocab) == ["NewTag", "Other"]
	# 同一次调用里重复（含仅大小写不同）的写法只出现一次
	assert display_tags(["Foo", "foo", "FOO"], vocab=vocab) == ["Foo"]


def test_display_tags_limit_only_caps_canonical() -> None:
	"""limit 只管规范标签：未识别写法不被截掉，否则永远看不到该补什么。"""
	vocab = make_vocab()
	assert display_tags(["cbt", "gay furry", "未知"], vocab=vocab, limit=2) == [
		"Gay", "Furry", "未知"]


def test_unknown_tags_are_logged(caplog: pytest.LogCaptureFixture) -> None:
	vocab = make_vocab()
	with caplog.at_level(logging.DEBUG, logger="sources.tags"):
		display_tags(["兽化", "未知A"], vocab=vocab)
	assert "未知A" in caplog.text


def test_resolve_all_records_by_default(
	_isolated_unknown_store: UnknownTagStore,
) -> None:
	"""留档发生在解析出口：调用方只要解析过，就不会漏记。"""
	vocab = make_vocab()
	tokens, residual = vocab.resolve_all(["兽化", "完全未知"])
	assert tokens == ["Furry", "Transformation", "Transfur"]
	assert residual == ["完全未知"]
	assert archived(_isolated_unknown_store) == {"完全未知": 1}

	# resolve() 仍不写盘：入参是规范名，不命中属于调用方写错名
	assert vocab.resolve("完全未知") == set()
	assert archived(_isolated_unknown_store) == {"完全未知": 1}


def test_resolve_all_can_skip_recording(
	_isolated_unknown_store: UnknownTagStore,
) -> None:
	"""`record=False` 只解析不留档（试规则 / 单测）。"""
	vocab = make_vocab()
	vocab.resolve_all(["完全未知"], record=False)
	assert archived(_isolated_unknown_store) == {}


def test_resolve_unknown_name_logs_without_recording(
	_isolated_unknown_store: UnknownTagStore, caplog: pytest.LogCaptureFixture
) -> None:
	"""规范名不命中只提示调用方写错了，不算「来源写法」，不进未识别表。"""
	vocab = make_vocab()
	with caplog.at_level(logging.DEBUG, logger="sources.tags"):
		assert vocab.resolve("NoSuchTag") == set()
	assert "NoSuchTag" in caplog.text
	assert archived(_isolated_unknown_store) == {}


# ---------- 入口规范化 ----------
def test_canonicalize_tags_normalizes_source_spellings() -> None:
	"""模型层入口：来源写法 → 规范名 + 未识别写法原样保留。"""
	assert canonicalize_tags(["兽人", "ケモホモ", "原创"]) == ["Gay", "Furry", "原创"]


def test_canonicalize_tags_is_idempotent() -> None:
	assert canonicalize_tags(["Furry"]) == ["Furry"]


def test_canonicalize_tags_skips_empty_values() -> None:
	assert canonicalize_tags(None) == []
	assert canonicalize_tags(["", "   "]) == []


def test_canonicalize_tags_degrades_when_vocabulary_unavailable(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""词表缺失 / 出错时不能阻断抓取：原样返回并打 warning。"""

	def boom() -> Vocabulary:
		raise FileNotFoundError("data/tags.toml 不存在")

	monkeypatch.setattr(tags_module, "get_vocabulary", boom)
	assert canonicalize_tags(["兽人", "原创"]) == ["兽人", "原创"]


def test_unknown_tags_are_not_auto_pruned(
	_isolated_unknown_store: UnknownTagStore,
) -> None:
	"""没人工判断过的写法不能自动消失：只有显式 prune() 才裁。"""
	store = _isolated_unknown_store
	store.record((f"tag{i}", f"Tag{i}") for i in range(600))
	assert len(store.top(0)) == 600

	assert store.prune(10) == 590
	assert len(store.top(0)) == 10


def test_unknown_tags_are_persisted(
	_isolated_unknown_store: UnknownTagStore,
) -> None:
	"""未识别标签要落盘：键是归一写法，text 保留原样，次数累加。"""
	vocab = make_vocab()
	display_tags(["兽化", "未知A", "未知B"], vocab=vocab)
	display_tags(["未知A", "未知a"], vocab=vocab)

	payload = json.loads(
		_isolated_unknown_store.path.read_text(encoding="utf-8"))
	rows = {key: (row["text"], row["count"]) for key, row in payload["tags"].items()}
	# 同一次调用内去重：count 是「带这个写法的作品数」，不是原始串出现次数
	assert rows == {"未知a": ("未知A", 2), "未知b": ("未知B", 1)}
	assert set(payload["tags"]["未知a"]) == {
		"text", "count", "first_seen", "last_seen"}

	# 读接口按次数降序
	assert archived(_isolated_unknown_store) == {"未知A": 2, "未知B": 1}

	# 重启后还在：新实例读同一个文件
	reloaded = UnknownTagStore(_isolated_unknown_store.path)
	assert [(item.text, item.count) for item in reloaded.top()] == [
		("未知A", 2), ("未知B", 1)]

	assert _isolated_unknown_store.clear() == 2
	assert archived(_isolated_unknown_store) == {}
	assert json.loads(
		_isolated_unknown_store.path.read_text(encoding="utf-8"))["tags"] == {}


def test_unknown_tags_can_skip_recording(
	_isolated_unknown_store: UnknownTagStore,
) -> None:
	"""`record=False` 只展示不记账（离线预览 / 测试用）。"""
	assert display_tags(["未知"], vocab=make_vocab(), record=False) == ["未知"]
	assert archived(_isolated_unknown_store) == {}


def test_unknown_tags_write_failure_keeps_display(
	_isolated_unknown_store: UnknownTagStore, monkeypatch: pytest.MonkeyPatch
) -> None:
	"""落盘失败不能影响展示：磁盘满 / 权限不对只打 warning。"""

	def boom(_entries):  # 只为触发异常，参数不用
		raise OSError("disk full")

	monkeypatch.setattr(_isolated_unknown_store, "record", boom)
	set_unknown_recorder(_isolated_unknown_store.record)   # 重新绑定成会抛异常的实现
	assert display_tags(["未知"], vocab=make_vocab()) == ["未知"]
	assert archived(_isolated_unknown_store) == {}


def test_get_vocabulary_loads_file_once(monkeypatch: pytest.MonkeyPatch) -> None:
	"""模块级入口只读一次：lru_cache 命中后不再碰文件。"""
	if not DEFAULT_PATH.exists():
		pytest.skip(f"词表不存在：{DEFAULT_PATH}")
	calls: list[str | Path | None] = []
	real = tags_module.load_vocabulary

	def fake_load(path: str | Path | None = None) -> Vocabulary:
		calls.append(path)
		return real(path)

	monkeypatch.setattr(tags_module, "load_vocabulary", fake_load)
	get_vocabulary.cache_clear()
	try:
		first = get_vocabulary()
		second = get_vocabulary()
	finally:
		get_vocabulary.cache_clear()
	assert first is second
	assert len(calls) == 1
	assert not first.errors


# ---------- 校验：ERROR ----------
def test_alias_conflict_is_error() -> None:
	errors = errors_of({"Other": {"group": "act", "order": 80, "aliases": ["男同"]}})
	assert has_error(errors, "别名冲突")


def test_parts_and_parents_are_exclusive() -> None:
	errors = errors_of(
		{"Both": {"group": "act", "order": 80, "parts": ["Gay"], "parents": ["Furry"]}}
	)
	assert has_error(errors, "互斥")


def test_undefined_reference_is_error() -> None:
	errors = errors_of({"Broken": {"group": "act", "order": 80, "parents": ["不存在"]}})
	assert has_error(errors, "未定义的标签")


def test_self_reference_is_error() -> None:
	errors = errors_of({"Loop": {"group": "act", "order": 80, "parents": ["Loop"]}})
	assert has_error(errors, "不能引用自己")


def test_parent_must_be_atomic() -> None:
	errors = errors_of({"Child": {"group": "act", "order": 80, "parents": ["GayFurry"]}})
	assert has_error(errors, "上级必须是原子标签")


def test_nested_parts_is_error() -> None:
	errors = errors_of({"Outer": {"group": "act", "order": 80, "parts": ["GayFurry", "Furry"]}})
	assert has_error(errors, "parts 不支持嵌套")


def test_cycle_is_error() -> None:
	errors = errors_of(
		{
			"Alpha": {"group": "act", "order": 80, "parts": ["Beta"]},
			"Beta": {"group": "act", "order": 81, "parts": ["Alpha"]},
		}
	)
	assert has_error(errors, "循环")


def test_casefold_duplicate_name_is_error() -> None:
	errors = errors_of({"gay": {"group": "act", "order": 80}})
	assert has_error(errors, "大小写")


def test_order_must_be_int() -> None:
	errors = errors_of({"Bad": {"group": "act", "order": "80"}})
	assert has_error(errors, "order")


def test_unsupported_schema_is_error() -> None:
	errors = errors_of(schema=1)
	assert has_error(errors, "meta.schema")


def test_bad_parts_mode_is_error() -> None:
	errors = errors_of(parts_mode="merge")
	assert has_error(errors, "parts_mode")


def test_bad_match_is_error() -> None:
	errors = errors_of(match="lower")
	assert has_error(errors, "meta.match")


# ---------- 校验：WARN ----------
def test_name_mismatch_with_parts_warns() -> None:
	vocab = make_vocab({"Odd": {"group": "act", "order": 80, "parts": ["Gay", "Furry"]}})
	assert any("不是 parts 的直接拼接" in warning for warning in vocab.warnings)


def test_alias_equal_to_name_warns() -> None:
	vocab = make_vocab({"Dup": {"group": "act", "order": 80, "aliases": ["Dup"]}})
	assert any("不必把规范名自己写进" in warning for warning in vocab.warnings)


def test_lowercase_name_outside_lang_group_warns() -> None:
	vocab = make_vocab({"lower": {"group": "act", "order": 80}})
	assert any("PascalCase" in warning for warning in vocab.warnings)


def test_lowercase_name_in_lang_group_is_fine() -> None:
	vocab = make_vocab({"zh": {"group": "lang", "order": 80}})
	assert not any("PascalCase" in warning for warning in vocab.warnings)


# ---------- 文档示例（对真词表跑一遍，防止文档与实现漂移） ----------
_COMMON_DEMOS: dict[str, list[str] | None] = {
	"ケモホモ": ["Gay", "Furry"],
	"Gay Furry": ["Gay", "Furry"],
	"gay/furry": ["Gay", "Furry"],
	"GAYFURRY": ["Gay", "Furry"],
	"Ｒ１８": ["R18"],
	"r-18": ["R18"],
	"獸人": ["Furry"],
	"兽化": ["Furry", "Transformation", "Transfur"],
	"完全未知": None,
}
# 生产词表里 CBT 只挂在 R18G 下；示例词表还挂了 BDSM
PRODUCTION_DEMOS = {**_COMMON_DEMOS, "CBT": ["R18", "R18G", "CBT"]}
EXAMPLE_DEMOS = {**_COMMON_DEMOS, "CBT": ["R18", "R18G", "BDSM", "CBT"]}


@pytest.mark.parametrize(
	("path", "demos"),
	[(DEFAULT_PATH, PRODUCTION_DEMOS), (EXAMPLE_PATH, EXAMPLE_DEMOS)],
	ids=["data/tags.toml", "data.example/tags.toml"],
)
def test_documented_examples(
	path: Path, demos: dict[str, list[str] | None]
) -> None:
	"""docs/08 里的解析示例必须与真词表一致。"""
	if not path.exists():
		pytest.skip(f"词表不存在：{path}")
	vocab = load_vocabulary(path)
	for raw, expected in demos.items():
		tokens, rest = vocab.resolve_all([raw])
		if expected is None:
			assert tokens == [] and rest == [raw], raw
		else:
			assert tokens == expected, raw
			assert rest == [], raw


# ---------- 词表守门 ----------
@pytest.mark.parametrize(
	"path",
	[DEFAULT_PATH, EXAMPLE_PATH],
	ids=["data/tags.toml", "data.example/tags.toml"],
)
def test_shipped_vocabulary_has_no_errors(path: Path) -> None:
	if not path.exists():
		pytest.skip(f"词表不存在：{path}")
	vocab = load_vocabulary(path)
	assert vocab.errors == []
	assert vocab.tags


def test_load_vocabulary_missing_file_raises(tmp_path: Path) -> None:
	with pytest.raises(FileNotFoundError):
		load_vocabulary(tmp_path / "nope.toml")
