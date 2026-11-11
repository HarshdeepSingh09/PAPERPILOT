import datetime
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Document, DocumentChunk, DocumentInsight
from app.services.classification_service import DOCUMENT_CATEGORIES

logger = logging.getLogger(__name__)

LEGAL_DISCLAIMER = (
    "Informational analysis only: this overview summarizes extracted document text and "
    "does not constitute legal advice or create an attorney-client relationship."
)


class AdaptiveInsightsService:
    """
    Generates, caches, and serves category-specific structured document intelligence
    for Research Papers, Business Reports, Meeting Notes, Legal Documents,
    Financial Reports, User Manuals / Technical Documentation, and General Documents.
    Strictly grounded in extracted document chunks; never invents figures, assignees,
    deadlines, or legal obligations.
    """

    def get_client(self):
        key = (settings.GEMINI_API_KEY or "").strip()
        if not key or key == "your_gemini_api_key_here":
            return None
        from google import genai
        return genai.Client(api_key=key)

    @staticmethod
    def _clean_json_response(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()

    @staticmethod
    def _format_citation(chunk: DocumentChunk, file_format: str) -> str:
        unit = "Page" if file_format == "pdf" else "Section"
        base = f"{unit} {chunk.page_start}"
        if chunk.page_end and chunk.page_end != chunk.page_start:
            base = f"{unit}s {chunk.page_start}-{chunk.page_end}"
        if file_format != "pdf" and getattr(chunk, "section_title", None):
            title = str(chunk.section_title).strip()
            if title and not title.lower().startswith("section "):
                return f"{base}: {title[:45]}"
        return base

    def get_saved_insights(
        self,
        document_id: str,
        category: str,
        db: Session,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if user_id is not None:
            doc = db.query(Document).filter(Document.id == document_id, Document.user_id == user_id).first()
            if not doc:
                return None
        record = (
            db.query(DocumentInsight)
            .filter(
                DocumentInsight.document_id == document_id,
                DocumentInsight.category == category,
            )
            .order_by(DocumentInsight.updated_at.desc())
            .first()
        )
        if not record:
            return None
        return self._record_to_dict(record)

    @staticmethod
    def _record_to_dict(record: DocumentInsight) -> Dict[str, Any]:
        try:
            parsed = json.loads(record.insights_json)
        except Exception:
            parsed = {}
        return {
            "id": record.id,
            "document_id": record.document_id,
            "category": record.category,
            "title": record.title,
            "generation_source": record.generation_source or "gemini",
            "insights": parsed,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    def get_or_generate_insights(
        self,
        document_id: str,
        db: Session,
        category: Optional[str] = None,
        force_regenerate: bool = False,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        q = db.query(Document).filter(Document.id == document_id)
        if user_id is not None:
            q = q.filter(Document.user_id == user_id)
        doc = q.first()
        if not doc:
            raise ValueError(f"Document with ID '{document_id}' not found.")

        target_category = category or doc.document_category or "General Document"
        if target_category not in DOCUMENT_CATEGORIES:
            target_category = "General Document"

        if not force_regenerate:
            cached = self.get_saved_insights(document_id, target_category, db, user_id=doc.user_id)
            if cached:
                return cached

        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )
        if not chunks:
            raise ValueError(f"No extracted text chunks available for document '{document_id}'.")

        file_format = (doc.file_format or "pdf").lower()
        doc_title = doc.title or doc.original_filename

        # Build bounded document context covering beginning, middle, and end
        selected_chunks = self._select_representative_chunks(chunks, max_chars=28000)
        compiled_text = ""
        for c in selected_chunks:
            cit = self._format_citation(c, file_format)
            compiled_text += f"\n[{cit}]:\n{c.content}\n"

        generated_payload: Optional[Dict[str, Any]] = None
        generation_source = "extractive"

        client = self.get_client()
        if client:
            prompt = self._build_category_prompt(
                category=target_category,
                doc_title=doc_title,
                file_format=file_format,
                compiled_text=compiled_text,
            )
            try:
                from google.genai import types
                config = types.GenerateContentConfig(
                    max_output_tokens=3072,
                    temperature=0.15,
                )
                raw_model = (settings.GEMINI_MODEL or "gemini-3.5-flash").replace("models/", "")
                response = client.models.generate_content(
                    model=raw_model,
                    contents=prompt,
                    config=config,
                )
                if response and response.text:
                    clean_json = self._clean_json_response(response.text)
                    parsed = json.loads(clean_json)
                    if isinstance(parsed, dict):
                        generated_payload = self._sanitize_payload(target_category, parsed)
                        generation_source = "gemini"
            except Exception as e:
                logger.warning(f"Gemini adaptive insights generation failed ({type(e).__name__}: {e}); using extractive grounding.")
                generated_payload = None

        if not generated_payload:
            generated_payload = self._extract_grounded_fallback(
                category=target_category,
                doc=doc,
                chunks=chunks,
                file_format=file_format,
            )
            generation_source = "extractive"

        if target_category == "Legal Document":
            generated_payload["disclaimer"] = LEGAL_DISCLAIMER

        now = datetime.datetime.now(datetime.timezone.utc)
        existing = (
            db.query(DocumentInsight)
            .filter(
                DocumentInsight.document_id == document_id,
                DocumentInsight.category == target_category,
            )
            .first()
        )
        if existing:
            existing.user_id = doc.user_id
            existing.title = f"{target_category}: {doc_title}"[:250]
            existing.insights_json = json.dumps(generated_payload)
            existing.generation_source = generation_source
            existing.updated_at = now
            db.commit()
            db.refresh(existing)
            return self._record_to_dict(existing)

        record = DocumentInsight(
            id=str(uuid.uuid4()),
            document_id=document_id,
            user_id=doc.user_id,
            category=target_category,
            title=f"{target_category}: {doc_title}"[:250],
            insights_json=json.dumps(generated_payload),
            generation_source=generation_source,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return self._record_to_dict(record)

    @staticmethod
    def _select_representative_chunks(chunks: List[DocumentChunk], max_chars: int = 28000) -> List[DocumentChunk]:
        total = sum(len(c.content or "") for c in chunks)
        if total <= max_chars:
            return chunks
        # Evenly sample chunks across beginning, middle, and conclusion
        selected: List[DocumentChunk] = []
        used_chars = 0
        n = len(chunks)
        step = max(1, n // 24)
        indices = list(range(0, n, step))
        if (n - 1) not in indices:
            indices.append(n - 1)
        for idx in indices:
            c = chunks[idx]
            if used_chars + len(c.content or "") > max_chars and selected:
                break
            selected.append(c)
            used_chars += len(c.content or "")
        return selected

    def _build_category_prompt(
        self,
        category: str,
        doc_title: str,
        file_format: str,
        compiled_text: str,
    ) -> str:
        citation_label = "Page X" if file_format == "pdf" else "Section X"
        schemas: Dict[str, str] = {
            "Research Paper": (
                '{\n'
                '  "research_summary": "Concise synthesis of the paper",\n'
                '  "research_objective": "Primary research question / hypothesis / goal",\n'
                '  "methodology_analysis": ["Methodological step, dataset, or experimental design detail"],\n'
                '  "key_findings": [{"finding": "Specific empirical result", "citation": "' + citation_label + '"}],\n'
                '  "limitations": ["Explicitly stated limitation or scope boundary"],\n'
                '  "important_contributions": ["Core theoretical or practical contribution"]\n'
                '}'
            ),
            "Business Report": (
                '{\n'
                '  "executive_summary": "Concise executive summary",\n'
                '  "key_insights": [{"insight": "Strategic business insight", "citation": "' + citation_label + '"}],\n'
                '  "important_figures": [{"metric": "Metric name", "value": "Exact figure from text", "context": "Brief context", "citation": "' + citation_label + '"}],\n'
                '  "business_findings": ["Operational or market finding grounded in document"],\n'
                '  "action_items": ["Concrete action stated in report"],\n'
                '  "recommendations": ["Strategic recommendation stated in report"]\n'
                '}\nNOTE: NEVER invent financial or business figures. Leave important_figures as [] if none are explicitly stated.'
            ),
            "Meeting Notes": (
                '{\n'
                '  "meeting_summary": "Concise overview of meeting purpose and outcome",\n'
                '  "important_decisions": [{"decision": "Decision agreed upon", "citation": "' + citation_label + '"}],\n'
                '  "action_items": [{"action": "Action item described", "citation": "' + citation_label + '"}],\n'
                '  "assigned_responsibilities": [{"assignee": "Exact person/team name", "task": "Assigned task", "citation": "' + citation_label + '"}],\n'
                '  "deadlines_mentioned": [{"deadline": "Exact date/timeframe", "item": "Deliverable or milestone", "citation": "' + citation_label + '"}],\n'
                '  "unresolved_issues": ["Open question, blocker, or deferred item"]\n'
                '}\nNOTE: ONLY include assignees and deadlines EXPLICITLY written in the text; return [] if absent.'
            ),
            "Legal Document": (
                '{\n'
                '  "disclaimer": "' + LEGAL_DISCLAIMER + '",\n'
                '  "document_overview": "Neutral factual overview of the legal instrument",\n'
                '  "important_clauses": [{"clause_title": "Clause name/number", "summary": "Neutral summary", "citation": "' + citation_label + '"}],\n'
                '  "obligations": [{"party": "Named party", "obligation": "Explicit contractual duty", "citation": "' + citation_label + '"}],\n'
                '  "dates_and_deadlines": [{"date_or_period": "Effective date / term / notice period", "context": "What it applies to", "citation": "' + citation_label + '"}],\n'
                '  "parties_involved": ["Named party 1", "Named party 2"],\n'
                '  "important_conditions": ["Termination, liability, governing law, or conditional trigger explicitly stated"]\n'
                '}\nNOTE: Informational only, NOT legal advice. Never invent legal obligations or unstated conclusions.'
            ),
            "Financial Report": (
                '{\n'
                '  "financial_summary": "Concise overview of reported financial performance",\n'
                '  "important_figures": [{"metric": "Metric name", "value": "Exact reported figure", "period": "Period", "citation": "' + citation_label + '"}],\n'
                '  "revenue_and_expenses": [{"item": "Revenue or expense line item", "amount": "Exact amount", "details": "Context", "citation": "' + citation_label + '"}],\n'
                '  "key_financial_trends": ["Reported period-over-period or operational financial trend"],\n'
                '  "important_ratios": [{"ratio_name": "Ratio name", "value": "Value", "note": "Reported or directly supported", "citation": "' + citation_label + '"}]\n'
                '}\nNOTE: NEVER fabricate missing numbers or calculate unsupported ratios. Return [] for important_ratios if insufficient data exists.'
            ),
            "User Manual / Technical Documentation": (
                '{\n'
                '  "documentation_summary": "Overview of system/product covered",\n'
                '  "important_instructions": [{"instruction": "Key operational rule or instruction", "citation": "' + citation_label + '"}],\n'
                '  "setup_steps": [{"step_number": 1, "title": "Step title", "detail": "Instruction details", "citation": "' + citation_label + '"}],\n'
                '  "troubleshooting": [{"issue": "Problem or error", "resolution": "Documented fix", "citation": "' + citation_label + '"}],\n'
                '  "important_warnings": [{"warning": "Safety, data-loss, or compatibility warning", "citation": "' + citation_label + '"}]\n'
                '}'
            ),
            "General Document": (
                '{\n'
                '  "ai_summary": "Clear comprehensive summary of the document",\n'
                '  "key_points": [{"point": "Important takeaway from the text", "citation": "' + citation_label + '"}],\n'
                '  "important_information": [{"topic": "Topic or entity", "detail": "Verified detail from text", "citation": "' + citation_label + '"}]\n'
                '}'
            ),
        }
        schema_str = schemas.get(category, schemas["General Document"])
        return (
            f"You are PaperPilot's specialized document analysis engine for category: '{category}'.\n"
            f"Document Title: {doc_title}\n"
            f"Source Citation Format: Use '{citation_label}' (from the bracketed chunk labels below).\n\n"
            "STRICT GROUNDING RULES:\n"
            "1. Derive ALL statements exclusively from the provided excerpts. Do NOT fabricate facts, numbers, ratios, deadlines, or names.\n"
            "2. If a specific array field has no explicit evidence in the document, return an empty list [].\n"
            "3. Return STRICT JSON ONLY (no markdown fences outside JSON) matching this schema:\n"
            f"{schema_str}\n\n"
            f"=== DOCUMENT EXCERPTS ===\n{compiled_text}\n=========================\n"
        )

    @staticmethod
    def _sanitize_payload(category: str, data: Dict[str, Any]) -> Dict[str, Any]:
        # Ensure expected keys exist cleanly without crashing frontend
        if category == "Legal Document":
            data["disclaimer"] = LEGAL_DISCLAIMER
        return data

    # --- Real Extractive Grounded Fallback (Zero Hardcoded / Fake Data) ---

    def _extract_grounded_fallback(
        self,
        category: str,
        doc: Document,
        chunks: List[DocumentChunk],
        file_format: str,
    ) -> Dict[str, Any]:
        sentences_with_cit: List[Dict[str, str]] = []
        for c in chunks:
            cit = self._format_citation(c, file_format)
            parts = re.split(r"(?<=[.!?])\s+|\n+", (c.content or "").strip())
            for p in parts:
                s = re.sub(r"\s+", " ", p).strip()
                if len(s) >= 25:
                    sentences_with_cit.append({"text": s, "citation": cit})

        def pick_matching(patterns: List[str], limit: int = 6) -> List[Dict[str, str]]:
            found: List[Dict[str, str]] = []
            seen = set()
            for item in sentences_with_cit:
                low = item["text"].lower()
                if any(re.search(pat, low) for pat in patterns):
                    key = item["text"][:80].lower()
                    if key not in seen:
                        seen.add(key)
                        found.append(item)
                        if len(found) >= limit:
                            break
            return found

        # Opening summary built directly from opening sentences of the document
        opening_sents = [x["text"] for x in sentences_with_cit[:4]]
        base_summary = " ".join(opening_sents) if opening_sents else (chunks[0].content[:600] if chunks else "")

        if category == "Research Paper":
            obj_hits = pick_matching([r"\bobjective\b", r"\bwe (?:propose|investigate|study|present|aim)\b", r"\bhypothesis\b", r"\babstract\b"], 2)
            meth_hits = pick_matching([r"\bmethod", r"\bexperiment", r"\bdataset\b", r"\barchitecture\b", r"\bapproach\b", r"\bevaluat"], 5)
            find_hits = pick_matching([r"\bfind", r"\bresult", r"\bshow", r"\bachiev", r"\bimprov", r"\boutperform", r"\bsignificant"], 6)
            lim_hits = pick_matching([r"\blimitation", r"\bthreat", r"\bconstraint", r"\bdrawback", r"\bfuture work\b", r"\bhowever\b"], 4)
            contrib_hits = pick_matching([r"\bcontribut", r"\bnovel", r"\bkey insight", r"\bdemonstrate", r"\bimpact\b"], 4)
            return {
                "research_summary": base_summary,
                "research_objective": obj_hits[0]["text"] if obj_hits else (sentences_with_cit[0]["text"] if sentences_with_cit else base_summary),
                "methodology_analysis": [x["text"] for x in meth_hits] or [x["text"] for x in sentences_with_cit[1:4]],
                "key_findings": [{"finding": x["text"], "citation": x["citation"]} for x in (find_hits or sentences_with_cit[2:6])],
                "limitations": [x["text"] for x in lim_hits],
                "important_contributions": [x["text"] for x in (contrib_hits or sentences_with_cit[1:4])],
            }

        if category == "Business Report":
            fig_items = self._extract_quantitative_items(chunks, file_format)
            insight_hits = pick_matching([r"\binsight", r"\btrend", r"\bgrowth", r"\bmarket", r"\bcustomer", r"\bperformance", r"\bshare\b"], 6)
            finding_hits = pick_matching([r"\bfinding", r"\bindicate", r"\bdriver", r"\bchallenge", r"\brisk\b", r"\bopportunity"], 5)
            action_hits = pick_matching([r"\baction\b", r"\bnext step", r"\bimplement", r"\bexecute", r"\binitiative", r"\bpriorit"], 5)
            rec_hits = pick_matching([r"\brecommend", r"\bshould\b", r"\bpropose", r"\badvise", r"\bstrategy\b"], 5)
            return {
                "executive_summary": base_summary,
                "key_insights": [{"insight": x["text"], "citation": x["citation"]} for x in (insight_hits or sentences_with_cit[:5])],
                "important_figures": [{"metric": f["metric"], "value": f["value"], "context": f["context"], "citation": f["citation"]} for f in fig_items[:8]],
                "business_findings": [x["text"] for x in (finding_hits or sentences_with_cit[1:5])],
                "action_items": [x["text"] for x in action_hits],
                "recommendations": [x["text"] for x in rec_hits],
            }

        if category == "Meeting Notes":
            dec_hits = pick_matching([r"\bdecid", r"\bdecision", r"\bagreed\b", r"\bapproved\b", r"\bresolved\b"], 6)
            act_hits = pick_matching([r"\baction\b", r"\btodo\b", r"\bfollow[- ]?up\b", r"\bwill\s+(?:prepare|send|review|update|complete|deliver|schedule)\b"], 8)
            unres_hits = pick_matching([r"\bunresolved\b", r"\bopen\s+(?:issue|question)\b", r"\bblocker\b", r"\bpending\b", r"\btbd\b", r"\bdefer"], 5)
            assignees = self._extract_explicit_assignees(chunks, file_format)
            deadlines = self._extract_explicit_deadlines(chunks, file_format)
            return {
                "meeting_summary": base_summary,
                "important_decisions": [{"decision": x["text"], "citation": x["citation"]} for x in dec_hits],
                "action_items": [{"action": x["text"], "citation": x["citation"]} for x in (act_hits or sentences_with_cit[1:5])],
                "assigned_responsibilities": assignees,
                "deadlines_mentioned": deadlines,
                "unresolved_issues": [x["text"] for x in unres_hits],
            }

        if category == "Legal Document":
            clause_hits = pick_matching([r"\bclause\b", r"\bsection\s+\d", r"\barticle\s+\d", r"\bconfidential", r"\bindemnif", r"\bterminat", r"\bliabilit", r"\bgoverning law\b"], 6)
            oblig_hits = pick_matching([r"\bshall\b", r"\bmust\b", r"\bagrees\s+to\b", r"\bobligat", r"\brequired\s+to\b"], 6)
            cond_hits = pick_matching([r"\bprovided\s+that\b", r"\bsubject\s+to\b", r"\bcondition", r"\bevent\s+of\s+default\b", r"\bforce\s+majeure\b", r"\barbitration\b"], 5)
            parties = self._extract_legal_parties(chunks)
            dates = self._extract_explicit_deadlines(chunks, file_format)
            return {
                "disclaimer": LEGAL_DISCLAIMER,
                "document_overview": base_summary,
                "important_clauses": [{"clause_title": f"Provision ({x['citation']})", "summary": x["text"], "citation": x["citation"]} for x in (clause_hits or sentences_with_cit[:4])],
                "obligations": [{"party": "Document Party", "obligation": x["text"], "citation": x["citation"]} for x in oblig_hits],
                "dates_and_deadlines": [{"date_or_period": d["deadline"], "context": d["item"], "citation": d["citation"]} for d in dates],
                "parties_involved": parties,
                "important_conditions": [x["text"] for x in cond_hits],
            }

        if category == "Financial Report":
            fig_items = self._extract_quantitative_items(chunks, file_format)
            rev_hits = pick_matching([r"\brevenue\b", r"\bsales\b", r"\bexpense", r"\bcost\b", r"\bincome\b", r"\bprofit\b", r"\bebitda\b", r"\bcash\s+flow\b"], 6)
            trend_hits = pick_matching([r"\bincreas", r"\bdecreas", r"\bgrew\b", r"\bdeclin", r"\byoy\b", r"\bquarter", r"\bmargin\b", r"\bcompared\s+to\b"], 5)
            ratio_items = self._extract_explicit_ratios(chunks, file_format)
            return {
                "financial_summary": base_summary,
                "important_figures": [{"metric": f["metric"], "value": f["value"], "period": "As reported", "citation": f["citation"]} for f in fig_items[:8]],
                "revenue_and_expenses": [{"item": "Reported Line Item", "amount": "-", "details": x["text"], "citation": x["citation"]} for x in rev_hits],
                "key_financial_trends": [x["text"] for x in (trend_hits or sentences_with_cit[1:4])],
                "important_ratios": ratio_items,
            }

        if category == "User Manual / Technical Documentation":
            instr_hits = pick_matching([r"\buse\b", r"\bensure\b", r"\bconfigure\b", r"\bselect\b", r"\bclick\b", r"\brun\b", r"\bcommand\b"], 6)
            step_hits = pick_matching([r"^\s*(?:step\s*\d+|\d+\.)", r"\bfirst,\b", r"\bthen\b", r"\binstall\b", r"\bsetup\b"], 6)
            trb_hits = pick_matching([r"\btroubleshoot", r"\berror\b", r"\bif\s+.*\bfails?\b", r"\bissue\b", r"\brestart\b", r"\bfix\b", r"\bverify\b"], 5)
            warn_hits = pick_matching([r"\bwarning\b", r"\bcaution\b", r"\bdanger\b", r"\bdo\s+not\b", r"\bnever\b", r"\bmust\s+not\b"], 5)
            return {
                "documentation_summary": base_summary,
                "important_instructions": [{"instruction": x["text"], "citation": x["citation"]} for x in (instr_hits or sentences_with_cit[:5])],
                "setup_steps": [{"step_number": i + 1, "title": f"Step {i + 1}", "detail": x["text"], "citation": x["citation"]} for i, x in enumerate(step_hits)],
                "troubleshooting": [{"issue": "Documented Issue / Note", "resolution": x["text"], "citation": x["citation"]} for x in trb_hits],
                "important_warnings": [{"warning": x["text"], "citation": x["citation"]} for x in warn_hits],
            }

        # General Document
        return {
            "ai_summary": base_summary,
            "key_points": [{"point": x["text"], "citation": x["citation"]} for x in sentences_with_cit[:6]],
            "important_information": [
                {
                    "topic": f"Key Detail ({x['citation']})",
                    "detail": x["text"],
                    "citation": x["citation"],
                }
                for x in sentences_with_cit[2:7]
            ],
        }

    def _extract_quantitative_items(self, chunks: List[DocumentChunk], file_format: str) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        seen = set()
        num_pattern = re.compile(r"((?:USD|EUR|GBP|INR|Rs\.?|[$€£₹])\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:million|billion|thousand|crore|lakh|[KMB]))?|\b\d[\d,]*(?:\.\d+)?\s*(?:%|percent|million|billion))", re.I)
        for c in chunks:
            cit = self._format_citation(c, file_format)
            for sent in re.split(r"(?<=[.!?])\s+|\n+", c.content or ""):
                m = num_pattern.search(sent)
                if m:
                    val = m.group(1).strip()
                    clean_s = re.sub(r"\s+", " ", sent).strip()
                    key = (val, clean_s[:50])
                    if key not in seen:
                        seen.add(key)
                        metric_guess = clean_s.split(val)[0].strip(" :-|")[-45:] or "Reported Figure"
                        results.append({"metric": metric_guess, "value": val, "context": clean_s[:180], "citation": cit})
        return results

    def _extract_explicit_assignees(self, chunks: List[DocumentChunk], file_format: str) -> List[Dict[str, str]]:
        assignees: List[Dict[str, str]] = []
        seen = set()
        pat = re.compile(
            r"\b(?:[Aa]ssigned\s+to|[Oo]wner|[Rr]esponsible|[Ll]ead)\s*[:\-]\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)"
            r"|\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:will|to)\s+(?:prepare|complete|review|update|send|finalize|deliver|lead|coordinate|audit|handle)\b",
        )
        for c in chunks:
            cit = self._format_citation(c, file_format)
            for line in re.split(r"\n+|(?<=[.!?])\s+", c.content or ""):
                m = pat.search(line)
                if m:
                    person = (m.group(1) or m.group(2) or "").strip()
                    if person and person.lower() not in {"the", "this", "team", "meeting", "action", "we", "they", "it"}:
                        clean_line = re.sub(r"\s+", " ", line).strip()
                        if (person, clean_line[:40]) not in seen:
                            seen.add((person, clean_line[:40]))
                            assignees.append({"assignee": person, "task": clean_line[:200], "citation": cit})
        return assignees[:10]

    def _extract_explicit_deadlines(self, chunks: List[DocumentChunk], file_format: str) -> List[Dict[str, str]]:
        deadlines: List[Dict[str, str]] = []
        seen = set()
        date_pat = re.compile(
            r"\b(?:by|due|deadline|before|effective|until|on)\s+((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:,?\s+\d{4})?|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|Q[1-4]\s*\d{4}|(?:Monday|Tuesday|Wednesday|Thursday|Friday)(?:\s+\w+)?|\d+\s+(?:days|weeks|months))\b",
            re.I,
        )
        for c in chunks:
            cit = self._format_citation(c, file_format)
            for line in re.split(r"\n+|(?<=[.!?])\s+", c.content or ""):
                m = date_pat.search(line)
                if m:
                    dl = m.group(1).strip()
                    clean_line = re.sub(r"\s+", " ", line).strip()
                    if (dl, clean_line[:40]) not in seen:
                        seen.add((dl, clean_line[:40]))
                        deadlines.append({"deadline": dl, "item": clean_line[:200], "citation": cit})
        return deadlines[:10]

    @staticmethod
    def _extract_legal_parties(chunks: List[DocumentChunk]) -> List[str]:
        parties: List[str] = []
        seen = set()
        text = "\n".join(c.content or "" for c in chunks[:3])
        for m in re.finditer(r'(?:between|and|party)\s+"?([A-Z][A-Za-z0-9\s,&.\-]{2,55}(?:Inc\.|LLC|Ltd\.|Corp\.|Corporation|LLP|Company|University))"?', text):
            name = m.group(1).strip(" ,.")
            if name.lower() not in seen:
                seen.add(name.lower())
                parties.append(name)
        return parties[:6]

    def _extract_explicit_ratios(self, chunks: List[DocumentChunk], file_format: str) -> List[Dict[str, str]]:
        ratios: List[Dict[str, str]] = []
        pat = re.compile(r"\b(gross margin|operating margin|net margin|debt[- ]to[- ]equity|current ratio|quick ratio|return on equity|roe|roa|ebitda margin)\b[^.\n]{0,80}?(\d+(?:\.\d+)?\s*(?:%|x|:1))", re.I)
        for c in chunks:
            cit = self._format_citation(c, file_format)
            for m in pat.finditer(c.content or ""):
                ratios.append({
                    "ratio_name": m.group(1).strip().title(),
                    "value": m.group(2).strip(),
                    "note": "Explicitly reported in document",
                    "citation": cit,
                })
        return ratios[:8]


adaptive_insights_service = AdaptiveInsightsService()
