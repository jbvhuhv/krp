def get_ai_service():
    from app.services.ai_service import create_ai_service

    return create_ai_service()
