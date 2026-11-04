def get_graph_service():
    """获取图谱服务实现。

    - `GRAPH_BACKEND=auto`（默认）：Neo4j 可用时用 Neo4j；不可用时退回内置只读演示图谱，
      保证没有图数据库的环境里「知识图谱 / 知识画像」页面依然有内容。
    - `neo4j`：始终使用 Neo4j（不可用则报错）。
    - `sqlite`：始终使用内置只读演示图谱（适合纯演示环境）。
    """
    from app.core.config import settings
    from app.core.database import neo4j_driver
    from app.services.graph import GraphService, neo4j_available

    mode = (settings.GRAPH_BACKEND or "auto").strip().lower()
    if mode == "sqlite" or (mode == "auto" and neo4j_available() is False):
        from app.services.graph.local_service import LocalGraphService

        return LocalGraphService()
    return GraphService(driver=neo4j_driver)
