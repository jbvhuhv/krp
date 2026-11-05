"""示例数据一键体验（Demo Bootstrap API）。

新注册用户最容易在两个地方流失：
1. 登录后满屏空状态，不知道这产品能给自己什么；
2. 上传真实笔记要等 LLM 抽取，网络/模型一抖就失败。

这里提供一个秒级完成的「样例书架」：一本小教材（2 章 8 个知识点）+
对应的一条笔记记录，全部由服务端静态写入，不调任何模型。
已有图谱数据的用户调用直接返回"无需引导"，幂等。
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db, get_graph_service
from app.core.constants import NOTE_STATUS
from app.core.logger import get_logger
from app.models.note import Note
from app.services.graph.constants import (
    NODE_TYPE_BOOK,
    NODE_TYPE_CATEGORY,
    NODE_TYPE_KNOWLEDGE,
)
from app.services.graph.local_service import LocalGraphService

logger = get_logger(__name__)
router = APIRouter()

SAMPLE_NOTE_CONTENT = """# 计算机网络 · 示例笔记

> 这是一条内置示例笔记：它已经完成 AI 抽取并生成了知识书《计算机网络 · 示例教材》。
> 你可以在这里体验反思答题、掌握度回写与数字分身；准备好自己的笔记后，直接删除它并上传真实内容即可。

## 网络与协议

- **计算机网络**：把分散的、独立功能的计算机通过通信链路与交换设备连接起来，
  在协议的协调下实现资源共享与信息传递的系统。
- **协议三要素**：语法（数据格式）、语义（动作与应答）、时序（事件顺序）。
  缺任何一项，通信双方都无法达成一致的理解。

## 分层与传输

- **分层模型**：OSI 七层与 TCP/IP 四层都是把复杂问题切成可独立演进的小问题；
  每层只向上一层提供服务，只对下一层隐藏实现。
- **TCP 与 UDP**：TCP 面向连接、可靠、有序，代价是握手与重传开销；
  UDP 无连接、开销小，适合实时音视频等"丢一点无所谓"的场景。

## 寻址

