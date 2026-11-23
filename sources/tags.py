"""标签词表（tags.toml）：加载 / 校验 / 解析。

设计见 docs/08-标签词表.md：
	- 复合标签（有 parts）：只拆成基础标签，自身不输出；不能写 print；
	- 分类标签（有 parents）：默认输出自己 + parents 的传递闭包；
	  print = false 时只输出父集（自身透明）；print = true 等价默认；
	- 纯原子标签（无 parts、无 parents）：输出自己；不能写 print；
	- parts 与 parents 互斥，且上级只能是原子标签；
	- parts_mode = "split" 拆分后不继承上级（默认）；"inherit" 拆分后按普通标签继续解析；
	- TOML 字段 print 在 Python 内读取为 print_self，避免遮蔽内置 print。

本模块不碰网络与 Telegram：给一份 TOML 数据，得到规范标签集合。
校验在 `Vocabulary` 构造时完成，结果读 `errors` / `warnings`：
errors 非空应阻断启动，warnings 打日志即可。改完词表跑
`pytest test/test_tags.py -q`（含两份词表的守门用例）就能确认没写坏。

运行时用 `get_vocabulary()` 拿进程内唯一实例（首次加载就把 errors / warnings 写进日志）。

接线方式：**数据入口一次搞定**。`sources.base` 的 `Novel/Series/Author.__post_init__`
调用 `canonicalize_tags()` 把来源写法换成规范名——txt 头部、私聊文案、缓存、分享都自动生效，
新代码不需要再接线。未识别写法的留档**不在这里写盘**：

	set_unknown_recorder(fn)  由 services 启动时装配（services/tag_service.install_tag_archive）
	                          fn 为空时只打 debug 日志，sources 不 import storage
	canonicalize_tags()       入口规范化：不截断；词表缺失 / 出错时原样返回，不阻断抓取
	display_tags()            展示：排序 + 截断 + 未识别写法原样带出（业务侧要限流时用）
"""

from __future__ import annotations

import logging
import re
import tomllib
import unicodedata
from collections.abc import Callable, Iterable
from functools import lru_cache
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
logger = logging.getLogger(__name__)

# 未识别写法的留档实现：(归一键, 原样写法) → 写入 data/unknown_tags.json
# 由 services 层启动时注入；默认是空实现，保证 sources 不依赖 storage
UnknownRecorder = Callable[[Iterable[tuple[str, str]]], object]


def _ignore_unknown(_entries: Iterable[tuple[str, str]]) -> None:
	"""默认留档实现：什么都不做（没装配时 sources 不碰存储）。"""


_recorder: UnknownRecorder = _ignore_unknown


def normalize(s: str) -> str:
	"""NFKC + 去 # + 折叠空白 + casefold。所有匹配键都经过这里。"""
	s = unicodedata.normalize("NFKC", s).strip()
	s = s.lstrip("#＃").strip()
	s = re.sub(r"\s+", " ", s)
	return s.casefold()


