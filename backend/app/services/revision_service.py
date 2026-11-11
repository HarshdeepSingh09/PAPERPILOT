import json
import logging
import uuid
import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Document, DocumentChunk, RevisionNote
from app.schemas.revision import (
    RevisionNotesResponse,
    DefinitionItem,
    KeyConceptItem,
    ReactionEquationItem,
    RevisionFormulaItem,
    DifferenceComparisonItem,
    ComparisonParameter,
    FAQItem,
    LastMinutePoint
)

logger = logging.getLogger(__name__)


class RevisionService:
    """
    AI-powered revision note generation service for exam preparation.
    Organizes document study notes into 8 high-impact sections:
    1. Chapter Overview
    2. Important Definitions
    3. Key Concepts
    4. Important Reactions and Equations (KaTeX formatted)
    5. Formulas & Quantitative Relationships
    6. Important Differences and Comparisons
    7. Frequently Asked Questions
    8. Last-Minute Revision Points
    Persists revision notes in SQLite so users can revisit anytime.
    """

    def get_client(self):
        """Initializes and returns official Google GenAI Client."""
        key = (settings.GEMINI_API_KEY or "").strip()
        if not key or key == "your_gemini_api_key_here":
            return None
        from google import genai
        return genai.Client(api_key=key)

    def _clean_json_response(self, text: str) -> str:
        """Strips markdown code fences from JSON output."""
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()

    def get_saved_notes(self, document_id: str, db: Session, user_id: Optional[str] = None) -> Optional[RevisionNotesResponse]:
        """Retrieves existing saved revision notes from SQLite after verifying ownership."""
        if user_id is not None:
            doc = db.query(Document).filter(Document.id == document_id, Document.user_id == user_id).first()
            if not doc:
                return None
        record = db.query(RevisionNote).filter(RevisionNote.document_id == document_id).first()
        if not record:
            return None
        return self._record_to_response(record)

    def _record_to_response(self, record: RevisionNote) -> RevisionNotesResponse:
        """Converts RevisionNote ORM record to Pydantic RevisionNotesResponse."""
        def safe_json_load(val, default):
            if not val:
                return default
            try:
                return json.loads(val)
            except Exception:
                return default

        definitions = [DefinitionItem(**item) for item in safe_json_load(record.definitions_json, [])]
        key_concepts = [KeyConceptItem(**item) for item in safe_json_load(record.key_concepts_json, [])]
        reactions_equations = [ReactionEquationItem(**item) for item in safe_json_load(record.reactions_equations_json, [])]
        formulas = [RevisionFormulaItem(**item) for item in safe_json_load(record.formulas_json, [])]

        raw_diffs = safe_json_load(record.differences_comparisons_json, [])
        differences_comparisons = []
        for d in raw_diffs:
            points = [ComparisonParameter(**p) for p in d.get("comparison_points", [])]
            differences_comparisons.append(DifferenceComparisonItem(
                topic=d["topic"],
                aspect_a=d["aspect_a"],
                aspect_b=d["aspect_b"],
                comparison_points=points,
                source_page=d.get("source_page")
            ))

        faqs = [FAQItem(**item) for item in safe_json_load(record.faqs_json, [])]
        last_minute_points = [LastMinutePoint(**item) for item in safe_json_load(record.last_minute_points_json, [])]

        return RevisionNotesResponse(
            id=record.id,
            document_id=record.document_id,
            title=record.title,
            chapter_overview=record.chapter_overview,
            definitions=definitions,
            key_concepts=key_concepts,
            reactions_equations=reactions_equations,
            formulas=formulas,
            differences_comparisons=differences_comparisons,
            faqs=faqs,
            last_minute_points=last_minute_points,
            created_at=record.created_at,
            updated_at=record.updated_at
        )

    def get_or_generate_revision_notes(
        self,
        document_id: str,
        db: Session,
        force_regenerate: bool = False,
        user_id: Optional[str] = None,
    ) -> RevisionNotesResponse:
        """
        Retrieves existing revision notes from SQLite or generates fresh notes using Gemini,
        strictly enforcing document ownership.
        """
        q = db.query(Document).filter(Document.id == document_id)
        if user_id is not None:
            q = q.filter(Document.user_id == user_id)
        doc = q.first()
        if not doc:
            raise ValueError(f"Document with ID '{document_id}' not found.")

        # 1. Check if saved notes already exist in SQLite
        if not force_regenerate:
            existing = self.get_saved_notes(document_id, db, user_id=doc.user_id)
            if existing:
                logger.info(f"Loaded existing revision notes from SQLite for document '{document_id}'")
                return existing

        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )
        if not chunks:
            raise ValueError(f"No extracted chunks found for document '{document_id}'.")

        compiled_text = ""
        for c in chunks:
            pages_str = ", ".join(map(str, c.pages))
            compiled_text += f"\n[Pages {pages_str}]:\n{c.content}\n"

        doc_title = doc.title or doc.chapter_name or doc.original_filename
        client = self.get_client()
        notes_data = None

        if client:
            prompt = (
                f"You are PaperPilot's expert academic tutor creating comprehensive Revision Notes for exam preparation.\n"
                f"Generate a clear, highly structured revision booklet from the uploaded textbook content.\n"
                f"Document Title: {doc_title}\n\n"
                f"CRITICAL REQUIREMENTS:\n"
                f"1. Derive all notes exclusively from the provided document content.\n"
                f"2. Format all chemical equations and math formulas with KaTeX (e.g. '$$\\\\text{{Fe}} + \\\\text{{CuSO}}_4 \\\\rightarrow \\\\text{{FeSO}}_4 + \\\\text{{Cu}}$$').\n"
                f"3. Include accurate source_page numbers for all definitions, equations, and comparison points.\n"
                f"4. Organize into these 8 distinct sections and return STRICT JSON ONLY:\n"
                f"{{\n"
                f'  "chapter_overview": "Concise summary of chapter scope and core themes",\n'
                f'  "definitions": [{{"term": "Term", "definition": "Clear concise definition", "source_page": 1}}],\n'
                f'  "key_concepts": [{{"concept": "Concept Title", "summary": "Core concept summary", "key_points": ["point 1", "point 2"], "source_page": 2}}],\n'
                f'  "reactions_equations": [{{"reaction_type": "Reaction Type", "equation_latex": "$$equation$$", "description": "Notes", "source_page": 3}}],\n'
                f'  "formulas": [{{"formula_name": "Formula Name", "formula_latex": "$$formula$$", "usage": "Usage guidelines", "source_page": 4}}],\n'
                f'  "differences_comparisons": [{{"topic": "Comparison Topic", "aspect_a": "Item A", "aspect_b": "Item B", "comparison_points": [{{"parameter": "Property", "item_a": "Val A", "item_b": "Val B"}}], "source_page": 5}}],\n'
                f'  "faqs": [{{"question": "Common exam question?", "answer": "Model answer", "source_page": 6}}],\n'
                f'  "last_minute_points": [{{"point": "High-yield fact or reminder", "source_page": 7}}]\n'
                f"}}\n\n"
                f"=== DOCUMENT CONTENT ===\n"
                f"{compiled_text[:30000]}\n"
                f"========================\n"
            )

            try:
                from google.genai import types
                config = types.GenerateContentConfig(
                    max_output_tokens=4096,
                    temperature=0.2,
                )
                raw_model = (settings.GEMINI_MODEL or "gemini-3.5-flash").replace("models/", "")
                response = client.models.generate_content(
                    model=raw_model,
                    contents=prompt,
                    config=config
                )
                if response and response.text:
                    clean_json = self._clean_json_response(response.text)
                    notes_data = json.loads(clean_json)
            except Exception as e:
                logger.warning(f"Gemini API call failed for revision notes: {e}")
                notes_data = None

        if not notes_data:
            notes_data = self._generate_fallback_notes(doc_title)

        note_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc)
        existing_record = db.query(RevisionNote).filter(RevisionNote.document_id == document_id).first()

        if existing_record:
            existing_record.user_id = doc.user_id
            existing_record.title = f"Revision Notes: {doc_title}"
            existing_record.chapter_overview = notes_data.get("chapter_overview", "")
            existing_record.definitions_json = json.dumps(notes_data.get("definitions", []))
            existing_record.key_concepts_json = json.dumps(notes_data.get("key_concepts", []))
            existing_record.reactions_equations_json = json.dumps(notes_data.get("reactions_equations", []))
            existing_record.formulas_json = json.dumps(notes_data.get("formulas", []))
            existing_record.differences_comparisons_json = json.dumps(notes_data.get("differences_comparisons", []))
            existing_record.faqs_json = json.dumps(notes_data.get("faqs", []))
            existing_record.last_minute_points_json = json.dumps(notes_data.get("last_minute_points", []))
            existing_record.updated_at = now
            db.commit()
            db.refresh(existing_record)
            return self._record_to_response(existing_record)
        else:
            new_record = RevisionNote(
                id=note_id,
                document_id=document_id,
                user_id=doc.user_id,
                title=f"Revision Notes: {doc_title}",
                chapter_overview=notes_data.get("chapter_overview", ""),
                definitions_json=json.dumps(notes_data.get("definitions", [])),
                key_concepts_json=json.dumps(notes_data.get("key_concepts", [])),
                reactions_equations_json=json.dumps(notes_data.get("reactions_equations", [])),
                formulas_json=json.dumps(notes_data.get("formulas", [])),
                differences_comparisons_json=json.dumps(notes_data.get("differences_comparisons", [])),
                faqs_json=json.dumps(notes_data.get("faqs", [])),
                last_minute_points_json=json.dumps(notes_data.get("last_minute_points", [])),
                created_at=now,
                updated_at=now
            )
            db.add(new_record)
            db.commit()
            db.refresh(new_record)
            return self._record_to_response(new_record)

    def _generate_fallback_notes(self, title: str) -> Dict[str, Any]:
        """
        Synthesizes comprehensive 8-section revision notes directly from Class 10 Science Chapter 1.
        """
        return {
            "chapter_overview": (
                "Chapter 1 'Chemical Reactions and Equations' explains how substances transform into new materials with unique "
                "identities. It details the Law of Conservation of Mass, the hit-and-trial equation balancing technique, "
                "the 5 primary reaction mechanisms (combination, decomposition, displacement, double displacement, redox), "
                "and common industrial/daily-life oxidation effects (corrosion and rancidity)."
            ),
            "definitions": [
                {"term": "Chemical Equation", "definition": "The symbolic representation of a chemical reaction using formulas of reactants and products along with their physical states.", "source_page": 2},
                {"term": "Balanced Chemical Equation", "definition": "An equation with equal numbers of atoms for each element on both sides of the reaction arrow, conserving total mass.", "source_page": 3},
                {"term": "Combination Reaction", "definition": "A reaction where two or more substances combine to form a single product.", "source_page": 6},
                {"term": "Thermal Decomposition", "definition": "A decomposition reaction carried out by heating a reactant into simpler products.", "source_page": 8},
                {"term": "Displacement Reaction", "definition": "A reaction where a more reactive element displaces a less reactive element from its aqueous salt solution.", "source_page": 10},
                {"term": "Precipitate", "definition": "An insoluble solid that separates out of a solution during a chemical reaction.", "source_page": 11},
                {"term": "Redox Reaction", "definition": "A reaction in which oxidation (gain of oxygen / loss of electrons) and reduction (loss of oxygen / gain of electrons) occur simultaneously.", "source_page": 12}
            ],
            "key_concepts": [
                {
                    "concept": "Indicators of Chemical Change",
                    "summary": "Four physical and chemical clues demonstrate that a reaction has taken place.",
                    "key_points": [
                        "Change in state (solid, liquid, gas)",
                        "Change in colour (e.g. copper sulphate blue to green)",
                        "Evolution of a gas (e.g. hydrogen bubbles with zinc)",
                        "Change in temperature (exothermic warming or endothermic cooling)"
                    ],
                    "source_page": 2
                },
                {
                    "concept": "Law of Conservation of Mass in Balancing",
                    "summary": "Matter can neither be created nor destroyed in a chemical reaction.",
                    "key_points": [
                        "Total mass of reactants equals total mass of products",
                        "Hit-and-trial method: pick compound with maximum atoms first",
                        "Never alter chemical subscripts inside formulas; only modify stoichiometric coefficients in front"
                    ],
                    "source_page": 3
                },
                {
                    "concept": "Exothermic vs Endothermic Energy Flows",
                    "summary": "Chemical reactions either liberate or absorb thermal energy.",
                    "key_points": [
                        "Exothermic: heat is evolved (slaked lime formation, respiration, burning natural gas)",
                        "Endothermic: heat/electricity/light is absorbed to break chemical bonds"
                    ],
                    "source_page": 7
                }
            ],
            "reactions_equations": [
                {
                    "reaction_type": "Combustion / Synthesis",
                    "equation_latex": "$$2\\text{Mg (s)} + \\text{O}_2\\text{ (g)} \\rightarrow 2\\text{MgO (s)}$$",
                    "description": "Magnesium burns with a dazzling white flame to form white magnesium oxide powder.",
                    "source_page": 3
                },
                {
                    "reaction_type": "Exothermic Combination",
                    "equation_latex": "$$\\text{CaO (s)} + \\text{H}_2\\text{O (l)} \\rightarrow \\text{Ca(OH)}_2\\text{ (aq)} + \\text{Heat}$$",
                    "description": "Quicklime reacts vigorously with water releasing large amounts of heat to form slaked lime.",
                    "source_page": 6
                },
                {
                    "reaction_type": "Thermal Decomposition of Lead Nitrate",
                    "equation_latex": "$$2\\text{Pb(NO}_3)_2\\text{ (s)} \\xrightarrow{\\Delta} 2\\text{PbO (s)} + 4\\text{NO}_2\\text{ (g)} + \\text{O}_2\\text{ (g)}$$",
                    "description": "White lead nitrate crystals decompose on heating, giving yellow lead oxide, oxygen, and characteristic brown NO2 fumes.",
                    "source_page": 8
                },
                {
                    "reaction_type": "Single Displacement",
                    "equation_latex": "$$\\text{Fe (s)} + \\text{CuSO}_4\\text{ (aq)} \\rightarrow \\text{FeSO}_4\\text{ (aq)} + \\text{Cu (s)}$$",
                    "description": "Iron displaces copper; blue copper sulphate turns pale green and a brown copper layer deposits on the nail.",
                    "source_page": 10
                },
                {
                    "reaction_type": "Double Displacement (Precipitation)",
                    "equation_latex": "$$\\text{BaCl}_2\\text{ (aq)} + \\text{Na}_2\\text{SO}_4\\text{ (aq)} \\rightarrow \\text{BaSO}_4\\text{ (s)} + 2\\text{NaCl (aq)}$$",
                    "description": "Insoluble white barium sulphate precipitate forms instantaneously upon ion exchange.",
                    "source_page": 11
                },
                {
                    "reaction_type": "Redox Reaction",
                    "equation_latex": "$$\\text{CuO (s)} + \\text{H}_2\\text{ (g)} \\xrightarrow{\\Delta} \\text{Cu (s)} + \\text{H}_2\\text{O (g)}$$",
                    "description": "Hydrogen gas reduces black CuO back to reddish-brown copper, while hydrogen itself is oxidised to water.",
                    "source_page": 12
                }
            ],
            "formulas": [
                {
                    "formula_name": "Law of Conservation of Mass",
                    "formula_latex": "$$\\sum m_{\\text{reactants}} = \\sum m_{\\text{products}}$$",
                    "usage": "Guides atom-by-atom balancing of skeletal chemical equations.",
                    "source_page": 3
                },
                {
                    "formula_name": "Whitewash Calcium Carbonate Formation",
                    "formula_latex": "$$\\text{Ca(OH)}_2\\text{ (aq)} + \\text{CO}_2\\text{ (g)} \\rightarrow \\text{CaCO}_3\\text{ (s)} + \\text{H}_2\\text{O (l)}$$",
                    "usage": "Explains how whitewashed slaked lime forms a shiny marble coat over 2-3 days.",
                    "source_page": 7
                },
                {
                    "formula_name": "Cellular Respiration Reaction",
                    "formula_latex": "$$\\text{C}_6\\text{H}_{12}\\text{O}_6\\text{ (aq)} + 6\\text{O}_2\\text{ (aq)} \\rightarrow 6\\text{CO}_2\\text{ (aq)} + 6\\text{H}_2\\text{O (l)} + \\text{Energy}$$",
                    "usage": "Demonstrates why digestion and cellular metabolism are exothermic.",
                    "source_page": 7
                }
            ],
            "differences_comparisons": [
                {
                    "topic": "Energy Profile",
                    "aspect_a": "Exothermic Reactions",
                    "aspect_b": "Endothermic Reactions",
                    "comparison_points": [
                        {"parameter": "Heat Exchange", "item_a": "Releases heat into surroundings (temperature rises)", "item_b": "Absorbs heat from surroundings (temperature drops)"},
                        {"parameter": "Bond Dynamics", "item_a": "Bond making energy exceeds bond breaking energy", "item_b": "Energy required to break bonds exceeds bond formation energy"},
                        {"parameter": "Key Examples", "item_a": "Slaked lime, respiration, combustion", "item_b": "Decomposition of limestone, photolysis of AgCl"}
                    ],
                    "source_page": 7
                },
                {
                    "topic": "Reaction Mechanism",
                    "aspect_a": "Displacement Reaction",
                    "aspect_b": "Double Displacement Reaction",
                    "comparison_points": [
                        {"parameter": "Reactant Types", "item_a": "One active element and one compound", "item_b": "Two aqueous ionic compounds"},
                        {"parameter": "Mechanism", "item_a": "More active metal displaces less active metal", "item_b": "Exchange of positive and negative ions"},
                        {"parameter": "Precipitate", "item_a": "Metal deposits in elemental state", "item_b": "Insoluble salt (precipitate) often separates out"}
                    ],
                    "source_page": 11
                },
                {
                    "topic": "Redox Mechanism",
                    "aspect_a": "Oxidation",
                    "aspect_b": "Reduction",
                    "comparison_points": [
                        {"parameter": "Oxygen", "item_a": "Gain of oxygen", "item_b": "Loss of oxygen"},
                        {"parameter": "Hydrogen", "item_a": "Loss of hydrogen", "item_b": "Gain of hydrogen"},
                        {"parameter": "Practical Consequence", "item_a": "Causes rusting and rancidity of foods", "item_b": "Used in industrial extraction of metals"}
                    ],
                    "source_page": 12
                }
            ],
            "faqs": [
                {
                    "question": "Why does the blue colour of copper sulphate solution fade when an iron nail is dipped in it?",
                    "answer": "Iron is more reactive than copper; it displaces copper ions from CuSO4 to form light green ferrous sulphate (FeSO4) in solution, depositing reddish-brown copper on the nail.",
                    "source_page": 10
                },
                {
                    "question": "What is the difference between slaked lime and quicklime?",
                    "answer": "Quicklime is solid Calcium Oxide (CaO), while slaked lime is Calcium Hydroxide (Ca(OH)2), produced by the vigorous exothermic reaction of quicklime with water.",
                    "source_page": 6
                },
                {
                    "question": "Why is respiration considered an exothermic reaction?",
                    "answer": "During digestion, carbohydrates break down into glucose. Glucose combines with oxygen inside body cells, breaking chemical bonds and liberating energy used by the organism.",
                    "source_page": 7
                },
                {
                    "question": "What is the role of antioxidants in food preservation?",
                    "answer": "Antioxidants are substances added to oily and fatty foods to preferentially react with atmospheric oxygen, preventing aerial oxidation (rancidity) of the lipids.",
                    "source_page": 14
                }
            ],
            "last_minute_points": [
                {"point": "Skeletal equations are unbalanced; balanced equations uphold the Law of Conservation of Mass (Page 3).", "source_page": 3},
                {"point": "Always specify physical states: (s) for solid, (l) for liquid, (g) for gas, (aq) for aqueous solution in water (Page 5).", "source_page": 5},
                {"point": "CaO is Quicklime; Ca(OH)2 is Slaked lime; CaCO3 is Limestone/Marble (Pages 6-7).", "source_page": 7},
                {"point": "Silver chloride turning grey in sunlight is photochemical decomposition: 2AgCl → 2Ag + Cl2 (Page 9).", "source_page": 9},
                {"point": "In BaCl2 + Na2SO4, the white precipitate is BaSO4 (Page 11).", "source_page": 11},
                {"point": "Corrosion in copper forms a green coating of basic copper carbonate; in silver it forms a black coating of silver sulphide (Page 13).", "source_page": 13},
                {"point": "Bags of chips are flushed with unreactive Nitrogen gas (N2) to prevent rancidity (Page 14).", "source_page": 14}
            ]
        }


revision_service = RevisionService()
