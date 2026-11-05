"""把知识书架导出成 Word 思维导图（.docx）。

为什么单独成模块：排版细节（中文字体、缩进、树形连接符）与 HTTP 层无关，
单独放在服务层可以脱离接口直接测试；后续如果要做「单本书导出」也只调这里。
"""

from __future__ import annotations

import io
import re
from datetime import date

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from app.services.graph.constants import (
    NODE_TYPE_BOOK,
    NODE_TYPE_CATEGORY,
    NODE_TYPE_KNOWLEDGE,
)

# 中文文档统一用雅黑；不指定 eastAsia 时 Word 会用宋体回退，字号也会漂
FONT = "微软雅黑"

COLOR_TITLE = RGBColor(0x0F, 0x17, 0x2A)
COLOR_BOOK = RGBColor(0x1E, 0x3A, 0x5F)
COLOR_ACCENT = RGBColor(0x25, 0x63, 0xEB)
COLOR_BODY = RGBColor(0x33, 0x41, 0x55)
COLOR_MUTED = RGBColor(0x94, 0xA3, 0xB8)
COLOR_LINE = RGBColor(0xCB, 0xD5, 0xE1)

# 摘要截断长度：思维导图要一眼扫完，长段落会把层级结构埋掉
SUMMARY_LIMIT = 80

_CHILD_TYPES = (NODE_TYPE_CATEGORY, NODE_TYPE_KNOWLEDGE)


def _plain(text: str | None) -> str:
    """把 Markdown 摘要压成纯文本，避免 Word 里出现 * 和 # 之类的噪音。"""
    if not text:
        return ""
    s = re.sub(r"```.*?```", " ", str(text), flags=re.S)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"^\s{0,3}#{1,6}\s*", "", s, flags=re.M)
    s = re.sub(r"^\s{0,3}[>\-\*\+]\s+", "", s, flags=re.M)
    s = s.replace("**", "").replace("__", "")
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > SUMMARY_LIMIT:
        s = s[:SUMMARY_LIMIT].rstrip("，。、；：,.;:") + "…"
    return s


def _set_run_font(run, size: float, *, bold: bool = False, color: RGBColor | None = None):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    # python-docx 只写 w:ascii/w:hAnsi，中文必须补 eastAsia 才生效
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        # rFonts 在 rPr 里必须排第一，append 到末尾 Word 会判为非法
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:eastAsia"), FONT)


def _node_children(node_id: str, by_parent: dict[str, list[dict]], seen: set[str]) -> list[dict]:
    children = []
    for child in by_parent.get(node_id, []):
        cid = child.get("id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        children.append(
            {
                "name": (child.get("name") or "未命名").strip(),
                "summary": _plain(child.get("summary")),
                "node_type": child.get("node_type") or NODE_TYPE_KNOWLEDGE,
                "children": _node_children(cid, by_parent, seen),
            }
        )
    return children


def _count_nodes(children: list[dict]) -> int:
    return sum(1 + _count_nodes(c["children"]) for c in children)


def build_book_forest(nodes: list[dict], book_id: str | None = None) -> list[dict] | None:
    """把扁平节点整理成「书 → 分类 / 知识点」的树。

    book_id 为 None 时返回整个书架；指定但找不到时返回 None（接口据此返回 404），
    与「找到了但知识书是空的」区分开。
    """
    by_parent: dict[str, list[dict]] = {}
    books: list[dict] = []
    for node in nodes:
        node_type = node.get("node_type")
        if node_type == NODE_TYPE_BOOK:
            books.append(node)
        elif node_type in _CHILD_TYPES:
            parent_id = node.get("parent_id")
            if parent_id:
                by_parent.setdefault(parent_id, []).append(node)

    for children in by_parent.values():
        children.sort(key=lambda n: (n.get("sort_order") if n.get("sort_order") is not None else 999999, n.get("name") or ""))

    books.sort(key=lambda b: (b.get("name") or "").lower())

    forest = []
    for book in books:
        bid = book.get("id")
        if not bid:
            continue
        if book_id and bid != book_id:
            continue
        roots = _node_children(bid, by_parent, {bid})
        forest.append(
            {
                "id": bid,
                "name": (book.get("name") or "未命名知识书").strip(),
                "summary": _plain(book.get("summary")),
                "node_count": _count_nodes(roots),
                "children": roots,
            }
        )

    if book_id is not None and not forest:
        return None
    return forest


