from fastapi import APIRouter

from app.collectors import list_adapters
from app.llm.deepseek import DeepSeekClient, is_online
from app.schemas import HealthOut

router = APIRouter()


@router.get("/health", response_model=HealthOut)
def health():
    client = DeepSeekClient()
    return HealthOut(
        status="ok",
        online=is_online(),
        deepseek_configured=client.configured,
        adapters=list_adapters(),
    )
