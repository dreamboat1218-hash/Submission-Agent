"""模块一：文件预处理。

负责多层嵌套压缩包递归解压、文件类型识别、格式转换（PDF/DOCX/表格/图片），
最终输出统一目录、Markdown 文档和文件清单。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_session_factory
from ..models import Task

logger = logging.getLogger(__name__)

ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".tar.gz", ".tar.bz2"}
DOCUMENT_EXTS = {".pdf", ".docx", ".doc", ".txt", ".md", ".markdown", ".xlsx", ".xls", ".csv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
SUPPORTED_EXTS = DOCUMENT_EXTS | IMAGE_EXTS

ProgressCallback = Callable[[float, str], None]


def _md_target_name(rel: Path) -> str:
    """生成不会超过文件系统上限的 Markdown 文件名（可读前缀 + 短哈希防重名）。"""
    digest = hashlib.sha1(rel.as_posix().encode("utf-8")).hexdigest()[:10]
    raw = (rel.stem or "document").strip().encode("utf-8")
    if len(raw) > 80:
        stem = raw[:80].decode("utf-8", errors="ignore").strip()
    else:
        stem = raw.decode("utf-8", errors="ignore").strip()
    return f"{stem or 'document'}__{digest}.md"


def run(task_id: str, progress_cb: ProgressCallback | None = None) -> dict:
    settings = get_settings()
    factory = get_session_factory()
    with factory() as db:
        task = db.get(Task, task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        source_path = Path(task.original_file_path)
        work_dir = Path(task.work_dir)

    work_dir.mkdir(parents=True, exist_ok=True)
    input_dir = work_dir / "input"
    md_dir = work_dir / "markdown"
    input_dir.mkdir(exist_ok=True)
    md_dir.mkdir(exist_ok=True)

    warnings: list[str] = []
    conflicts: list[str] = []

    if source_path.suffix.lower() in ARCHIVE_EXTS or _is_nested_archive(source_path):
        if progress_cb:
            progress_cb(6, "检测到压缩包，开始递归解压")
        extract_archive(source_path, input_dir, depth=0, warnings=warnings, conflicts=conflicts)
    else:
        target = input_dir / source_path.name
        if source_path.resolve() != target.resolve():
            shutil.copy2(source_path, target)

    files = _collect_files(input_dir, max_files=settings.max_files_per_task)
    if not files:
        reasons = warnings[:10] or ["未找到 PDF/DOCX/文本/表格/图片等可处理文件"]
        raise RuntimeError("压缩包中未找到可处理的文件：" + "；".join(reasons))

    manifest_entries: list[dict] = []
    combined_parts: list[str] = []
    total = len(files)

    for index, file_path in enumerate(files, start=1):
        rel = file_path.relative_to(input_dir)
        entry_warnings: list[str] = []
        try:
            md_path, page_count = convert_to_markdown(file_path, md_dir / _md_target_name(rel))
            status = "converted"
        except Exception as exc:
            logger.exception("convert failed: %s", file_path)
            md_path = ""
            page_count = 0
            status = "failed"
            entry_warnings.append(f"{type(exc).__name__}: {exc}")

        entry = {
            "path": str(file_path),
            "rel_path": rel.as_posix(),
            "type": _classify(file_path),
            "size": file_path.stat().st_size,
            "md_path": md_path,
            "page_count": page_count,
            "status": status,
            "warnings": entry_warnings,
        }
        manifest_entries.append(entry)
        warnings.extend(entry_warnings)

        if md_path and Path(md_path).exists():
            combined_parts.append(f"# 文档：{rel.as_posix()}\n\n{Path(md_path).read_text(encoding='utf-8')}")
        if progress_cb:
            progress_cb(6 + 12 * index / total, f"已转换 {index}/{total} 个文件")

    manifest = {
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(manifest_entries),
        "files": manifest_entries,
        "warnings": warnings[:100],
        "conflicts": conflicts[:100],
    }
    (work_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (work_dir / "combined.md").write_text("\n\n".join(combined_parts), encoding="utf-8")
    (work_dir / "metadata.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "original_file_name": task.original_file_name,
                "file_count": len(manifest_entries),
                "warnings": warnings[:100],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if progress_cb:
        progress_cb(18, f"预处理完成，共 {len(manifest_entries)} 个文件")
    return manifest


def _classify(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".pdf"}:
        return "pdf"
    if suffix in {".docx", ".doc"}:
        return "word"
    if suffix in {".txt", ".md", ".markdown"}:
        return "text"
    if suffix in {".xlsx", ".xls", ".csv"}:
        return "spreadsheet"
    if suffix in IMAGE_EXTS:
        return "image"
    return "other"


def _is_nested_archive(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".tar.gz") or name.endswith(".tgz") or name.endswith(".tar.bz2")


def _collect_files(root: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            if filename.startswith("."):
                continue
            path = Path(dirpath) / filename
            if _classify(path) != "other" and path.suffix.lower() not in ARCHIVE_EXTS:
                files.append(path)
            if len(files) >= max_files:
                return files
    return files


def _decode_zip_name(name: str) -> str:
    if not any(ord(ch) > 127 for ch in name):
        return name
    try:
        fixed = name.encode("cp437").decode("gbk", errors="replace")
        return fixed if "\ufffd" not in fixed else name
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


MAX_PATH_BYTES = 900
MAX_COMPONENT_BYTES = 180


def _shorten_name(name: str, budget: int) -> str:
    """按 UTF-8 字节预算截断路径段，保留可读前缀 + 短哈希避免重名。"""
    raw = name.encode("utf-8")
    if len(raw) <= budget:
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    digest = hashlib.sha1(raw).hexdigest()[:8]
    suffix = f"_{digest}" + (f".{ext}" if ext else "")
    keep = max(budget - len(suffix.encode("utf-8")), 16)
    prefix = stem.encode("utf-8")[:keep].decode("utf-8", errors="ignore").rstrip()
    return f"{prefix or 'file'}{suffix}"


def _safe_target(dest: Path, name: str) -> Path:
    dest_root = dest.resolve()
    parts = [part for part in PurePosixPath(name.replace("\\", "/")).parts if part not in ("", ".")]
    if not parts:
        return dest_root
    parts = [_shorten_name(part, MAX_COMPONENT_BYTES) for part in parts]
    candidate = dest_root.joinpath(*parts)
    if len(str(candidate).encode("utf-8")) > MAX_PATH_BYTES:
        parts = [_shorten_name(part, 40) for part in parts[:-1]] + [_shorten_name(parts[-1], 90)]
        candidate = dest_root.joinpath(*parts)
    target = candidate.resolve()
    if target != dest_root and not target.is_relative_to(dest_root):
        raise RuntimeError(f"path traversal detected: {name}")
    return target


def extract_archive(
    archive_path: Path,
    dest: Path,
    depth: int = 0,
    max_depth: int | None = None,
    warnings: list[str] | None = None,
    conflicts: list[str] | None = None,
    passwords: tuple[str, ...] = ("", "123456", "1234", "123", "password"),
    _processed: set[Path] | None = None,
) -> None:
    warnings = warnings if warnings is not None else []
    conflicts = conflicts if conflicts is not None else []
    processed = _processed if _processed is not None else set()
    if archive_path in processed:
        return
    processed.add(archive_path)
    settings = get_settings()
    max_depth = max_depth or settings.max_extract_depth
    if depth >= max_depth:
        warnings.append(f"已达最大解压深度 {max_depth}，跳过 {archive_path.name}")
        return

    dest.mkdir(parents=True, exist_ok=True)
    suffix = archive_path.suffix.lower()
    try:
        if suffix == ".zip" or archive_path.name.lower().endswith(".zip"):
            _extract_zip(archive_path, dest, passwords, conflicts)
        elif suffix in {".tar", ".gz", ".tgz", ".bz2"} or _is_nested_archive(archive_path):
            _extract_tar(archive_path, dest)
        elif suffix == ".7z":
            _extract_7z(archive_path, dest, warnings)
        elif suffix == ".rar":
            _extract_rar(archive_path, dest, warnings)
        else:
            warnings.append(f"不支持的压缩格式：{archive_path.name}")
            return
    except Exception as exc:
        warnings.append(f"解压失败 {archive_path.name}: {type(exc).__name__}: {exc}")
        return

    for child in sorted(dest.rglob("*")):
        if not child.is_file():
            continue
        if child.name.startswith("._") or "__MACOSX" in child.parts:
            continue
        if child.suffix.lower() in ARCHIVE_EXTS or _is_nested_archive(child):
            extract_archive(
                child,
                dest,
                depth=depth + 1,
                max_depth=max_depth,
                warnings=warnings,
                conflicts=conflicts,
                passwords=passwords,
                _processed=processed,
            )


def _extract_zip(archive_path: Path, dest: Path, passwords: tuple[str, ...], conflicts: list[str]) -> None:
    with zipfile.ZipFile(archive_path) as zf:
        members = zf.infolist()
        if not members:
            return
        for info in members:
            name = _decode_zip_name(info.filename)
            if name.startswith("._") or "__MACOSX" in name:
                continue
            target = _safe_target(dest, name)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            data = _read_zip_member(zf, info, passwords)
            if target.exists():
                conflicts.append(f"文件冲突，覆盖：{name}")
            with open(target, "wb") as fp:
                fp.write(data)


def _read_zip_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, passwords: tuple[str, ...]) -> bytes:
    for password in passwords:
        try:
            if password:
                zf.setpassword(password.encode("utf-8"))
            else:
                zf.setpassword(None)
            return zf.read(info)
        except RuntimeError as exc:
            if "password" in str(exc).lower() or "encrypted" in str(exc).lower():
                continue
            raise
    raise RuntimeError("压缩包受密码保护，密码字典尝试失败")


def _extract_tar(archive_path: Path, dest: Path) -> None:
    with tarfile.open(archive_path) as tf:
        for member in tf.getmembers():
            target = _safe_target(dest, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tf.extractfile(member)
            if source is None:
                continue
            with open(target, "wb") as fp:
                shutil.copyfileobj(source, fp)


def _extract_7z(archive_path: Path, dest: Path, warnings: list[str]) -> None:
    try:
        import py7zr

        with py7zr.SevenZipFile(archive_path, mode="r") as zf:
            zf.extractall(path=dest)
    except ImportError:
        warnings.append("未安装 py7zr，无法解压 .7z 文件")
    except Exception as exc:
        warnings.append(f".7z 解压失败：{exc}")


def _extract_rar(archive_path: Path, dest: Path, warnings: list[str]) -> None:
    try:
        import rarfile

        with rarfile.RarFile(archive_path) as rf:
            rf.extractall(path=dest)
        return
    except ImportError:
        pass
    except Exception as exc:
        warnings.append(f"rarfile 解压失败，尝试 bsdtar：{exc}")

    if _extract_rar_with_bsdtar(archive_path, dest, warnings):
        return

    warnings.append("未安装 rarfile 且 bsdtar 不可用，无法解压 .rar 文件")


def _extract_rar_with_bsdtar(archive_path: Path, dest: Path, warnings: list[str]) -> bool:
    """使用 macOS/Linux 自带的 bsdtar 按原始字节读取 RAR 成员，避免 GBK 文件名乱码。"""
    import shutil
    import subprocess

    bsdtar = shutil.which("bsdtar") or shutil.which("tar")
    if not bsdtar:
        return False
    archive_bytes = os.fsencode(str(archive_path))
    try:
        listing = subprocess.run([os.fsencode(bsdtar), b"-tf", archive_bytes], capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, OSError) as exc:
        warnings.append(f"bsdtar 列表读取失败：{exc}")
        return False

    raw_lines = listing.splitlines()
    if not raw_lines:
        return False
    success = 0
    for raw_line in raw_lines:
        try:
            name = raw_line.decode("gbk", errors="replace")
        except UnicodeDecodeError:
            name = raw_line.decode("utf-8", errors="replace")
        name = name.replace("\\", "/")
        try:
            target = _safe_target(dest, name)
        except RuntimeError as exc:
            warnings.append(f"跳过非法路径 {name!r}: {exc}")
            continue
        if name.endswith("/") or raw_line.endswith(b"/"):
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            content = subprocess.run(
                [os.fsencode(bsdtar), b"-xOf", archive_bytes, raw_line],
                capture_output=True,
                check=True,
            ).stdout
            with open(target, "wb") as fp:
                fp.write(content)
            success += 1
        except (subprocess.CalledProcessError, OSError) as exc:
            warnings.append(f"提取失败 {name}: {exc}")
    return success > 0


def convert_to_markdown(source: Path, md_path: Path) -> tuple[str, int]:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    file_type = _classify(source)
    if file_type == "pdf":
        page_count = _convert_pdf(source, md_path)
    elif file_type == "word":
        try:
            page_count = _convert_docx(source, md_path)
        except Exception:
            page_count = _convert_doc_legacy(source, md_path)
    elif file_type == "text":
        page_count = 0
        _convert_text(source, md_path)
    elif file_type == "spreadsheet":
        page_count = 0
        _convert_spreadsheet(source, md_path)
    elif file_type == "image":
        page_count = 0
        _convert_image(source, md_path)
    else:
        raise RuntimeError(f"不支持的文件类型：{source.suffix}")
    return str(md_path), page_count


def _convert_pdf(source: Path, md_path: Path) -> int:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("未安装 PyMuPDF，无法解析 PDF") from exc

    parts: list[str] = [f"# {source.name}\n"]
    page_count = 0
    with fitz.open(source) as doc:
        page_count = doc.page_count
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            parts.append(f"\n<!-- page: {index} -->\n\n{text}\n")
    md_path.write_text("\n".join(parts), encoding="utf-8")
    return page_count


def _convert_docx(source: Path, md_path: Path) -> int:
    try:
        import docx
        from docx.document import Document as DocxDocument
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise RuntimeError("未安装 python-docx，无法解析 DOCX") from exc

    document = docx.Document(source)
    parts: list[str] = [f"# {source.name}\n"]
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag
        if tag.endswith("}p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if text:
                style = paragraph.style.name if paragraph.style else ""
                if "Heading" in style or "标题" in style:
                    parts.append(f"\n## {text}\n")
                else:
                    parts.append(text)
        elif tag.endswith("}tbl"):
            table = Table(child, document)
            parts.append(_table_to_markdown(table))
    md_path.write_text("\n".join(parts), encoding="utf-8")
    return 0


def _convert_doc_legacy(source: Path, md_path: Path) -> int:
    """旧版二进制 Word（.doc / 伪装成 .docx）通过 textutil 或 antiword 转换。

    macOS 的 textutil 在超长中文路径下会误报"文件不存在"且仍返回 0，
    因此先复制到短临时路径再转换，并校验输出文件是否真的生成。
    """
    import shutil
    import subprocess
    import tempfile

    textutil = shutil.which("textutil")
    antiword = shutil.which("antiword")
    if not textutil and not antiword:
        raise RuntimeError("未找到 textutil/antiword，无法解析旧版 Word 文档")

    with tempfile.TemporaryDirectory(prefix="bid_doc_") as tmp:
        tmp_dir = Path(tmp)
        safe_source = tmp_dir / f"source{source.suffix.lower() or '.doc'}"
        shutil.copy2(source, safe_source)

        if textutil:
            txt_path = tmp_dir / "output.txt"
            result = subprocess.run(
                [textutil, "-convert", "txt", str(safe_source), "-output", str(txt_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0 or not txt_path.exists():
                detail = (result.stderr or result.stdout or "").strip()[-300:] or "未生成输出文件"
                raise RuntimeError(f"textutil 转换失败：{detail}")
            data = txt_path.read_bytes()
            for encoding in ("utf-8-sig", "utf-16", "gbk"):
                try:
                    text = data.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                text = data.decode("utf-8", errors="replace")
            md_path.write_text(f"# {source.name}\n\n{text}", encoding="utf-8")
            return 0

        result = subprocess.run([antiword, str(safe_source)], capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"antiword 转换失败：{result.stderr[-300:]}")
        md_path.write_text(f"# {source.name}\n\n{result.stdout}", encoding="utf-8")
        return 0


def _table_to_markdown(table) -> str:
    rows: list[list[str]] = []
    for row in table.rows:
        rows.append([cell.text.replace("\n", " ").strip() for cell in row.cells])
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    lines = ["| " + " | ".join(r + [""] * (width - len(r))) + " |" for r in rows]
    header = "|" + "---|" * width
    return "\n".join([lines[0], header, *lines[1:]])


def _convert_text(source: Path, md_path: Path) -> None:
    data = source.read_bytes()
    for encoding in ("utf-8-sig", "gbk", "utf-16"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    md_path.write_text(f"# {source.name}\n\n{text}", encoding="utf-8")


def _convert_spreadsheet(source: Path, md_path: Path) -> None:
    suffix = source.suffix.lower()
    if suffix == ".csv":
        _convert_text(source, md_path)
        return
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("未安装 openpyxl，无法解析表格") from exc

    wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
    parts = [f"# {source.name}\n"]
    for sheet in wb.worksheets:
        parts.append(f"\n## 工作表：{sheet.title}\n")
        rows = [["" if cell.value is None else str(cell.value).replace("\n", " ") for cell in row] for row in sheet.iter_rows()]
        if rows:
            width = max(len(r) for r in rows)
            normalized = [r + [""] * (width - len(r)) for r in rows]
            parts.append("| " + " | ".join(normalized[0]) + " |")
            parts.append("|" + "---|" * width)
            parts.extend("| " + " | ".join(r) + " |" for r in normalized[1:])
    md_path.write_text("\n".join(parts), encoding="utf-8")


def _convert_image(source: Path, md_path: Path) -> None:
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        md_path.write_text(
            f"# {source.name}\n\n<!-- OCR 未启用，未安装 paddleocr，无法转换图片内容 -->\n",
            encoding="utf-8",
        )
        return

    ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    result = ocr.ocr(str(source), cls=True)
    lines: list[str] = []
    for page in result or []:
        for item in page or []:
            if item and len(item) >= 2 and item[1]:
                lines.append(str(item[1][0]))
    md_path.write_text(f"# {source.name}\n\n" + "\n".join(lines), encoding="utf-8")
