"""私有原件校验、完整性检查和本地文本解析；不负责发布或判分。"""
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4
import warnings

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

DEFAULT_PRIVATE_DIR = Path(__file__).resolve().parents[1] / "private-data" / "attachments"
MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 40
MAX_PIXELS = 20_000_000
MAX_TEXT_BYTES = 200_000
MEDIA_TYPES = ("application/pdf", "image/png", "image/jpeg", "audio/mpeg", "audio/mp4")

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
    return Path(os.getenv("SHUTONG_PRIVATE_DIR", str(DEFAULT_PRIVATE_DIR))).resolve()


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


def load_blob(attachment):
    try:
        with blob_path(attachment.storage_key).open("rb") as file:
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


def parse_text(data, media_type):
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
