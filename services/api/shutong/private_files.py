"""私有原件校验、完整性检查和本地文本解析；不负责发布或判分。"""
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4
import warnings
import xml.etree.ElementTree as ET
import zipfile

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from .home import (
    assert_no_cross_environment_path,
    default_attachments_dir,
    default_school_exams_dir,
    resolve_school_exam_subpath,
    sanitize_archive_segment,
)

DEFAULT_PRIVATE_DIR = default_attachments_dir()
MAX_BYTES = 35 * 1024 * 1024
MAX_PAGES = 40
MAX_PIXELS = 20_000_000
MAX_TEXT_BYTES = 200_000
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MEDIA_TYPES = ("application/pdf", "image/png", "image/jpeg", "audio/mpeg", "audio/mp4", DOCX_MEDIA_TYPE)

PDF_RENDER_DPI = 150
PDF_RENDER_TIMEOUT = 120
PDF_OCR_PAGE_TIMEOUT = 60
OCR_PAGE_MARKER = "\n\n—— 第 {page} 页（OCR 草稿）——\n"

# 扫描件常见的软件水印、公众号页眉及阅卷扫描仪条码串模式
_OCR_NOISE_RE = re.compile(
    r"\{#\{[A-Za-z0-9+/=]+\}#\}|"
    r"扫描全能王\s*创建|"
    r"帮\s*考\s*京\s*[：:]\s*号\s*众\s*公|"
    r"公\s*众\s*号\s*[：:]\s*京\s*考\s*帮"
)


def private_root():
    raw = os.getenv("SHUTONG_PRIVATE_DIR")
    target = Path(raw) if raw else default_attachments_dir()
    return assert_no_cross_environment_path(target)


def school_exams_root() -> Path:
    return assert_no_cross_environment_path(default_school_exams_dir())


def ensure_school_exam_archive_dirs(archive_dir: str) -> Path:
    """在 data/school-exams/ 下幂等创建档案目录及 exam-paper / answer-sheet 子目录（0700）。"""
    root = school_exams_root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    archive_path = resolve_school_exam_subpath(archive_dir)
    for target in (archive_path, archive_path / "exam-paper", archive_path / "answer-sheet"):
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(target, 0o700)
        except OSError:
            pass
    return archive_path


def school_exam_file_path(relative_path: str) -> Path:
    return resolve_school_exam_subpath(relative_path)


def attachment_file_path(attachment) -> Path:
    rel = getattr(attachment, "relative_path", None)
    if isinstance(rel, str) and rel.strip():
        return school_exam_file_path(rel.strip())
    return blob_path(attachment.storage_key)


def blob_path(key):
    if not re.fullmatch(r"[0-9a-f]{32}", key):
        raise HTTPException(409, detail="INVALID_STORAGE_KEY")
    return private_root() / key


def run_tool(arguments, timeout=20, **kwargs):
    try:
        result = subprocess.run(arguments, capture_output=True, timeout=timeout, **kwargs)
    except FileNotFoundError:
        raise HTTPException(503, detail="LOCAL_PARSER_NOT_INSTALLED")
    except subprocess.TimeoutExpired:
        raise HTTPException(422, detail="DOCUMENT_PROCESSING_TIMEOUT")
    if result.returncode:
        raise HTTPException(422, detail="DOCUMENT_PROCESSING_FAILED")
    return result