def _surface(raw: str) -> str:
	"""展示用的原样写法：NFKC + 去前导 #，其余保持来源大小写。"""
	text = unicodedata.normalize("NFKC", raw).strip()
	return text.lstrip("#＃").strip()


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
		# 只存顶层解析结果，且是不可变集合：对外一律给副本
		self._resolved: dict[str, frozenset[str]] = {}
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
			if "print" in rec:
				print_self = rec["print"]
				if not isinstance(print_self, bool):
					self._err(f"{name}.print: 必须是布尔值")
				if parts:
					self._err(f"{name}: parts 节点不能设置 print（parts 永不输出自身）")
				elif not parents:
					self._err(f"{name}: print 只能用于有 parents 的标签")
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
		"""复合标签拆到原子标签；不继承原子标签的 parents；print=false 的原子部分不输出。"""
		if name in stack or name not in self.tags:
			return set()  # 循环已在校验阶段报告
		rec = self.tags[name]
		if not isinstance(rec, dict):
			return set()  # 记录结构非法，已在校验阶段报 ERROR
		parts = rec.get("parts") if _is_str_list(rec.get("parts")) else []
		if not parts:
			print_self = rec.get("print", True)
			return {name} if print_self is not False else set()
		out: set[str] = set()
		for ref in parts:
			out |= self._atoms(ref, (*stack, name))
		return out


	def resolve(self, name: str) -> set[str]:
		"""规范名 → 输出集合（只有原子标签）。

		纯函数：不排序、不落盘。未知名只返回空集合（打 debug，不写进
		`unknown_tags`——入参已经是规范名，不命中说明调用方写了词表里没有的名字）。

		返回的是副本：调用方随便 `add` / `|=` 都改不到内部缓存。
		"""
		if name not in self.tags:
			logger.debug("resolve() 收到词表里没有的规范名：%r", name)
		return set(self._resolve(name, ()))

	def _resolve(self, name: str, stack: tuple[str, ...]) -> set[str]:
		"""带防环栈的递归实现：只有顶层结果（stack 为空）才写缓存。

		递归中途的局部结果会被 `stack` 截断（环已在校验阶段报 ERROR），
		写进缓存会把错误结果永久留下来，所以一律不缓存、不改缓存。
		"""
		cached = self._resolved.get(name)
		if cached is not None:
			return set(cached)
		if name in stack or name not in self.tags:
			return set()
		rec = self.tags[name]
		if not isinstance(rec, dict):
			return set()
		parts = rec.get("parts") if _is_str_list(rec.get("parts")) else []
		out: set[str]
		if parts:
			out = set()
			for ref in parts:
				if self.parts_mode == "inherit":
					out |= self._resolve(ref, (*stack, name))
				else:
					out |= self._atoms(ref, (*stack, name))
		else:
			print_self = rec.get("print", True)
			out = {name} if print_self is not False else set()
		parents = rec.get("parents") if _is_str_list(rec.get("parents")) else []
		for ref in parents:
			out |= self._resolve(ref, (*stack, name))
		if not stack:
			self._resolved[name] = frozenset(out)
		return out.copy()


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


	def resolve_all(
		self, raws: Iterable[str], *, record: bool = True
	) -> tuple[list[str], list[str]]:
		"""批量解析 → （已排序的规范名，未识别的原始串）。

		解析到此为止：这是**唯一的留档点**——未识别写法默认写进
		`data/unknown_tags.json`（同一次调用内去重，`count` 记「作品数」）。
		`record=False` 只解析不留档（试规则 / 单测）。
		"""
		out: set[str] = set()
		rest: list[str] = []
		for raw in raws:
			hits = self.resolve_one(raw)
			if hits is None:
				rest.append(raw)
				continue
			for name in hits:
				out |= self.resolve(name)
		if record and rest:
			_record_residual(rest)
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


# ---------- 加载 ----------
def load_vocabulary(path: str | Path | None = None) -> Vocabulary:
	"""读一份 tags.toml 并完成校验。

	文件缺失 / TOML 语法错误直接抛异常，交给启动流程处理；
	结构性问题不抛异常，读 `Vocabulary.errors`（非空应阻断启动）与 `warnings`。
	"""
	target = Path(path) if path is not None else DEFAULT_PATH
	with target.open("rb") as file:
		return Vocabulary(tomllib.load(file))


@lru_cache(maxsize=1)
def get_vocabulary() -> Vocabulary:
	"""进程内共享一份词表：首次调用时加载 + 校验，之后只读。

	docs/08 §7 要求「只加载一次」；errors / warnings 在这里直接写日志，
	启动流程只需要检查 `get_vocabulary().errors` 是否为空。
	文件缺失或 TOML 语法错误照旧抛异常（`lru_cache` 不会缓存异常）。
	"""
	vocab = load_vocabulary()
	for error in vocab.errors:
		logger.error("标签词表：%s", error)
	for warning in vocab.warnings:
		logger.warning("标签词表：%s", warning)
	return vocab


