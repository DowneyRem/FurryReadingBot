from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pyzipper as zf

from storage import zip as zip_sync

logger = logging.getLogger(__name__)


async def zip_files(
	paths: str | Path | list[str | Path],
	*,
	password: str = "",
	zippath: str | Path | None = None,
	comment: str = "",
	delete: bool = False,
) -> Path:
	"""
	异步压缩多个文件成单个 zip（线程池执行，不阻塞事件循环）。

	Args:
		paths: 待压缩的文件路径（单个或列表）。
		password: 压缩密码；为空则不加密。
		zippath: 指定生成的 zip 路径；为空则按源文件自动命名。
		comment: 压缩文件注释。
		delete: 为 True 时，压缩完成后删除源文件。

	Returns:
		生成的 zip 文件路径。
	"""
	return await asyncio.to_thread(
		zip_sync.zip_files,
		paths,
		password=password,
		zippath=zippath,
		comment=comment,
		delete=delete,
	)


async def zip_each_file(
	paths: str | Path | list[str | Path],
	*,
	password: str = "",
	zip_dir: str | Path | None = None,
	comment: str = "",
	delete: bool = False,
) -> list[Path]:
	"""
	异步将每个文件分别压缩为独立的「文件名.zip」。

	Args:
		paths: 待压缩的文件路径（单个或列表）。
		password: 压缩密码；为空则不加密。
		zip_dir: 指定 zip 输出目录，或其下的某个 .zip 路径（仅取其所在目录）；
			为空则在源文件同目录生成。
		comment: 压缩文件注释。
		delete: 为 True 时，压缩完成后删除源文件。

	Returns:
		生成的所有 zip 文件路径列表。
	"""
	return await asyncio.to_thread(
		zip_sync.zip_each_file,
		paths,
		password=password,
		zip_dir=zip_dir,
		comment=comment,
		delete=delete,
	)


async def zip_folder(
	folder: str | Path,
	*,
	password: str = "",
	zippath: str | Path | None = None,
	comment: str = "",
	delete: bool = False,
) -> Path:
	"""
	异步压缩文件夹及其子文件。

	Args:
		folder: 待压缩的文件夹路径。
		password: 压缩密码；为空则不加密。
		zippath: 指定生成的 zip 路径；为空则为「文件夹名.zip」。
		comment: 压缩文件注释。
		delete: 为 True 时，压缩完成后删除源文件夹。

	Returns:
		生成的 zip 文件路径。
	"""
	return await asyncio.to_thread(
		zip_sync.zip_folder,
		folder,
		password=password,
		zippath=zippath,
		comment=comment,
		delete=delete,
	)


async def zip_path(
	path: str | Path | list[str | Path],
	*,
	password: str = "",
	zippath: str | Path | None = None,
	comment: str = "",
	delete: bool = False,
	each: bool = False,
) -> Path | list[Path] | str:
	"""
	异步压缩传入的文件或文件夹。

	Args:
		path: 待压缩的文件 / 文件列表 / 文件夹路径。
		password: 压缩密码；为空则不加密。
		zippath: 指定 zip 路径（或 each 模式下的输出目录）。
		comment: 压缩文件注释。
		delete: 为 True 时，压缩完成后删除源文件/文件夹。
		each: 为 True 时，每个文件单独打成「文件名.zip」；仅对文件/文件列表有效。

	Returns:
		生成的 zip 路径；each=True 时为路径列表；无法压缩时返回空字符串。
	"""
	return await asyncio.to_thread(
		zip_sync.zip_path,
		path,
		password=password,
		zippath=zippath,
		comment=comment,
		delete=delete,
		each=each,
	)


async def unzip_file(
	zippath: str | Path,
	*,
	password: str = "",
	dest: str | Path | None = None,
	nested: bool = True,
	delete: bool = False,
) -> Path:
	"""
	异步解压单个 zip（线程池执行，不阻塞事件循环）。

	Args:
		zippath: 待解压的 zip 文件路径。
		password: 解压密码。
		dest: 指定解压目录；为空则在 zip 同目录智能解压。
		nested: 为 True 时，递归解压 zip 内部的 zip，并删除内部 zip。
		delete: 为 True 时，解压后删除该 zip 源文件。

	Returns:
		解压得到的目录（或主内容路径）。
	"""
	return await asyncio.to_thread(
		zip_sync.unzip_file,
		zippath,
		password=password,
		dest=dest,
		nested=nested,
		delete=delete,
	)


async def unzip_folder(
	folder: str | Path,
	*,
	password: str = "",
	dest: str | Path | None = None,
	nested: bool = False,
	delete: bool = False,
	max_concurrency: int = 4,
) -> Path | str:
	"""
	异步解压目录下所有 zip；多个 zip 在线程池中有限并发。

	Args:
		folder: 含有 zip 文件的文件夹路径。
		password: 解压密码。
		dest: 指定解压目录；为空则在各 zip 旁智能解压。
		nested: 为 True 时，递归解压 zip 内部的 zip。
		delete: 为 True 时，解压后删除 zip 源文件；若同时 nested=True，内部 zip 也会被删。
		max_concurrency: 同时解压的最大 zip 数量，避免磁盘/CPU 打满。

	Returns:
		最后一次成功解压得到的路径；目录下无 zip 时返回空字符串。
	"""
	folder_p = Path(folder)
	zips = sorted(folder_p.rglob("*.zip"))
	if not zips:
		logger.info("%s 目录下无 zip 文件", folder_p)
		return ""

	sem = asyncio.Semaphore(max(1, max_concurrency))

	async def _one(zp: Path) -> Path:
		async with sem:
			logger.info("正在解压：%s", zp)
			return await unzip_file(
				zp, password=password, dest=dest, nested=nested, delete=delete
			)

	results = await asyncio.gather(
		*[_one(zp) for zp in zips],
		return_exceptions=True,
	)

	last: Path | str = ""
	for zp, result in zip(zips, results):
		if isinstance(result, Exception):
			logger.error("解压失败：%s，原因：%s", zp, result)
			continue
		last = result
	return last


async def unzip_path(
	path: str | Path,
	*,
	password: str = "",
	dest: str | Path | None = None,
	nested: bool = False,
	delete: bool = False,
) -> Path | str:
	"""
	异步智能解压：传入 zip 则解压该文件，传入文件夹则解压其下所有 zip。

	Args:
		path: 待解压的 zip 文件，或含有 zip 的文件夹路径。
		password: 解压密码。
		dest: 指定解压目录。
		nested: 为 True 时，递归解压内部 zip。
		delete: 为 True 时，解压后删除 zip 源文件。

	Returns:
		解压得到的路径；无法处理时返回空字符串。
	"""
	path_p = Path(path)
	# is_zipfile 很快，可直接在事件循环调用；若希望绝对不碰同步 IO，也可 to_thread
	if await asyncio.to_thread(zf.is_zipfile, path_p):
		return await unzip_file(
			path_p, password=password, dest=dest, nested=nested, delete=delete
		)
	if path_p.is_dir():
		return await unzip_folder(
			path_p, password=password, dest=dest, nested=nested, delete=delete
		)
	logger.warning("%s 非 zip 文件，亦非含有 zip 的目录", path_p)
	return ""