def validate_file(data, media_type):
    if media_type not in MEDIA_TYPES:
        raise HTTPException(415, detail="UNSUPPORTED_FILE_TYPE")
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413 if data else 422, detail="INVALID_FILE_SIZE")
    if media_type == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise HTTPException(422, detail="FILE_TYPE_MISMATCH")
        with TemporaryDirectory(prefix="pageboy-pdf-") as directory:
            path = Path(directory) / "input.pdf"
            path.write_bytes(data)
            result = run_tool(["pdfinfo", str(path)], env={**os.environ, "LC_ALL": "C"})
        info = result.stdout.decode("utf-8", errors="replace")
        pages = re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)
        if not pages or not 1 <= int(pages[1]) <= MAX_PAGES or re.search(r"^Encrypted:\s+yes", info, re.MULTILINE):
            raise HTTPException(422, detail="UNSUPPORTED_PDF")
    elif media_type == DOCX_MEDIA_TYPE:
        if not data.startswith(b"PK\x03\x04"):
            raise HTTPException(422, detail="FILE_TYPE_MISMATCH")
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("missing word/document.xml")
                ET.fromstring(archive.read("word/document.xml"))
        except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError):
            raise HTTPException(422, detail="INVALID_DOCX")
    elif media_type in ("audio/mpeg", "audio/mp4"):
        # 仅魔数校验（mp3：ID3 或 0xFF Ex/Fx 帧头；mp4/m4a：偏移 4 处 ftyp），不引入时长/码率解析。
        if media_type == "audio/mpeg":
            valid = data.startswith(b"ID3") or (len(data) > 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)
        else:
            valid = len(data) > 12 and data[4:8] == b"ftyp"
        if not valid:
            raise HTTPException(422, detail="FILE_TYPE_MISMATCH")
    else:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    expected = "PNG" if media_type == "image/png" else "JPEG"
                    if image.format != expected or image.width * image.height > MAX_PIXELS:
                        raise ValueError("invalid image")
                    image.load()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(422, detail="INVALID_IMAGE")


def _safe_school_exam_filename(filename: str) -> str:
    raw = Path((filename or "").strip()).name
    if not raw:
        return "document.bin"
    if "." in raw:
        stem, ext = raw.rsplit(".", 1)
        safe_stem = sanitize_archive_segment(stem, fallback="file", max_len=96)
        safe_ext = re.sub(r"[^A-Za-z0-9]", "", ext)[:12]
        return f"{safe_stem}.{safe_ext}" if safe_ext else safe_stem
    return sanitize_archive_segment(raw, fallback="file", max_len=96)


def write_school_exam_file(archive_dir: str, subdir: str, filename: str, data: bytes) -> tuple[str, str]:
    """将校考文件写入 data/school-exams/<archive_dir>/<subdir>/（0600 权限），返回 (storage_key, relative_path)。"""
    if subdir not in {"exam-paper", "answer-sheet"}:
        raise ValueError(f"unsupported school exam subdir: {subdir!r}")
    ensure_school_exam_archive_dirs(archive_dir)
    key = uuid4().hex
    safe_name = _safe_school_exam_filename(filename)
    rel = f"{archive_dir}/{subdir}/{safe_name}"
    target = school_exam_file_path(rel)
    if target.exists():
        if "." in safe_name:
            stem, ext = safe_name.rsplit(".", 1)
            safe_name = f"{stem}_{key[:6]}.{ext}"
        else:
            safe_name = f"{safe_name}_{key[:6]}"
        rel = f"{archive_dir}/{subdir}/{safe_name}"
        target = school_exam_file_path(rel)
    created = False
    try:
        with open(target, "xb", opener=lambda path, flags: os.open(path, flags, 0o600)) as file:
            created = True
            file.write(data)
    except OSError:
        if created:
            target.unlink(missing_ok=True)
        raise
    return key, rel


def write_school_exam_scoped_blob(subdir: str, filename: str, data: bytes) -> tuple[str, str]:
    """将报告或扫描待归档原卷写入 data/school-exams/<subdir>/，避免混入 data/attachments/。"""
    if subdir not in {"reports", "papers"}:
        raise ValueError(f"unsupported scoped subdir: {subdir!r}")
    root = school_exams_root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    target_dir = root / subdir
    target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = uuid4().hex
    safe_name = _safe_school_exam_filename(filename)
    rel = f"{subdir}/{key[:8]}_{safe_name}"
    target = school_exam_file_path(rel)
    created = False
    try:
        with open(target, "xb", opener=lambda path, flags: os.open(path, flags, 0o600)) as file:
            created = True
            file.write(data)
    except OSError:
        if created:
            target.unlink(missing_ok=True)
        raise
    return key, rel


