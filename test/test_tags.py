"""标签词表：归一 / 拆分 / 上级闭包 / 匹配与排序 / 校验。

两份词表各有一条守门用例：词表改坏（errors 非空）时 CI 直接红。
运行：python -m pytest test/test_tags.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sources.tags import DEFAULT_PATH, Vocabulary, load_vocabulary, normalize

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
