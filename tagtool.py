#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tags.toml 的加载 / 校验 / 解析参考实现（parts + parents 版）。

规则：
  - 复合标签（有 parts）：只拆分成基础标签，本身不输出。
  - 原子标签（无 parts）：输出自己，并加上 parents 的传递闭包。
  - parts 与 parents 互斥。
  - parts_mode = "split"   拆分后原样输出，不继承基础标签的上级（默认）
  - parts_mode = "inherit" 拆分后按普通标签解析，会带上各自的上级

Python 3.11+ 用标准库 tomllib；3.10 只需 `pip install tomli`。
用法：python tagtool.py tags.example.toml
"""
from __future__ import annotations

import re
import sys
import unicodedata

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
SPLIT_RE = re.compile(r"[\s/,，、|;；]+")
RESERVED = {"meta"}
PARTS_MODES = {"split", "inherit"}


def normalize(s: str) -> str:
    """NFKC + 去 # + 折叠空白 + casefold。匹配键一律经过这里。"""
    s = unicodedata.normalize("NFKC", s).strip()
    s = s.lstrip("#＃").strip()
    s = re.sub(r"\s+", " ", s)
    return s.casefold()


class Vocabulary:
    def __init__(self, data: dict):
        self.meta = data.get("meta", {})
        self.tags = {k: v for k, v in data.items() if k not in RESERVED}
        self.parts_mode = self.meta.get("parts_mode", "split")
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.alias_index: dict[str, str] = {}
        self._resolved: dict[str, set[str]] = {}
        self._validate()
        self._build_index()
        self._check_cycles()

    # ---------- 校验 ----------
    def _err(self, msg: str) -> None:
        self.errors.append(msg)

    def _warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def _validate(self) -> None:
        if self.parts_mode not in PARTS_MODES:
            self._err(f"meta.parts_mode 必须是 {sorted(PARTS_MODES)} 之一")

        seen: dict[str, str] = {}
        for name, rec in self.tags.items():
            if name in RESERVED:
                self._err(f"{name!r}: 保留名，不能作为标签名")
            if not NAME_RE.match(name):
                self._err(f"{name!r}: 标签名必须是 [A-Za-z][A-Za-z0-9_]*")
            cf = name.casefold()
            if cf in seen:
                self._err(f"标签名仅大小写不同：{seen[cf]!r} 与 {name!r}")
            seen[cf] = name
            if not isinstance(rec, dict):
                self._err(f"{name!r}: 记录必须是表")
                continue
            for field in ("parts", "parents", "aliases"):
                val = rec.get(field, [])
                if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
                    self._err(f"{name}.{field}: 必须是字符串数组")

        for name, rec in self.tags.items():
            if not isinstance(rec, dict):
                continue
            parts = rec.get("parts", [])
            parents = rec.get("parents", [])
            if parts and parents:
                self._err(f"{name}: parts 与 parents 互斥（复合标签只拆分，原子标签才加上级）")
            for field in ("parts", "parents"):
                for ref in rec.get(field, []):
                    if ref not in self.tags:
                        self._err(f"{name}.{field}: 未定义的标签 {ref!r}")
                    elif ref == name:
                        self._err(f"{name}.{field}: 不能引用自己")
            for ref in parents:
                if ref in self.tags and self.tags[ref].get("parts"):
                    self._err(f"{name}.parents: 上级 {ref!r} 是复合标签；上级必须是原子标签")
            if parts and normalize("".join(parts)) != name.casefold():
                self._warn(f"{name}: name 不是 parts 的直接拼接，确认它应为复合标签还是原子标签 + parents")
            if len({normalize(a) for a in rec.get("aliases", [])}) != len(rec.get("aliases", [])):
                self._warn(f"{name}: aliases 内部有重复（已忽略，不影响结果）")

    def _build_index(self) -> None:
        for name, rec in self.tags.items():
            if not isinstance(rec, dict):
                continue
            for surface in [name, *rec.get("aliases", [])]:
                key = normalize(surface)
                if not key:
                    self._err(f"{name}: 空别名")
                    continue
                prev = self.alias_index.get(key)
                if prev is not None and prev != name:
                    self._err(f"别名冲突 {surface!r}: {prev!r} 与 {name!r}")
                self.alias_index[key] = name

    def _check_cycles(self) -> None:
        color = {name: 0 for name in self.tags}
        reported: set[str] = set()

        def dfs(name: str, path: list[str]) -> None:
            color[name] = 1
            rec = self.tags.get(name, {})
            for field in ("parts", "parents"):
                for ref in rec.get(field, []):
                    if ref not in self.tags:
                        continue
                    if color[ref] == 1:
                        cycle = " -> ".join(path + [name, ref])
                        if cycle not in reported:
                            reported.add(cycle)
                            self._err("循环：" + cycle)
                    elif color[ref] == 0:
                        dfs(ref, path + [name])
            color[name] = 2

        for name in self.tags:
            if color[name] == 0:
                dfs(name, [])

    # ---------- 解析 ----------
    def _atoms(self, name: str, stack: tuple[str, ...]) -> set[str]:
        """复合标签拆到原子标签；不继承原子标签的 parents。"""
        if name in stack:
            return set()  # 循环已在校验阶段报告
        parts = self.tags[name].get("parts", [])
        if not parts:
            return {name}
        out: set[str] = set()
        for ref in parts:
            out |= self._atoms(ref, stack + (name,))
        return out

    def resolve(self, name: str, stack: tuple[str, ...] = ()) -> set[str]:
        if name in self._resolved:
            return self._resolved[name]
        if name in stack:
            return set()
        rec = self.tags[name]
        parts = rec.get("parts", [])
        if parts:
            out: set[str] = set()
            for ref in parts:
                if self.parts_mode == "inherit":
                    out |= self.resolve(ref, stack + (name,))
                else:
                    out |= self._atoms(ref, stack + (name,))
        else:
            out = {name}
            for ref in rec.get("parents", []):
                out |= self.resolve(ref, stack + (name,))
        self._resolved[name] = out
        return out

    def resolve_one(self, raw: str) -> list[str] | None:
        key = normalize(raw)
        if not key:
            return None
        hit = self.alias_index.get(key)
        if hit is not None:  # 整串优先：允许带空格的来源标签
            return [hit]
        pieces = [p for p in SPLIT_RE.split(key) if p]
        if len(pieces) > 1:  # 再按分隔符拆：gay/furry、R18,兽人
            names = [self.alias_index.get(p) for p in pieces]
            if all(n is not None for n in names):
                return names  # type: ignore[return-value]
        return None

    def sort_key(self, name: str):
        rec = self.tags.get(name, {})
        return (rec.get("order", 10**6), name)

    def resolve_all(self, raws) -> tuple[list[str], list[str]]:
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


def main(path: str) -> int:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    vocab = Vocabulary(data)
    print(f"tags={len(vocab.tags)}  alias_keys={len(vocab.alias_index)}  errors={len(vocab.errors)}  warnings={len(vocab.warnings)}")
    for e in vocab.errors:
        print("  ERROR", e)
    for w in vocab.warnings:
        print("  WARN ", w)
    if vocab.errors:
        return 1

    print("\n解析示例：")
    demos = ["ケモホモ", "Gay Furry", "gay/furry", "GAYFURRY", "Ｒ１８", "r-18", "CBT", "獸人", "兽化", "完全未知"]
    for raw in demos:
        toks, rest = vocab.resolve_all([raw])
        shown = " ".join("#" + t for t in toks) if toks else "(residual) " + " ".join(rest)
        print(f"  {raw!r:16} -> {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "tags.example.toml"))
