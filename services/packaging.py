"""下载打包：把来源返回的模型写成 txt / zip。

来源（`sources/`）只负责拉取并解析模型；落盘、命名、压缩都在这里。
每次打包使用独立的临时工作目录，产物交付后整目录删除，
不同下载之间不会共享目录、互相覆盖或混入旧文件。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Iterable

from infra.archive import zip_path
from infra.files import remove_file, safe_filename, save_text
from sources import resolve_source
from sources.base import Novel, NovelSource, Series
from sources.format import format_novel_text, format_series_text
from sources.utils import is_real_series


logger = logging.getLogger(__name__)


WORK_ROOT = Path(__file__).resolve().parents[1] / "files" / "work"
# 同一次打包里并发拉取章节的上限，避免对来源站点突发请求
FETCH_CONCURRENCY = 4


async def build(link: str, file_type: str = "auto", *, work_root: Path = WORK_ROOT) -> Path:
	"""拉取链接对应的作品并打包，返回产物路径（位于独立工作目录内）。

	file_type 只对系列生效：txt / zip 指定格式，其他值按章节标题自动判断。
	"""
	source = resolve_source(link)
	if source is None:
		raise ValueError(f"暂不支持该链接：{link}")

	work_root.mkdir(parents=True, exist_ok=True)
	workdir = Path(tempfile.mkdtemp(prefix="dl-", dir=work_root))
	try:
		if source.is_novel_link(link):
			novel = await source.fetch_novel(link)
			return await _write_novel(novel, workdir)
		if source.is_series_link(link):
			series = await source.fetch_series(link)
			novels = await _fetch_novels(source, series.novel_ids)
			if _series_as_txt(series, file_type):
				return await _write_series_txt(series, novels, workdir)
			folder = await _write_series_dir(series, novels, workdir)
			return await zip_path(folder, delete=True)
		return await _build_author(source, link, workdir)
	except BaseException:
		await remove_file(workdir)
		raise


def clear_work_root(work_root: Path = WORK_ROOT) -> None:
	"""启动时清空打包目录：上次进程被强杀时可能留下未交付的工作目录。"""
	if work_root.exists():
		shutil.rmtree(work_root)


async def discard(path: Path, *, work_root: Path = WORK_ROOT) -> None:
	"""删除产物；产物位于打包工作目录内时，连同工作目录一起删除。"""
	if path.parent.parent == work_root:
		await remove_file(path.parent)
	else:
		await remove_file(path)


async def _build_author(source: NovelSource, link: str, workdir: Path) -> Path:
	author = await source.fetch_author(link)
	root = workdir / safe_filename(author.author_name)
	in_series: set[str] = set()
	failures: list[Exception] = []
	for series_id in author.series_ids:
		try:
			series = await source.fetch_series(series_id)
			in_series.update(series.novel_ids)
			novels = await _fetch_novels(source, series.novel_ids)
		except Exception as error:
			# 单个系列抓不到（已删除 / 无权限 / 全部章节失败）不该拖垮整包：
			# 先记下来继续跑，最后一篇都没写出来时再把第一个原因抛出。
			failures.append(error)
			logger.warning(
				"作者 %s 的系列 %s 抓取失败，已跳过：%s",
				author.author_name, series_id, error, exc_info=error,
			)
			continue
		# 写盘不放进上面的 try：磁盘错误要上抛，不能当成「跳过一章」
		if _series_as_txt(series, "auto"):
			await _write_series_txt(series, novels, root)
		else:
			await _write_series_dir(series, novels, root)

	single_ids = [nid for nid in author.novel_ids if nid not in in_series]
	try:
		singles = await _fetch_novels(source, single_ids)
	except Exception as error:
		failures.append(error)
		logger.warning(
			"作者 %s 的单篇全部抓取失败，已跳过：%s",
			author.author_name, error, exc_info=error,
		)
		singles = []
	for novel in singles:
		await _write_novel(novel, root / "单篇")

	root.mkdir(parents=True, exist_ok=True)
	if failures and not any(root.rglob("*.txt")):
		raise failures[0]
	return await zip_path(root, delete=True)


async def _fetch_novels(source: NovelSource, novel_ids: Iterable[str]) -> list[Novel]:
	"""限并发拉取多篇，结果保持输入顺序，单章失败只跳过该章。

	网络 / 权限 / 解析失败都写 warning 后继续，避免一篇坏章拖垮整个系列或作者包；
	只有「一篇都没拿到」时才抛出第一个异常，让调用方给出失败提示。
	"""
	ids = [str(novel_id) for novel_id in novel_ids]
	if not ids:
		return []
	semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

	async def fetch_one(novel_id: str) -> Novel:
		async with semaphore:
			return await source.fetch_novel(novel_id)

	results = await asyncio.gather(*(fetch_one(nid) for nid in ids), return_exceptions=True)
	novels: list[Novel] = []
	failures: list[tuple[str, Exception]] = []
	for novel_id, result in zip(ids, results):
		if isinstance(result, BaseException):
			if not isinstance(result, Exception):
				# CancelledError 等系统级异常继续上抛，不要当成「坏章节」吞掉
				raise result
			failures.append((novel_id, result))
			logger.warning("章节 %s 抓取失败，已跳过：%s", novel_id, result, exc_info=result)
			continue
		novels.append(result)

	if failures:
		logger.warning(
			"本次共跳过 %d 章：%s",
			len(failures), "、".join(nid for nid, _ in failures),
		)
	if failures and not novels:
		raise failures[0][1]
	return novels


def _series_as_txt(series: Series, file_type: str) -> bool:
	if file_type in ("txt", "zip"):
		return file_type == "txt"
	return is_real_series(series)


async def _write_novel(novel: Novel, folder: Path) -> Path:
	path = _unique_path(folder / f"{safe_filename(novel.title)}.txt")
	return await save_text(path, format_novel_text(novel))


async def _write_series_txt(series: Series, novels: list[Novel], folder: Path) -> Path:
	path = _unique_path(folder / f"{safe_filename(series.title)}.txt")
	return await save_text(path, format_series_text(series, novels))


async def _write_series_dir(series: Series, novels: list[Novel], folder: Path) -> Path:
	"""系列分章写入同名目录；文件名带序号，保证顺序且同名章节不互相覆盖。"""
	target = _unique_path(folder / safe_filename(series.title))
	target.mkdir(parents=True)
	width = len(str(len(novels)))
	for index, novel in enumerate(novels, start=1):
		name = f"{index:0{width}d}_{safe_filename(novel.title)}.txt"
		await save_text(target / name, format_novel_text(novel))
	return target


def _unique_path(path: Path) -> Path:
	"""目标已存在时追加「 (2)」「 (3)」…，避免同名作品互相覆盖。"""
	if not path.exists():
		return path
	stem, suffix = path.stem, path.suffix
	index = 2
	while True:
		candidate = path.with_name(f"{stem} ({index}){suffix}")
		if not candidate.exists():
			return candidate
		index += 1
