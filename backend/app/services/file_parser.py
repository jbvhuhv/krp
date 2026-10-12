import re
import zipfile
from xml.etree import ElementTree as ET

import pypdf


def parse_text(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def parse_pdf(file_path: str) -> str:
    reader = pypdf.PdfReader(file_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)


_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def parse_docx(file_path: str) -> str:
    """解析 .docx（OOXML 本质是 zip），零依赖提取 word/document.xml 文本。"""
    try:
        with zipfile.ZipFile(file_path) as zf:
            xml_bytes = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("无效的 Word 文档（.docx）") from exc
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError("无法解析 Word 文档内容") from exc

    lines = []
    for para in root.iter(f"{_WORD_NS}p"):
        text = "".join(t.text or "" for t in para.iter(f"{_WORD_NS}t"))
        if text.strip():
            lines.append(text.strip())
    return "\n".join(lines)


def parse_doc(file_path: str) -> str:
    """旧版 .doc 为 OLE 二进制，尽力提取可读文本片段（效果有限）。"""
    with open(file_path, "rb") as f:
        data = f.read()
    text = data.decode("utf-16-le", errors="ignore")
    chunks = re.findall(r"[\u4e00-\u9fff\u0020-\u007e]{4,}", text)
    return "\n".join(c.strip() for c in chunks if c.strip())


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