# ---------- 展示与未识别记账 ----------
# 评级互斥（业务约定，见 docs/08 §7）：命中 R18 / R18G 时 SFW 不成立。
# 词表里 R18G 的 parents 是 R18，闭包已经带上 R18，所以只看这两个规范名。
EXCLUSIVE_RATINGS = frozenset({"R18", "R18G"})
EXCLUDED_BY_EXCLUSIVE = frozenset({"SFW"})


def set_unknown_recorder(recorder: UnknownRecorder | None) -> None:
	"""装配未识别写法的留档实现（services 启动时调用一次；传 None 恢复空实现）。

	sources 只调用回调，不 import storage —— 留档位置由上层决定（现在是
	`data/unknown_tags.json`，见 `services/tag_service.install_tag_archive()`）。
	"""
	global _recorder
	_recorder = recorder or _ignore_unknown


def _apply_rating_exclusion(tokens: list[str]) -> list[str]:
	"""评级互斥：出现 R18 / R18G 时丢掉 SFW（来源两者都标时按 R18 优先）。"""
	if EXCLUSIVE_RATINGS.isdisjoint(tokens):
		return tokens
	return [tag for tag in tokens if tag not in EXCLUDED_BY_EXCLUSIVE]


def display_tags(
	raws: Iterable[str] | None,
	*,
	limit: int | None = 8,
	vocab: Vocabulary | None = None,
	record: bool = True,
) -> list[str]:
	"""来源写法 → 可直接展示的标签列表（排序 + 截断 + 未识别写法原样带出）。

	- 规范标签按 group / order 排序，`limit` 只约束**规范标签**的数量
	  （`None` 不截断；未识别写法通常很少，不占这个名额，免得被截掉后看不见）；
	- 未识别写法只做全角归一 + 去前导 `#`（大小写保持来源原样），按出现顺序去重，
	  追加在规范标签之后；
	- 评级互斥：规范标签里同时出现 `R18` / `R18G` 时丢掉 `SFW`（先互斥再截断）；
	- 留档由 `resolve_all()` 触发（`record` 透传），一次调用只记一次；
	- `record=False` 只展示不留档（试规则 / 单测 / 自定义词表）；
	- 落盘失败只打 warning，不影响返回结果。
	"""
	vocabulary = vocab if vocab is not None else get_vocabulary()
	tokens, residual = vocabulary.resolve_all(raws or [], record=record)
	tokens = _apply_rating_exclusion(tokens)
	unknown = list(_unique_surfaces(residual).values())
	if limit is not None:
		tokens = tokens[:limit]
	return tokens + unknown


def canonicalize_tags(raws: Iterable[str] | None) -> list[str]:
	"""数据入口规范化：不截断，词表缺失 / 出错时原样返回，绝不阻断抓取。

	`Novel/Series/Author.__post_init__` 用它，所以「构造即规范」：txt 头部、私聊文案、
	file_id 缓存、分享都直接拿到规范标签。幂等：已经规范的写法再跑一遍结果不变。
	"""
	values = [str(raw) for raw in (raws or []) if isinstance(raw, str) and raw.strip()]
	if not values:
		return []
	try:
		return display_tags(values, limit=None)
	except Exception:
		logger.warning("标签规范化失败，保留原始写法", exc_info=True)
		return values


def _unique_surfaces(residual: Iterable[str]) -> dict[str, str]:
	"""residual → {归一键: 原样写法}，保持首次出现顺序；空写法直接跳过。"""
	surfaces: dict[str, str] = {}
	for raw in residual:
		if not isinstance(raw, str):
			continue
		surface = _surface(raw)
		key = normalize(surface)
		if not key:
			continue
		surfaces.setdefault(key, surface)
	return surfaces


def _record_residual(residual: Iterable[str]) -> None:
	"""未识别写法留档：同一次解析内按归一写法去重（`count` = 作品数）。"""
	surfaces = _unique_surfaces(residual)
	if not surfaces:
		return
	logger.debug("标签未识别（已原样带出，可补 aliases）：%s", list(surfaces.values()))
	try:
		_recorder(surfaces.items())
	except Exception:
		# 只是记账：磁盘满 / 权限不对都不该让下载和分享失败
		logger.warning("未识别标签落盘失败（不影响解析与展示）", exc_info=True)
