import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ConceptItem(BaseModel):
    term: str
    definition: str
    source_page: Optional[int] = None


class FormulaEquationItem(BaseModel):
    name: str
    equation_latex: str
    explanation: str
    source_page: Optional[int] = None


class ChapterSummaryItem(BaseModel):
    chapter_title: str
    summary: str
    key_points: List[str] = []
    source_page: Optional[int] = None


class FactItem(BaseModel):
    fact: str
    category: Optional[str] = "Key Fact"
    source_page: Optional[int] = None


class PageRefItem(BaseModel):
    page: int
    topic: str
    snippet: Optional[str] = None


class SummaryGenerateRequest(BaseModel):
    document_id: str
    format: Optional[str] = "comprehensive"
    force_regenerate: bool = False


class SummaryResponse(BaseModel):
    id: Optional[str] = None
    document_id: str
    title: str
    overview: str
    executive_overview: str
    key_takeaways: List[str]
    important_concepts: List[ConceptItem] = []
    formulas_equations: List[FormulaEquationItem] = []
    chapter_summaries: List[ChapterSummaryItem] = []
    important_facts: List[FactItem] = []
    page_references: List[PageRefItem] = []
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