def unlink_attachment_blob(attachment) -> None:
    attachment_file_path(attachment).unlink(missing_ok=True)


def cleanup_empty_school_exam_archive_dir(archive_dir: str | None) -> None:
    if not archive_dir or not archive_dir.strip():
        return
    try:
        archive_path = resolve_school_exam_subpath(archive_dir.strip())
    except Exception:
        return
    if not archive_path.is_dir():
        return
    for sub in ("exam-paper", "answer-sheet"):
        sub_path = archive_path / sub
        if sub_path.is_dir():
            try:
                if not any(sub_path.iterdir()):
                    sub_path.rmdir()
            except OSError:
                pass
    try:
        if not any(archive_path.iterdir()):
            archive_path.rmdir()
    except OSError:
        pass


def remove_school_exam_archive_dir(archive_dir: str | None) -> None:
    """当没有任何校考记录再引用该 archive_dir 时，彻底清理 data/school-exams/<archive_dir>/ 及其内部残留文件。"""
    if not archive_dir or not archive_dir.strip():
        return
    try:
        archive_path = resolve_school_exam_subpath(archive_dir.strip())
    except Exception:
        return
    if archive_path.is_dir() and not archive_path.is_symlink():
        shutil.rmtree(archive_path, ignore_errors=True)


def write_blob(data):
    root = private_root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = uuid4().hex
    path = blob_path(key)
    created = False
    try:
        with open(path, "xb", opener=lambda path, flags: os.open(path, flags, 0o600)) as file:
            created = True
            file.write(data)
    except OSError:
        if created:
            path.unlink(missing_ok=True)
        raise
    return key


_ORIGINAL_WRITE_BLOB = write_blob


def load_blob(attachment):
    path = attachment_file_path(attachment)
    if path.is_symlink():
        raise HTTPException(409, detail="INVALID_STORAGE_KEY")
    try:
        with path.open("rb") as file:
            data = file.read(MAX_BYTES + 1)
    except FileNotFoundError:
        raise HTTPException(409, detail="ATTACHMENT_FILE_MISSING")
    if len(data) != attachment.byte_size or sha256(data).hexdigest() != attachment.sha256:
        raise HTTPException(409, detail="ATTACHMENT_HASH_MISMATCH")
    return data


def pdf_needs_ocr(text):
    """纯决策：剔除已知扫描器水印/条码及空白标点后无有效正文，或多页试卷仅含极短页眉时，视为无有效文本层并触发 OCR 兜底。
    含真实文本层的 PDF 一律不降级 OCR。"""
    cleaned = _OCR_NOISE_RE.sub("", text)
    meaningful = re.sub(r"[\s·•.．_—\-]+", "", cleaned)
    if not meaningful:
        return True
    if text.count("\x0c") >= 4 and len(meaningful) < 30:
        return True
    return False


def ocr_pdf(path, directory):
    """无文本层 PDF 的兜底：pdftoppm 逐页渲染为 PNG，再逐页 tesseract chi_sim+eng。
    返回按页序拼接、带页码标记的草稿文本（OCR 结果，非结构化，须人工核对）。"""
    root = Path(directory)
    run_tool(["pdftoppm", "-r", str(PDF_RENDER_DPI), "-png", "-l", str(MAX_PAGES), str(path), str(root / "page")],
             timeout=PDF_RENDER_TIMEOUT)
    images = sorted(root.glob("page-*.png"), key=lambda item: int(item.stem.rsplit("-", 1)[1]))
    pages = []
    for index, image in enumerate(images, 1):
        target = root / f"ocr-{index}"
        run_tool(["tesseract", str(image), str(target), "-l", "chi_sim+eng"], timeout=PDF_OCR_PAGE_TIMEOUT)
        page_text = target.with_suffix(".txt").read_text(encoding="utf-8", errors="replace").strip()
        if page_text:
            pages.append(OCR_PAGE_MARKER.format(page=index) + page_text)
    return "".join(pages).strip()


