"""标签词表（tags.toml）：加载 / 校验 / 解析。

设计见 docs/08-标签词表.md：
	- 复合标签（有 parts）：只拆成基础标签，自身不输出；
	- 原子标签（无 parts）：输出自己 + parents 的传递闭包；
	- parts 与 parents 互斥，且上级只能是原子标签；
	- parts_mode = "split" 拆分后不继承上级（默认）；"inherit" 拆分后按普通标签继续解析。

本模块不碰网络与 Telegram：给一份 TOML 数据，得到规范标签集合。
校验在 `Vocabulary` 构造时完成，结果读 `errors` / `warnings`：
errors 非空应阻断启动，warnings 打日志即可。改完词表跑
`pytest test/test_tags.py -q`（含两份词表的守门用例）就能确认没写坏。
"""

from __future__ import annotations

import re
import tomllib
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
SPLIT_RE = re.compile(r"[\s/,，、|;；]+")
# 顶层非标签的保留键
RESERVED = {"meta"}
PARTS_MODES = {"split", "inherit"}
MATCH_MODES = {"casefold"}
SUPPORTED_SCHEMA = 2
DEFAULT_ORDER = 10**6
# 这些组的规范名惯例是全小写（#en #zh #txt），其余组建议 PascalCase
LOWERCASE_GROUPS = {"format", "lang"}
DEFAULT_PATH = Path(__file__).parent.parent.resolve() / "data" / "tags.toml"


def normalize(s: str) -> str:
	"""NFKC + 去 # + 折叠空白 + casefold。所有匹配键都经过这里。"""
	s = unicodedata.normalize("NFKC", s).strip()
	s = s.lstrip("#＃").strip()
	s = re.sub(r"\s+", " ", s)
	return s.casefold()


def _is_str_list(value: Any) -> bool:
	return isinstance(value, list) and all(isinstance(x, str) for x in value)


