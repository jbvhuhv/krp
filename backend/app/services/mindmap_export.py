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
# 树形连线必须等宽：├ │ └ 的列宽固定，逐层嵌套才不会错位
MONO_FONT = "Consolas"
# 等宽字体下两个字符（"├ "）占的宽度，用来对齐摘要的悬挂缩进
INDENT_STEP_CM = 0.41

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


def _set_run_font(
    run,
    size: float,
    *,
    bold: bool = False,
    color: RGBColor | None = None,
    font: str = FONT,
):
    run.font.name = font
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
    # 等宽字体只用于连线字符，中文仍走雅黑
    rfonts.set(qn("w:eastAsia"), FONT if font == MONO_FONT else font)


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


def build_book_forest(
    nodes: list[dict], book_ids: list[str] | str | None = None
) -> list[dict] | None:
    """把扁平节点整理成「书 → 分类 / 知识点」的树。

    book_ids 为空时返回整个书架；指定了但一本都没匹配上返回 None（接口据此 404），
    与「选中了书但这本书没知识点」区分开。接受单个字符串是为了兼容旧调用。
    """
    if isinstance(book_ids, str):
        book_ids = [book_ids]
    wanted = {bid for bid in (book_ids or []) if bid}

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
        children.sort(
            key=lambda n: (
                n.get("sort_order") if n.get("sort_order") is not None else 999999,
                n.get("name") or "",
            )
        )

    books.sort(key=lambda b: (b.get("name") or "").lower())

    forest = []
    for book in books:
        bid = book.get("id")
        if not bid:
            continue
        if wanted and bid not in wanted:
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

    if wanted and not forest:
        return None
    return forest


def _write_children(doc, children: list[dict], depth: int, prefix: str = ""):
    """深度优先写出一棵子树，连线从书名一路贯通到叶子。

    prefix 携带祖先层的竖线（"│ " / "  "），每层固定两个等宽字符宽，
    所以整棵树的脉络是连续的，而不是只有本级的一个连接符。
    """
    total = len(children)
    for index, child in enumerate(children):
        last = index == total - 1
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm(0.3)
        paragraph.paragraph_format.space_before = Pt(6 if depth == 1 else 1.2)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing = 1.25
        # 有子节点的行别被拆到下一页末尾，脉络断页会更难读
        paragraph.paragraph_format.keep_with_next = bool(child["children"])

        if prefix:
            lead = paragraph.add_run(prefix)
            _set_run_font(lead, 10.5, color=COLOR_LINE, font=MONO_FONT)
        connector = paragraph.add_run("└ " if last else "├ ")
        _set_run_font(connector, 10.5, color=COLOR_LINE, font=MONO_FONT)

        is_category = child["node_type"] == NODE_TYPE_CATEGORY
        name_run = paragraph.add_run(child["name"])
        _set_run_font(
            name_run,
            11.5 if is_category else 10.5,
            bold=is_category,
            color=COLOR_BOOK if is_category else COLOR_BODY,
        )

        if child["summary"]:
            note = doc.add_paragraph()
            # 悬挂缩进对齐到名字起点：0.3 左边距 + 每层两个等宽字符
            note.paragraph_format.left_indent = Cm(0.3 + INDENT_STEP_CM * depth + 0.12)
            note.paragraph_format.space_before = Pt(0)
            note.paragraph_format.space_after = Pt(1)
            note.paragraph_format.line_spacing = 1.2
            note_run = note.add_run(child["summary"])
            _set_run_font(note_run, 9, color=COLOR_MUTED)

        if child["children"]:
            # 不是最后一个兄弟，竖线要继续往下画
            _write_children(doc, child["children"], depth + 1, prefix + ("  " if last else "│ "))


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