def _decode_mtef_ole(raw: bytes) -> str:
    """从 Word MathType OLE 二进制对象中提取可读公式文本（最佳努力提取，仍须人工核对）。"""
    pos = raw.find("Equation Native".encode("utf-16le"))
    if pos == -1:
        return ""
    size = int.from_bytes(raw[pos + 0x78 : pos + 0x7C], "little")
    idx = 0
    while True:
        p = raw.find(b"\x1c\x00\x00\x00\x02\x00", idx)
        if p == -1:
            break
        if raw[p + 28 : p + 30] == b"\x05\x01":
            mtef = raw[p + 28 : p + size]
            out = []
            i = 12
            while i < len(mtef) - 2:
                b = mtef[i]
                if 0x81 <= b <= 0x97:
                    ch = int.from_bytes(mtef[i + 1 : i + 3], "little")
                    if 0x20 <= ch <= 0x2FFF and ch not in (0x2F01, 0x2F44, 0x0501):
                        out.append(chr(ch))
                        i += 3
                        continue
                i += 1
            return "".join(out)[1:] if len(out) > 1 else "".join(out)
        idx = p + 1
    return ""


def extract_docx_text(data: bytes) -> str:
    """从 .docx 压缩包中提取段落文本与内嵌公式文本。"""
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            rel_map: dict[str, str] = {}
            if "word/_rels/document.xml.rels" in archive.namelist():
                rels = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
                rel_map = {r.attrib.get("Id", ""): r.attrib.get("Target", "") for r in rels}
            doc = ET.fromstring(archive.read("word/document.xml"))
            names = set(archive.namelist())
            paragraphs: list[str] = []
            for para in doc.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                parts: list[str] = []
                for elem in para.iter():
                    if elem.tag.endswith("}t") and elem.text:
                        parts.append(elem.text)
                    elif elem.tag.endswith("}OLEObject"):
                        rid = elem.attrib.get(
                            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", ""
                        )
                        target = rel_map.get(rid, "")
                        if target and f"word/{target}" in names:
                            eq = _decode_mtef_ole(archive.read(f"word/{target}"))
                            if eq:
                                parts.append(f"${eq}$")
                line = "".join(parts).strip()
                if line:
                    paragraphs.append(line)
            return "\n".join(paragraphs)
    except (zipfile.BadZipFile, ET.ParseError, KeyError):
        raise HTTPException(422, detail="DOCUMENT_PROCESSING_FAILED")


def parse_text(data, media_type):
    if media_type == DOCX_MEDIA_TYPE:
        text = extract_docx_text(data).strip()
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise HTTPException(422, detail="EXTRACTED_TEXT_TOO_LARGE")
        return text, "python-docx-xml"
    with TemporaryDirectory(prefix="pageboy-parse-") as directory:
        path = Path(directory) / ("input.pdf" if media_type == "application/pdf" else "input.image")
        path.write_bytes(data)
        output = Path(directory) / "output.txt"
        if media_type == "application/pdf":
            run_tool(["pdftotext", "-layout", "-enc", "UTF-8", str(path), str(output)])
            pdftotext_version = run_tool(["pdftotext", "-v"]).stderr.decode().splitlines()[0]
            text = output.read_text(encoding="utf-8", errors="replace")
            if pdf_needs_ocr(text):
                text = ocr_pdf(path, directory)
                tesseract_version = run_tool(["tesseract", "--version"]).stdout.decode().splitlines()[0]
                version = f"{pdftotext_version} + {tesseract_version} (ocr fallback)"
            else:
                version = pdftotext_version
        else:
            run_tool(["tesseract", str(path), str(output.with_suffix("")), "-l", "chi_sim+eng"])
            text = output.read_text(encoding="utf-8", errors="replace")
            version = run_tool(["tesseract", "--version"]).stdout.decode().splitlines()[0]
        text = text.strip()
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise HTTPException(422, detail="EXTRACTED_TEXT_TOO_LARGE")
        return text, version