def _write_children(doc, children: list[dict], depth: int):
    """深度优先写出一棵子树：分类用 ◆，知识点用 ├/└ 树形连接符。"""
    total = len(children)
    for index, child in enumerate(children):
        last = index == total - 1
        indent = Cm(0.4 if depth == 1 else 0.4 + 0.75 * (depth - 1))
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.left_indent = indent
        paragraph.paragraph_format.space_before = Pt(7 if depth == 1 else 1.5)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.3
        # 分类标题别被拆到下一页末尾
        paragraph.paragraph_format.keep_with_next = bool(child["children"])

        if child["node_type"] == NODE_TYPE_CATEGORY:
            marker = paragraph.add_run("◆ ")
            _set_run_font(marker, 11, bold=True, color=COLOR_ACCENT)
            name_run = paragraph.add_run(child["name"])
            _set_run_font(name_run, 11.5, bold=True, color=COLOR_BOOK)
        else:
            connector = "└ " if last else "├ "
            mark = paragraph.add_run(connector)
            _set_run_font(mark, 10.5, color=COLOR_LINE)
            name_run = paragraph.add_run(child["name"])
            _set_run_font(name_run, 10.5, color=COLOR_BODY)

        if child["summary"]:
            note = doc.add_paragraph()
            note.paragraph_format.left_indent = indent + Cm(0.42)
            note.paragraph_format.space_before = Pt(0)
            note.paragraph_format.space_after = Pt(1)
            note.paragraph_format.line_spacing = 1.25
            note_run = note.add_run(child["summary"])
            _set_run_font(note_run, 9, color=COLOR_MUTED)

        if child["children"]:
            _write_children(doc, child["children"], depth + 1)


def render_docx(*, books: list[dict], owner_label: str, generated_at: date) -> bytes:
    """渲染成 .docx 字节流。books 为空也出一份文档，说明书架还没内容。"""
    doc = Document()

    # A4 + 适中页边距：默认模板是 Letter，中文打印会切边
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.4)
    section.right_margin = Cm(2.2)

    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(10.5)
    normal.paragraph_format.line_spacing = 1.3

    total_books = len(books)
    total_nodes = sum(b["node_count"] for b in books)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(2)
    title_run = title.add_run("我的知识思维导图")
    _set_run_font(title_run, 24, bold=True, color=COLOR_TITLE)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(4)
    meta = (
        f"{owner_label} · {total_books} 本书 · {total_nodes} 个知识点 · {generated_at:%Y-%m-%d}"
        if total_books
        else f"{owner_label} · {generated_at:%Y-%m-%d}"
    )
    sub_run = subtitle.add_run(meta)
    _set_run_font(sub_run, 9.5, color=COLOR_MUTED)

    if not books:
        hint = doc.add_paragraph()
        hint.paragraph_format.space_before = Pt(28)
        hint_run = hint.add_run("书架还是空的")
        _set_run_font(hint_run, 13, bold=True, color=COLOR_BOOK)
        tip = doc.add_paragraph()
        tip_run = tip.add_run("去「笔记」上传一篇 Markdown 笔记，系统会自动生成知识书，这里就能导出思维导图了。")
        _set_run_font(tip_run, 10, color=COLOR_MUTED)
    else:
        for book_index, book in enumerate(books):
            heading = doc.add_paragraph(style="Heading 1")
            heading.paragraph_format.space_before = Pt(6 if book_index == 0 else 22)
            heading.paragraph_format.space_after = Pt(0)
            heading.paragraph_format.line_spacing = 1.25
            heading.paragraph_format.keep_with_next = True

            bar = heading.add_run("▍ ")
            _set_run_font(bar, 16, bold=True, color=COLOR_ACCENT)
            name_run = heading.add_run(book["name"])
            _set_run_font(name_run, 16, bold=True, color=COLOR_BOOK)
            count_run = heading.add_run(f"　{book['node_count']} 个知识点")
            _set_run_font(count_run, 9.5, color=COLOR_MUTED)

            if not book["children"]:
                empty = doc.add_paragraph()
                empty.paragraph_format.left_indent = Cm(0.4)
                empty.paragraph_format.space_before = Pt(4)
                empty_run = empty.add_run("（这本知识书还没有知识点）")
                _set_run_font(empty_run, 10, color=COLOR_MUTED)
                continue

            _write_children(doc, book["children"], 1)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_run = footer.add_run("知识管理与反思平台 · 知识思维导图")
    _set_run_font(footer_run, 8.5, color=COLOR_MUTED)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
