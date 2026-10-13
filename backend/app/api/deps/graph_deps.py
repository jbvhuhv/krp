def get_graph_service():
    from app.core.database import neo4j_driver
    from app.services.graph_service import GraphService

    return GraphService(driver=neo4j_driver)
