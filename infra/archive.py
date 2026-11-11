"""压缩 / 解压：同步实现 + 异步包装（线程池执行）。

原来 ``storage/zip.py`` 与 ``storage/zip_async.py`` 的职责合并到这里，
业务侧统一使用模块底部的异步 API。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Iterable

import pyzipper as zf

logger = logging.getLogger(__name__)


def _as_paths(path: str | Path | Iterable[str | Path]) -> list[Path]:
	"""把单个路径或路径列表统一成 list[Path]。"""
	if isinstance(path, (str, Path)):
		return [Path(path)]
	return [Path(p) for p in path]


def _open_zip(zippath: Path, *, password: str = "", mode: str = "w"):
	"""打开 AESZipFile；有密码时启用 AES 加密。"""
	encryption = zf.WZ_AES if password else None
	return zf.AESZipFile(zippath, mode, compression=zf.ZIP_DEFLATED, encryption=encryption)


def _apply_password_and_comment(z, password: str = "", comment: str = "") -> None:
	"""写入密码与注释（comment 仅支持 bytes）。"""
	if password:
		z.setpassword(password.encode("utf-8"))
	if comment:
		z.comment = comment.encode("utf-8")


def _common_path(paths: list[Path | str]) -> Path:
	"""多个路径的共同父路径。"""
	import os
	return Path(os.path.commonpath([str(p) for p in paths]))


def _zip_files(
	paths: str | Path | list[str | Path],
	*,
	password: str = "",
	zippath: str | Path | None = None,
	comment: str = "",
	delete: bool = False,
) -> Path:
	"""
	压缩多个文件成单个 zip；使用 pyzipper 可用 AES256 加密。

	Args:
		paths: 待压缩的文件路径（单个或列表）。
		password: 压缩密码；为空则不加密。
		zippath: 指定生成的 zip 路径；为空则按源文件自动命名。
		comment: 压缩文件注释。
		delete: 为 True 时，压缩完成后删除源文件。

	Returns:
		生成的 zip 文件路径。
	"""
	files = _as_paths(paths)
	if not files:
		raise ValueError("没有可压缩的文件")

	folder = files[0].parent if len(files) == 1 else _common_path(files)
	if zippath:
		out = Path(zippath)
	elif len(files) == 1:
		out = files[0].with_suffix(".zip")
	else:
		out = folder.with_suffix(".zip")

	out.parent.mkdir(parents=True, exist_ok=True)
	if out.exists():
		out.unlink()

	with _open_zip(out, password=password) as z:
		_apply_password_and_comment(z, password, comment)
		for f in files:
			z.write(f, arcname=str(f.relative_to(folder)))

	if delete:
		for f in files:
			f.unlink(missing_ok=True)
	logger.info("压缩完成：%s", out)
	return out


def _zip_each_file(
	paths: str | Path | list[str | Path],
	*,
	password: str = "",
	zip_dir: str | Path | None = None,
	comment: str = "",
	delete: bool = False,
) -> list[Path]:
	"""
	将每个文件分别压缩为独立的「文件名.zip」；使用 pyzipper 可用 AES256 加密。

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
	files = _as_paths(paths)
	results: list[Path] = []

	base: Path | None = None
	if zip_dir:
		base = Path(zip_dir)
		if base.suffix.lower() == ".zip":
			base = base.parent
		base.mkdir(parents=True, exist_ok=True)

	root = files[0].parent if len(files) == 1 else _common_path(files)

	for f in files:
		if base is not None:
			rel = f.name if len(files) == 1 else f.relative_to(root)
			out = base / Path(rel).with_suffix(".zip")
		else:
			out = f.with_suffix(".zip")

		out.parent.mkdir(parents=True, exist_ok=True)
		if out.exists():
			out.unlink()

		with _open_zip(out, password=password) as z:
			_apply_password_and_comment(z, password, comment)
			z.write(f, arcname=f.name)

		results.append(out)
		logger.info("压缩完成：%s", out)

	if delete:
		for f in files:
			f.unlink(missing_ok=True)
	return results


