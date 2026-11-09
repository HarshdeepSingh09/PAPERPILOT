import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class DefinitionItem(BaseModel):
    term: str
    definition: str
    source_page: Optional[int] = None


class KeyConceptItem(BaseModel):
    concept: str
    summary: str
    key_points: List[str] = []
    source_page: Optional[int] = None


class ReactionEquationItem(BaseModel):
    reaction_type: str
    equation_latex: str
    description: str
    source_page: Optional[int] = None


class RevisionFormulaItem(BaseModel):
    formula_name: str
    formula_latex: str
    usage: str
    source_page: Optional[int] = None


class ComparisonParameter(BaseModel):
    parameter: str
    item_a: str
    item_b: str


class DifferenceComparisonItem(BaseModel):
    topic: str
    aspect_a: str
    aspect_b: str
    comparison_points: List[ComparisonParameter] = []
    source_page: Optional[int] = None


class FAQItem(BaseModel):
    question: str
    answer: str
    source_page: Optional[int] = None


class LastMinutePoint(BaseModel):
    point: str
    source_page: Optional[int] = None


class RevisionNotesGenerateRequest(BaseModel):
    document_id: str
    force_regenerate: bool = False


class RevisionNotesResponse(BaseModel):
    id: Optional[str] = None
    document_id: str
    title: str
    chapter_overview: str
    definitions: List[DefinitionItem] = []
    key_concepts: List[KeyConceptItem] = []
    reactions_equations: List[ReactionEquationItem] = []
    formulas: List[RevisionFormulaItem] = []
    differences_comparisons: List[DifferenceComparisonItem] = []
    faqs: List[FAQItem] = []
    last_minute_points: List[LastMinutePoint] = []
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None


# Backwards compatibility models
RevisionCard = KeyConceptItem
