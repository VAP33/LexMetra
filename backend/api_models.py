from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    inspection_date: date
    module: str = "lmpc"
    department: Optional[str] = "Department of Consumer Affairs"
    jurisdiction: str = "IN"
    product_category: Optional[str] = None
    commodity_type: Optional[str] = None
    top_k: int = Field(default=6, ge=1, le=20)


class RAGRetrieveRequest(RAGQueryRequest):
    pass
