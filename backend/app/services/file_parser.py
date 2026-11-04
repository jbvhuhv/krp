import re
import zipfile
from xml.etree import ElementTree as ET

import pypdf

# 解析阶段的安全上限：上传文件本身已限制 10MB，但压缩包/PDF 可以「小体积解出大内容」，
# 这里再加一道解压与结构上限，防止 zip 炸弹 / XML 实体扩展 / 超长 PDF 把内存和 CPU 打满。
MAX_TEXT_CHARS = 2_000_000
MAX_ZIP_ENTRIES = 2048
MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_XML_BYTES = 16 * 1024 * 1024
MAX_PDF_PAGES = 500


def parse_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read(MAX_TEXT_CHARS)


def parse_pdf(file_path: str) -> str:
    reader = pypdf.PdfReader(file_path)
    pages = []
    # 限制页数：恶意 PDF 可以用极多页把 CPU 占满
    for index, page in enumerate(reader.pages):
        if index >= MAX_PDF_PAGES:
            break
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)[:MAX_TEXT_CHARS]


_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def parse_docx(file_path: str) -> str:
    """解析 .docx（OOXML 本质是 zip），零依赖提取 word/document.xml 文本。"""
    try:
        with zipfile.ZipFile(file_path) as zf:
            infos = zf.infolist()
            # 限制条目数量与声明解压总量，挡住高压缩比 zip 炸弹
            if len(infos) > MAX_ZIP_ENTRIES:
                raise ValueError("Word 文档结构异常（条目过多）")
            declared = sum(getattr(i, "file_size", 0) or 0 for i in infos)
            if declared > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("Word 文档解压后体积过大")
            xml_bytes = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("无效的 Word 文档（.docx）") from exc

    if len(xml_bytes) > MAX_XML_BYTES:
        raise ValueError("Word 文档正文过大")
    # 拒绝 DOCTYPE：阻断外部实体与实体扩展（billion laughs）类攻击
    if b"<!DOCTYPE" in xml_bytes[:4096]:
        raise ValueError("Word 文档包含不允许的 DOCTYPE 声明")

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError("无法解析 Word 文档内容") from exc

    lines = []
    total = 0
    for para in root.iter(f"{_WORD_NS}p"):
        text = "".join(t.text or "" for t in para.iter(f"{_WORD_NS}t"))
        if text.strip():
            lines.append(text.strip())
            total += len(text)
            if total > MAX_TEXT_CHARS:
                break
    return "\n".join(lines)


def parse_doc(file_path: str) -> str:
    """旧版 .doc 为 OLE 二进制，尽力提取可读文本片段（效果有限）。"""
    with open(file_path, "rb") as f:
        data = f.read(MAX_TEXT_CHARS)
    text = data.decode("utf-16-le", errors="ignore")
    chunks = re.findall(r"[\u4e00-\u9fff\u0020-\u007e]{4,}", text)
    return "\n".join(c.strip() for c in chunks if c.strip())[:MAX_TEXT_CHARS]


def parse_file(file_path: str, fmt: str) -> str:
    fmt = fmt.lower().lstrip(".")
    if fmt in ("md", "markdown", "txt"):
        return parse_text(file_path)
    if fmt == "pdf":
        return parse_pdf(file_path)
    if fmt == "docx":
        return parse_docx(file_path)
    if fmt == "doc":
        return parse_doc(file_path)
    raise ValueError(f"不支持的文件格式: {fmt}")