class Vocabulary:
	"""一份 tags.toml 的解析结果：别名索引 + 输出闭包 + 校验问题。"""

	def __init__(self, data: dict[str, Any]) -> None:
		meta = data.get("meta")
		self.meta: dict[str, Any] = meta if isinstance(meta, dict) else {}
		self.tags: dict[str, Any] = {
			str(key): value for key, value in data.items() if key not in RESERVED
		}
		self.parts_mode: str = str(self.meta.get("parts_mode") or "split")
		self.errors: list[str] = []
		self.warnings: list[str] = []
		self.alias_index: dict[str, str] = {}
		# 组 → 序号，决定输出顺序的第一关键字
		self.group_rank: dict[str, int] = {}
		self._resolved: dict[str, set[str]] = {}
		self._validate()
		self._build_index()
		self._build_group_rank()
		self._check_cycles()

	# ---------- 校验 ----------
	def _err(self, msg: str) -> None:
		self.errors.append(msg)

	def _warn(self, msg: str) -> None:
		self.warnings.append(msg)

	def _validate(self) -> None:
		schema = self.meta.get("schema")
		if schema is None:
			self._warn("meta.schema 未配置，按 schema=2 处理")
		elif schema != SUPPORTED_SCHEMA:
			self._err(f"meta.schema 必须是 {SUPPORTED_SCHEMA}，当前为 {schema!r}")
		match = self.meta.get("match")
		if match is not None and match not in MATCH_MODES:
			self._err(f"meta.match 只支持 {sorted(MATCH_MODES)}；归一规则写死在 normalize() 里")
		if self.parts_mode not in PARTS_MODES:
			self._err(f"meta.parts_mode 必须是 {sorted(PARTS_MODES)} 之一")

		seen: dict[str, str] = {}
		for name, rec in self.tags.items():
			if not NAME_RE.match(name):
				self._err(f"{name!r}: 标签名必须是 [A-Za-z][A-Za-z0-9_]*")
			cf = name.casefold()
			if cf in seen:
				self._err(f"标签名仅大小写不同：{seen[cf]!r} 与 {name!r}")
			seen[cf] = name
			if not isinstance(rec, dict):
				self._err(f"{name!r}: 记录必须是表")
				continue
			group = rec.get("group")
			if group is not None and not isinstance(group, str):
				self._err(f"{name}.group: 必须是字符串")
			elif isinstance(group, str) and group not in LOWERCASE_GROUPS and not name[:1].isupper():
				self._warn(f"{name!r}: 建议改成 PascalCase（输出就是 #{name}）")
			order = rec.get("order")
			if order is not None and (not isinstance(order, int) or isinstance(order, bool)):
				self._err(f"{name}.order: 必须是整数，当前为 {order!r}")
			for field in ("parts", "parents", "aliases"):
				if field in rec and not _is_str_list(rec[field]):
					self._err(f"{name}.{field}: 必须是字符串数组")

		for name, rec in self.tags.items():
			if not isinstance(rec, dict):
				continue
			parts = rec.get("parts") if _is_str_list(rec.get("parts")) else []
			parents = rec.get("parents") if _is_str_list(rec.get("parents")) else []
			if parts and parents:
				self._err(f"{name}: parts 与 parents 互斥（复合标签只拆分，原子标签才加上级）")
			for field in ("parts", "parents"):
				refs = rec.get(field) if _is_str_list(rec.get(field)) else []
				for ref in refs:
					if ref not in self.tags:
						self._err(f"{name}.{field}: 未定义的标签 {ref!r}")
					elif ref == name:
						self._err(f"{name}.{field}: 不能引用自己")
			for ref in parents:
				target = self.tags.get(ref)
				if isinstance(target, dict) and target.get("parts"):
					self._err(f"{name}.parents: 上级 {ref!r} 是复合标签；上级必须是原子标签")
			for ref in parts:
				target = self.tags.get(ref)
				if isinstance(target, dict) and target.get("parts"):
					self._err(f"{name}.parts: {ref!r} 也是复合标签；parts 不支持嵌套")
			if parts and normalize("".join(parts)) != name.casefold():
				self._warn(f"{name}: name 不是 parts 的直接拼接，确认它应为复合标签还是原子标签 + parents")
			aliases = rec.get("aliases") if _is_str_list(rec.get("aliases")) else []
			if len({normalize(alias) for alias in aliases}) != len(aliases):
				self._warn(f"{name}: aliases 内部有重复（已忽略，不影响结果）")
			if any(normalize(alias) == name.casefold() for alias in aliases):
				self._warn(f"{name}: 不必把规范名自己写进 aliases")

	# ---------- 索引 ----------
	def _build_index(self) -> None:
		"""规范名 + 别名 → 匹配键索引；归一后全局唯一。"""
		for name, rec in self.tags.items():
			if not isinstance(rec, dict):
				continue
			aliases = rec.get("aliases") if _is_str_list(rec.get("aliases")) else []
			for surface in [name, *aliases]:
				key = normalize(surface)
				if not key:
					self._err(f"{name}: 空别名")
					continue
				prev = self.alias_index.get(key)
				if prev is not None and prev != name:
					self._err(f"别名冲突 {surface!r}: {prev!r} 与 {name!r}")
				self.alias_index[key] = name

	def _build_group_rank(self) -> None:
		"""组顺序：meta.groups 显式声明，否则按词表里 group 首次出现的顺序。"""
		declared = self.meta.get("groups")
		if _is_str_list(declared) and declared:
			order = list(dict.fromkeys(declared))
			self.group_rank = {group: index for index, group in enumerate(order)}
			for name, rec in self.tags.items():
				group = rec.get("group") if isinstance(rec, dict) else None
				if isinstance(group, str) and group and group not in self.group_rank:
					self._warn(f"{name}.group: {group!r} 不在 meta.groups 里，排在最后")
			return
		derived: list[str] = []
		for rec in self.tags.values():
			group = rec.get("group") if isinstance(rec, dict) else None
			if isinstance(group, str) and group and group not in derived:
				derived.append(group)
		self.group_rank = {group: index for index, group in enumerate(derived)}

	def _check_cycles(self) -> None:
		color = {name: 0 for name in self.tags}
		reported: set[str] = set()

		def dfs(name: str, path: list[str]) -> None:
			color[name] = 1
			rec = self.tags.get(name)
			rec = rec if isinstance(rec, dict) else {}
			for field in ("parts", "parents"):
				refs = rec.get(field) if _is_str_list(rec.get(field)) else []
				for ref in refs:
					if ref not in self.tags:
						continue
					if color[ref] == 1:
						cycle = " -> ".join([*path, name, ref])
						if cycle not in reported:
							reported.add(cycle)
							self._err("循环：" + cycle)
					elif color[ref] == 0:
						dfs(ref, [*path, name])
			color[name] = 2

		for name in self.tags:
			if color[name] == 0:
				dfs(name, [])

	# ---------- 解析 ----------
	def _atoms(self, name: str, stack: tuple[str, ...]) -> set[str]:
		"""复合标签拆到原子标签；不继承原子标签的 parents。"""
		if name in stack or name not in self.tags:
			return set()  # 循环已在校验阶段报告
		rec = self.tags[name]
		parts = rec.get("parts") if _is_str_list(rec.get("parts")) else []
		if not parts:
			return {name}
		out: set[str] = set()
		for ref in parts:
			out |= self._atoms(ref, (*stack, name))
		return out

	def resolve(self, name: str, stack: tuple[str, ...] = ()) -> set[str]:
		"""规范名 → 输出集合（只有原子标签）。"""
		cached = self._resolved.get(name)
		if cached is not None:
			return cached
		if name in stack or name not in self.tags:
			return set()
		rec = self.tags[name]
		parts = rec.get("parts") if _is_str_list(rec.get("parts")) else []
		out: set[str]
		if parts:
			out = set()
			for ref in parts:
				if self.parts_mode == "inherit":
					out |= self.resolve(ref, (*stack, name))
				else:
					out |= self._atoms(ref, (*stack, name))
		else:
			out = {name}
			parents = rec.get("parents") if _is_str_list(rec.get("parents")) else []
			for ref in parents:
				out |= self.resolve(ref, (*stack, name))
		self._resolved[name] = out
		return out

	def resolve_one(self, raw: str) -> list[str] | None:
		"""任意来源写法 → 命中的规范名；完全不命中返回 None。"""
		key = normalize(raw)
		if not key:
			return None
		hit = self.alias_index.get(key)
		if hit is not None:  # 整串优先：允许带空格的来源标签
			return [hit]
		pieces = [piece for piece in SPLIT_RE.split(key) if piece]
		if len(pieces) > 1:  # 再按分隔符拆：gay/furry、R18,兽人
			names = [self.alias_index.get(piece) for piece in pieces]
			if all(name is not None for name in names):
				return list(dict.fromkeys(names))  # 去重：gay/gay 只算一次
		return None

	def resolve_all(self, raws: Iterable[str]) -> tuple[list[str], list[str]]:
		"""批量解析 → （已排序的规范名，未识别的原始串）。"""
		out: set[str] = set()
		rest: list[str] = []
		for raw in raws:
			hits = self.resolve_one(raw)
			if hits is None:
				rest.append(raw)
				continue
			for name in hits:
				out |= self.resolve(name)
		return sorted(out, key=self.sort_key), rest

	def sort_key(self, name: str) -> tuple[int, int, str]:
		"""输出顺序：group（声明序/首次出现序）→ order → 名字。"""
		rec = self.tags.get(name)
		rec = rec if isinstance(rec, dict) else {}
		group = rec.get("group")
		tail = len(self.group_rank)
		rank = self.group_rank.get(group, tail) if isinstance(group, str) else tail
		order = rec.get("order")
		if not isinstance(order, int) or isinstance(order, bool):
			order = DEFAULT_ORDER
		return rank, order, name


def load_vocabulary(path: str | Path | None = None) -> Vocabulary:
	"""读一份 tags.toml 并完成校验。

	文件缺失 / TOML 语法错误直接抛异常，交给启动流程处理；
	结构性问题不抛异常，读 `Vocabulary.errors`（非空应阻断启动）与 `warnings`。
	"""
	target = Path(path) if path is not None else DEFAULT_PATH
	with target.open("rb") as file:
		return Vocabulary(tomllib.load(file))