- **IP 地址**：网络层用来定位主机；IPv4 32 位已紧张，IPv6 128 位解决地址耗尽。
- **DNS**：把人类易记的域名翻译成 IP 地址，是一个自顶向下的分布式查询系统。
- **路由**：网络层决定分组走哪条路径；路由协议在路由器之间交换可达性信息。
"""

# 样例结构：书 → 2 章 → 每章 4 个知识点；points 为 (名称, 摘要)
SAMPLE_BOOK = {
    "name": "计算机网络 · 示例教材",
    "subject": "计算机网络",
    "chapters": [
        {
            "name": "第 1 章 网络与协议",
            "points": [
                ("计算机网络", "分散的计算机经通信链路与协议连接，实现资源共享与信息传递的系统。"),
                ("协议三要素", "语法、语义、时序——通信双方达成一致理解的三个组成部分。"),
                ("电路交换与分组交换", "电路交换先建立专用通路，分组交换按存储转发共享链路。"),
                ("带宽与时延", "链路容量决定吞吐上限；发送、传播、排队、处理四段时延构成总时延。"),
            ],
        },
        {
            "name": "第 2 章 分层与传输",
            "points": [
                ("OSI 与 TCP/IP 分层", "把复杂网络问题切成可独立演进的小问题，层间以服务接口衔接。"),
                ("TCP 与 UDP", "TCP 可靠有序、有握手重传开销；UDP 轻量无连接，适合实时场景。"),
                ("IP 地址与 DNS", "IP 定位主机；DNS 把域名翻译成 IP，是分布式的层次查询系统。"),
                ("路由与转发", "路由协议交换可达性信息，转发依据查表逐跳把分组送往目的地。"),
            ],
        },
    ],
    # 知识点间的横向关系 (源, 目标)
    "edges": [
        ("协议三要素", "计算机网络"),
        ("OSI 与 TCP/IP 分层", "协议三要素"),
        ("TCP 与 UDP", "OSI 与 TCP/IP 分层"),
        ("路由与转发", "IP 地址与 DNS"),
        ("带宽与时延", "电路交换与分组交换"),
    ],
}


@router.post("/bootstrap")
async def bootstrap_demo(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    graph_service=Depends(get_graph_service),
):
    """为空书架账号写入一套静态示例（1 本书 + 1 条笔记），不调用任何模型。"""
    if isinstance(graph_service, LocalGraphService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="当前运行在只读演示图谱模式，无法生成个人示例数据",
        )

    try:
        books = await graph_service.get_books(user_id)
    except Exception:  # noqa: BLE001 - 图谱探测失败与空书架同等对待，交给写入阶段报错
        books = []
    if books:
        return {
            "bootstrapped": False,
            "message": "书架已有知识书，无需示例数据",
        }

    note_id = str(uuid.uuid4())
    nodes_count = 0
    edges_count = 0

    try:
        book_id = await graph_service.create_node(
            user_id=user_id,
            name=SAMPLE_BOOK["name"],
            summary="一条示例笔记生成的知识书：网络基础与传输分层。",
            type=NODE_TYPE_BOOK,
            source_note_id=note_id,
            subject=SAMPLE_BOOK["subject"],
            node_type=NODE_TYPE_BOOK,
            origin="demo",
        )
        nodes_count += 1

        for chapter in SAMPLE_BOOK["chapters"]:
            category_id = await graph_service.create_node(
                user_id=user_id,
                name=chapter["name"],
                summary="",
                type=NODE_TYPE_CATEGORY,
                source_note_id=note_id,
                subject=SAMPLE_BOOK["subject"],
                node_type=NODE_TYPE_CATEGORY,
                parent_id=book_id,
                origin="demo",
            )
            nodes_count += 1

            for index, (point_name, point_summary) in enumerate(chapter["points"]):
                await graph_service.create_node(
                    user_id=user_id,
                    name=point_name,
                    summary=point_summary,
                    type=NODE_TYPE_KNOWLEDGE,
                    source_note_id=note_id,
                    subject=SAMPLE_BOOK["subject"],
                    node_type=NODE_TYPE_KNOWLEDGE,
                    parent_id=category_id,
                    origin="demo",
                    sort_order=index,
                )
                nodes_count += 1

        # 横向关系边：名称 → 已创建节点 id
        name_to_id = {}
        try:
            all_nodes = await graph_service.get_all_nodes(user_id)
            name_to_id = {n.get("name"): n.get("id") for n in all_nodes if n.get("name")}
        except Exception:  # noqa: BLE001 - 关系边是锦上添花，失败不影响书架生成
            logger.warning("示例图谱回读失败，跳过关系边", exc_info=True)

        for src_name, dst_name in SAMPLE_BOOK["edges"]:
            src_id = name_to_id.get(src_name)
            dst_id = name_to_id.get(dst_name)
            if src_id and dst_id and src_id != dst_id:
                edge_id = await graph_service.create_edge(
                    user_id=user_id,
                    source_id=src_id,
                    target_id=dst_id,
                )
                if edge_id:
                    edges_count += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("示例数据写入图谱失败 user=%s", user_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="知识图谱暂不可用，请稍后再试",
        ) from exc

    # 图谱写入成功后再落 SQLite 笔记记录，保证「笔记 → 知识书」能互相跳转
    note = Note(
        id=note_id,
        user_id=user_id,
        title="计算机网络 · 示例笔记",
        content=SAMPLE_NOTE_CONTENT,
        format="markdown",
        tags="示例,计算机网络",
        status=NOTE_STATUS["SUCCESS"],
        nodes_count=nodes_count,
        edges_count=edges_count,
        processed_time=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(note)
    await db.commit()

    return {
        "bootstrapped": True,
        "book_id": book_id,
        "note_id": note_id,
        "nodes_count": nodes_count,
        "edges_count": edges_count,
    }