def _zip_folder(
	folder: str | Path,
	*,
	password: str = "",
	zippath: str | Path | None = None,
	comment: str = "",
	delete: bool = False,
) -> Path:
	"""
	压缩文件夹及其子文件；使用 pyzipper 可用 AES256 加密。

	Args:
		folder: 待压缩的文件夹路径。
		password: 压缩密码；为空则不加密。
		zippath: 指定生成的 zip 路径；为空则为「文件夹名.zip」。
		comment: 压缩文件注释。
		delete: 为 True 时，压缩完成后删除源文件夹。

	Returns:
		生成的 zip 文件路径。
	"""
	folder = Path(folder)
	if not folder.is_dir():
		raise NotADirectoryError(folder)

	out = Path(zippath) if zippath else folder.parent / f"{folder.name}.zip"
	out.parent.mkdir(parents=True, exist_ok=True)
	if out.exists():
		out.unlink()

	parent = folder.parent
	with _open_zip(out, password=password) as z:
		_apply_password_and_comment(z, password, comment)
		for f in folder.rglob("*"):
			if f.is_file():
				z.write(f, arcname=str(f.relative_to(parent)))

	if delete:
		import shutil
		shutil.rmtree(folder)
	logger.info("压缩完成：%s", out)
	return out


def _zip_path(
	path: str | Path | list[str | Path],
	*,
	password: str = "",
	zippath: str | Path | None = None,
	comment: str = "",
	delete: bool = False,
	each: bool = False,
) -> Path | list[Path] | str:
	"""
	压缩传入的文件或文件夹；使用 pyzipper 可用 AES256 加密。

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
	if isinstance(path, (list, tuple)) or Path(path).is_file():
		if each:
			return _zip_each_file(path, password=password, zip_dir=zippath, comment=comment, delete=delete)
		return _zip_files(path, password=password, zippath=zippath, comment=comment, delete=delete)

	p = Path(path)
	if p.is_dir():
		return _zip_folder(p, password=password, zippath=zippath, comment=comment, delete=delete)
	
	logger.warning("无法压缩，不存在：%s", path)
	return ""


def _unzip_file(
	zippath: str | Path,
	*,
	password: str = "",
	dest: str | Path | None = None,
	nested: bool = True,
	delete: bool = False,
) -> Path:
	"""
	解压 zip 文件；使用 pyzipper 可解压 AES256 与 ZipCrypto 加密包（AES 更快）。

	智能解压：
		- zip 内无统一文件夹、或有多个顶层项时，新建以 zip 文件名为名的文件夹再解压；
		- zip 内只有 1 个与 zip 同名的文件夹时，直接解压到目标目录。

	建议用支持 Unicode 文件名的工具压缩，避免解压后文件名乱码。

	Args:
		zippath: 待解压的 zip 文件路径。
		password: 解压密码。
		dest: 指定解压目录；为空则在 zip 同目录智能解压。
		nested: 为 True 时，递归解压 zip 内部的 zip，并删除内部 zip。
		delete: 为 True 时，解压后删除该 zip 源文件。

	Returns:
		解压得到的目录（或主内容路径）。
	"""
	zippath = Path(zippath)
	if not zf.is_zipfile(zippath):
		raise ValueError(f"不是 zip：{zippath}")

	with zf.AESZipFile(zippath, "r") as z:
		if z.comment:
			logger.info("压缩文件注释：%s", z.comment.decode("utf-8", errors="replace"))

		names = z.namelist()
		if not names:
			return zippath.parent

		if len(names) >= 2:
			zip_dir0 = Path(_common_path(names)).name
		else:
			zip_dir0 = Path(names[0]).name

		zip_name = zippath.stem.strip()
		if dest:
			dest_p = Path(dest)
			dest_p.mkdir(parents=True, exist_ok=True)
			if zip_dir0 == zip_name:
				extract_to = dest_p
				result = dest_p / zip_dir0
			else:
				extract_to = result = dest_p / zip_name
		else:
			result = zippath.with_name(zippath.stem)
			extract_to = zippath.parent if zip_dir0 == zip_name else result

		extract_to.mkdir(parents=True, exist_ok=True)
		pwd = password.encode("utf-8") if password else None
		try:
			for name in names:
				z.extract(name, extract_to, pwd)
				inner = extract_to / name
				if nested and name.lower().endswith(".zip") and inner.is_file():
					logger.info("解压内部 zip：%s", inner)
					_unzip_file(inner, password=password, nested=nested, delete=True)
			logger.info("解压完成：%s", zippath)
		except RuntimeError:
			logger.error("密码【%s】错误，解压失败：%s", password, zippath)
			raise

	if delete:
		zippath.unlink(missing_ok=True)
	return result


def _unzip_folder(
	folder: str | Path,
	*,
	password: str = "",
	dest: str | Path | None = None,
	nested: bool = False,
	delete: bool = False,
) -> Path | str:
	"""
	解压目录下所有 zip 文件。

	Args:
		folder: 含有 zip 文件的文件夹路径。
		password: 解压密码。
		dest: 指定解压目录；为空则在各 zip 旁智能解压。
		nested: 为 True 时，递归解压 zip 内部的 zip。
		delete: 为 True 时，解压后删除 zip 源文件；若同时 nested=True，内部 zip 也会被删。

	Returns:
		最后一次解压得到的路径；目录下无 zip 时返回空字符串。
	"""
	folder = Path(folder)
	zips = sorted(folder.rglob("*.zip"))
	if not zips:
		logger.info("%s 目录下无 zip 文件", folder)
		return ""

	last: Path | str = ""
	for zp in zips:
		logger.info("正在解压：%s", zp)
		last = _unzip_file(zp, password=password, dest=dest, nested=nested, delete=delete)
	return last


def _unzip_path(
	path: str | Path,
	*,
	password: str = "",
	dest: str | Path | None = None,
	nested: bool = False,
	delete: bool = False,
) -> Path | str:
	"""
	智能解压：传入 zip 则解压该文件，传入文件夹则解压其下所有 zip。

	Args:
		path: 待解压的 zip 文件，或含有 zip 的文件夹路径。
		password: 解压密码。
		dest: 指定解压目录。
		nested: 为 True 时，递归解压内部 zip。
		delete: 为 True 时，解压后删除 zip 源文件。

	Returns:
		解压得到的路径；无法处理时返回空字符串。
	"""
	path = Path(path)
	if zf.is_zipfile(path):
		return _unzip_file(path, password=password, dest=dest, nested=nested, delete=delete)
	if path.is_dir():
		return _unzip_folder(path, password=password, dest=dest, nested=nested, delete=delete)
	logger.warning("%s 非 zip 文件，亦非含有 zip 的目录", path)
	return ""


# ----- 异步 API：业务代码统一使用以下函数 -----

async def zip_files(
	paths: str | Path | list[str | Path],
	*,
	password: str = "",
	zippath: str | Path | None = None,
	comment: str = "",
	delete: bool = False,
) -> Path:
	"""异步压缩多个文件成单个 zip。"""
	return await asyncio.to_thread(
		_zip_files,
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
	"""异步把每个文件分别压缩为独立的「文件名.zip」。"""
	return await asyncio.to_thread(
		_zip_each_file,
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
	"""异步压缩文件夹及其子文件。"""
	return await asyncio.to_thread(
		_zip_folder,
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
	"""异步压缩传入的文件或文件夹。"""
	return await asyncio.to_thread(
		_zip_path,
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
	"""异步解压单个 zip。"""
	return await asyncio.to_thread(
		_unzip_file,
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
	"""异步解压目录下所有 zip；多个 zip 在线程池中有限并发。"""
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
	"""异步智能解压：zip 文件则解压它，目录则解压其下所有 zip。"""
	path_p = Path(path)
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
