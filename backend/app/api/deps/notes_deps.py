from app.api.deps.ai_deps import get_ai_service
from app.api.deps.graph_deps import get_graph_service


def get_extraction_service():
    from app.core.database import AsyncSessionLocal
    from app.services.extraction_service import ExtractionService

    return ExtractionService(
        ai_service=get_ai_service(),
        graph_service=get_graph_service(),
        session_factory=AsyncSessionLocal,
    )

def get_ocr_service():
    from app.services.ai.base import create_vision_provider
    from app.services.ocr_service import OcrService

    return OcrService(provider=create_vision_provider())
