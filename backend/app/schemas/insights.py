import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class CategoryUpdateRequest(BaseModel):
    category: str = Field(..., min_length=1, max_length=100)


class InsightsGenerateRequest(BaseModel):
    document_id: str
    category: Optional[str] = None
    force_regenerate: bool = False


class AdaptiveInsightsResponse(BaseModel):
    id: Optional[str] = None
    document_id: str
    category: str
    title: str
    generation_source: str = "gemini"
    insights: Dict[str, Any]
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
