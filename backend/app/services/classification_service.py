import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from app.core.config import settings

logger = logging.getLogger(__name__)

DOCUMENT_CATEGORIES: List[str] = [
    "Educational Material",
    "Research Paper",
    "Business Report",
    "Meeting Notes",
    "Legal Document",
    "Financial Report",
    "User Manual / Technical Documentation",
    "General Document",
]


class DocumentClassificationService:
    """
    Classifies documents into one of 8 supported categories using extracted text,
    structural headings, and extracted metadata (never filename alone).
    Avoids unnecessary Gemini API calls by resolving clear structural matches
    deterministically and making at most one controlled Gemini request when ambiguous.
    """

    LOW_CONFIDENCE_THRESHOLD = 0.45
    HIGH_CONFIDENCE_SKIP_AI_THRESHOLD = 0.78

    # Weighted signals: (regex_pattern, weight, label)
    CATEGORY_SIGNALS: Dict[str, List[Tuple[str, float, str]]] = {
        "Educational Material": [
            (r"\bchapter\s+\d+\b", 2.0, "chapter marker"),
            (r"\bactivity\s+\d+(?:\.\d+)?\b", 2.2, "textbook activity"),
            (r"\blearning\s+objectives?\b|\bwhat\s+you\s+have\s+learnt\b", 2.5, "learning summary"),
            (r"\bin-?text\s+questions?\b|\bback\s+exercises?\b|\bexercises?\b|\bpractice\s+questions?\b", 2.0, "exercises"),
            (r"\b(?:ncert|textbook|syllabus|curriculum|class\s+(?:ix|x|xi|xii|\d+)|grade\s+\d+|lesson\s+\d+|unit\s+\d+)\b", 2.2, "curriculum reference"),
            (r"\b(?:theorem|corollary|worked\s+example|solved\s+example|homework|assignment)\b", 1.8, "pedagogical block"),
            (r"\b(?:let\s+us\s+understand|remember|try\s+this|think\s+and\s+answer)\b", 1.5, "student prompt"),
        ],
        "Research Paper": [
            (r"(?m)^\s*(?:\d+\.?\s*)?abstract\b|\babstract\s*[:\n]", 3.0, "abstract section"),
            (r"\b(?:methodology|materials\s+and\s+methods|experimental\s+setup)\b", 2.2, "methodology section"),
            (r"\b(?:literature\s+review|related\s+work|prior\s+work)\b", 2.0, "literature review"),
            (r"\b(?:results\s+and\s+discussion|statistical\s+significance|p\s*[<>=]\s*0\.\d+)\b", 2.2, "empirical results"),
            (r"\b(?:et\s+al\.|doi\s*:|arxiv\s*:|peer-?reviewed|hypothesis|ablation\s+study)\b", 2.2, "academic citations/terms"),
            (r"(?m)^\s*(?:\d+\.?\s*)?(?:references|bibliography|acknowledg(?:e)?ments)\b", 2.0, "references section"),
            (r"\b(?:findings\s+suggest|future\s+work|limitations\s+of\s+(?:this|our)\s+study)\b", 1.8, "research discussion"),
        ],
        "Meeting Notes": [
            (r"\b(?:minutes\s+of\s+(?:the\s+)?meeting|meeting\s+(?:notes|minutes|summary|recap))\b", 3.5, "meeting minutes header"),
            (r"\b(?:attendees|participants|present\s*:|absent\s*:|apologies\s*:|chaired\s+by)\b", 2.5, "attendee list"),
            (r"\b(?:agenda\s+items?|meeting\s+date|next\s+meeting|call\s+to\s+order|adjourned)\b", 2.2, "agenda/schedule"),
            (r"\b(?:action\s+items?|decisions?\s+(?:made|agreed)|follow-?ups?|key\s+takeaways)\b", 2.0, "decisions/action items"),
            (r"\b(?:assigned\s+to|owner\s*:|due\s+date\s*:|deadline\s*:|responsible\s+party)\b", 1.8, "ownership/deadlines"),
        ],
        "Legal Document": [
            (r"\b(?:whereas|hereinafter\s+(?:referred\s+to\s+as)?|witnesseth|in\s+witness\s+whereof)\b", 3.2, "legal recitals"),
            (r"\b(?:governing\s+law|jurisdiction|indemnif(?:y|ication)|arbitration|force\s+majeure)\b", 2.5, "legal clauses"),
            (r"\b(?:this\s+agreement|master\s+services\s+agreement|non-?disclosure|confidentiality\s+obligations?)\b", 2.5, "contract agreement"),
            (r"\b(?:party\s+of\s+the\s+first\s+part|licensor|licensee|lessor|lessee|the\s+parties\s+agree)\b", 2.5, "contract parties"),
            (r"\b(?:liability|severability|termination\s+for\s+cause|breach\s+of\s+contract|warranties)\b", 2.0, "legal covenants"),
            (r"\bshall\s+(?:not|be|indemnify|comply|deliver|pay|notify)\b", 1.5, "mandatory legal 'shall'"),
        ],
        "Financial Report": [
            (r"\b(?:balance\s+sheet|income\s+statement|statement\s+of\s+cash\s+flows?|cash\s+flow\s+statement)\b", 3.2, "financial statements"),
            (r"\b(?:ebitda|gross\s+margin|operating\s+margin|net\s+income|net\s+profit|earnings\s+per\s+share|eps)\b", 2.5, "financial metrics"),
            (r"\b(?:total\s+revenue|operating\s+expenses|cost\s+of\s+(?:goods\s+sold|revenue)|cogs|capex)\b", 2.2, "revenue/expense lines"),
            (r"\b(?:assets|liabilities|shareholders?\s*'?\s*equity|fiscal\s+year|fy\s*\d{2,4}|q[1-4]\s+\d{4})\b", 2.0, "accounting/fiscal terms"),
            (r"\b(?:audited|auditor|yoy|year-?over-?year|debt-?to-?equity|current\s+ratio|roe|roa)\b", 1.8, "financial ratios/audit"),
        ],
        "Business Report": [
            (r"\b(?:executive\s+summary|business\s+(?:report|review|overview|plan)|quarterly\s+business\s+review)\b", 2.5, "business report structure"),
            (r"\b(?:market\s+(?:analysis|share|size|trends)|competitive\s+landscape|swot\s+analysis)\b", 2.5, "market analysis"),
            (r"\b(?:kpi|key\s+performance\s+indicators?|roi|return\s+on\s+investment|churn\s+rate|arr|mrr)\b", 2.0, "business KPIs"),
            (r"\b(?:strategic\s+recommendations?|growth\s+strategy|go-?to-?market|stakeholders?|roadmap)\b", 2.0, "strategy/recommendations"),
            (r"\b(?:customer\s+acquisition|pipeline|segment\s+performance|operational\s+efficiency)\b", 1.8, "business operations"),
        ],
        "User Manual / Technical Documentation": [
            (r"\b(?:user\s+manual|installation\s+guide|getting\s+started|quick\s+start|setup\s+steps?)\b", 2.8, "manual/setup heading"),
            (r"\b(?:prerequisites|system\s+requirements|configuration|troubleshooting|faq)\b", 2.2, "tech doc sections"),
            (r"\b(?:step\s+\d+\s*:|command\s+line|cli|api\s+reference|endpoint|parameters?\s*:)\b", 2.0, "procedural/API instructions"),
            (r"\b(?:warning\s*:|caution\s*:|danger\s*:|note\s*:|do\s+not\s+(?:disconnect|power\s+off|modify))\b", 2.2, "safety/operational warnings"),
            (r"\b(?:install|run\s+the\s+command|restart\s+the\s+device|firmware|error\s+code)\b", 1.8, "technical actions"),
        ],
    }

    def get_client(self):
        key = (settings.GEMINI_API_KEY or "").strip()
        if not key or key == "your_gemini_api_key_here":
            return None
        from google import genai
        return genai.Client(api_key=key)

    @staticmethod
    def _normalize_category(raw_cat: Optional[str]) -> str:
        if not raw_cat:
            return "General Document"
        cleaned = raw_cat.strip().lower()
        for valid in DOCUMENT_CATEGORIES:
            if valid.lower() == cleaned:
                return valid
        # Soft matching for slight phrasing variants from AI output
        mapping = {
            "educational": "Educational Material",
            "education": "Educational Material",
            "textbook": "Educational Material",
            "research": "Research Paper",
            "academic paper": "Research Paper",
            "business": "Business Report",
            "meeting": "Meeting Notes",
            "legal": "Legal Document",
            "contract": "Legal Document",
            "financial": "Financial Report",
            "finance": "Financial Report",
            "manual": "User Manual / Technical Documentation",
            "technical documentation": "User Manual / Technical Documentation",
            "user manual": "User Manual / Technical Documentation",
            "general": "General Document",
        }
        for k, v in mapping.items():
            if k in cleaned:
                return v
        return "General Document"

    def _heuristic_score(
        self,
        text_sample: str,
        doc_metadata: Optional[Dict[str, Any]] = None,
        headings: Optional[List[str]] = None,
    ) -> Tuple[str, float, str, float]:
        """
        Scores document content, headings, and metadata against domain signals.
        Returns (top_category, confidence, reason, margin_over_second).
        Never inspects filename.
        """
        combined = text_sample or ""
        headings_text = " \n ".join(headings or [])
        meta_parts = []
        if doc_metadata:
            for k in ("title", "chapter_name", "chapter_number", "subject"):
                if doc_metadata.get(k):
                    meta_parts.append(str(doc_metadata[k]))
        meta_text = " ".join(meta_parts)

        full_text = f"{meta_text}\n{headings_text}\n{combined}"
        if not full_text.strip():
            return "General Document", 0.35, "Insufficient text to classify domain.", 0.0

        scores: Dict[str, float] = {cat: 0.0 for cat in DOCUMENT_CATEGORIES if cat != "General Document"}
        matched_reasons: Dict[str, List[str]] = {cat: [] for cat in scores}

        # Metadata bonuses grounded strictly in extracted document properties
        if doc_metadata:
            if doc_metadata.get("chapter_name") or doc_metadata.get("chapter_number"):
                scores["Educational Material"] += 2.2
                matched_reasons["Educational Material"].append("extracted chapter metadata")
            if doc_metadata.get("subject"):
                scores["Educational Material"] += 1.8
                matched_reasons["Educational Material"].append("extracted academic subject")

        for category, rules in self.CATEGORY_SIGNALS.items():
            for pattern, weight, label in rules:
                matches = re.findall(pattern, full_text, flags=re.IGNORECASE)
                if matches:
                    # First match gets full weight, repeated distinct matches add capped bonus
                    bonus = min(len(matches) - 1, 3) * (weight * 0.25)
                    scores[category] += weight + bonus
                    if label not in matched_reasons[category]:
                        matched_reasons[category].append(label)

        # Extra boost when financial currency/percentage density aligns with financial keywords
        currency_hits = len(re.findall(r"(?:\$|€|£|₹|USD|EUR|INR)\s*\d[\d,]*(?:\.\d+)?|\b\d+(?:\.\d+)?%", combined))
        if currency_hits >= 6 and scores["Financial Report"] > 0:
            scores["Financial Report"] += 1.5
            if "dense financial figures" not in matched_reasons["Financial Report"]:
                matched_reasons["Financial Report"].append("dense financial figures")

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_cat, top_score = ranked[0]
        second_cat, second_score = ranked[1] if len(ranked) > 1 else ("General Document", 0.0)
        distinct_signals = len(matched_reasons[top_cat])

        if top_score < 2.2 or (distinct_signals < 2 and top_score < 3.2):
            return (
                "General Document",
                0.40,
                "No strong category-specific structural signals detected; classified as General Document.",
                0.0,
            )

        margin = top_score - second_score
        # Normalize confidence cleanly into [0.45, 0.96]
        raw_conf = 0.45 + min(top_score / 12.0, 0.35) + min(margin / 8.0, 0.16)
        if distinct_signals == 1:
            raw_conf = min(raw_conf, 0.68)
        confidence = round(max(0.45, min(0.96, raw_conf)), 2)

        reasons_list = matched_reasons[top_cat][:4]
        reason = f"Detected {', '.join(reasons_list)} in extracted content."
        return top_cat, confidence, reason, margin

    def classify_document(
        self,
        text_sample: str,
        doc_metadata: Optional[Dict[str, Any]] = None,
        headings: Optional[List[str]] = None,
        use_ai: bool = True,
    ) -> Dict[str, Any]:
        """
        Determines document category and confidence from extracted content and metadata.
        Makes at most one controlled Gemini call only when deterministic signals are ambiguous.
        """
        # Prepare balanced excerpt (opening + middle snippet) without filename
        excerpt = (text_sample or "").strip()
        if len(excerpt) > 5000:
            excerpt = excerpt[:3500] + "\n...\n" + excerpt[-1200:]

        h_cat, h_conf, h_reason, margin = self._heuristic_score(
            text_sample=text_sample,
            doc_metadata=doc_metadata,
            headings=headings,
        )

        # Skip Gemini if heuristic evidence is already decisive (saves quota!)
        if h_cat != "General Document" and h_conf >= self.HIGH_CONFIDENCE_SKIP_AI_THRESHOLD and margin >= 1.5:
            return {
                "category": h_cat,
                "confidence": h_conf,
                "source": "heuristic",
                "reason": h_reason,
            }

        # Controlled single AI classification request when ambiguous
        if use_ai and excerpt:
            client = self.get_client()
            if client:
                ai_result = self._classify_with_gemini_once(
                    client=client,
                    excerpt=excerpt[:3500],
                    headings=headings or [],
                    doc_metadata=doc_metadata or {},
                )
                if ai_result is not None:
                    ai_cat = ai_result["category"]
                    ai_conf = ai_result["confidence"]
                    if ai_conf < self.LOW_CONFIDENCE_THRESHOLD:
                        return {
                            "category": "General Document",
                            "confidence": ai_conf,
                            "source": "ai",
                            "reason": f"Low classification confidence ({ai_conf:.2f}); defaulted to General Document.",
                        }
                    return {
                        "category": ai_cat,
                        "confidence": ai_conf,
                        "source": "ai",
                        "reason": ai_result["reason"],
                    }

        # Fallback to deterministic result, applying low-confidence rule
        if h_conf < self.LOW_CONFIDENCE_THRESHOLD:
            return {
                "category": "General Document",
                "confidence": h_conf,
                "source": "heuristic",
                "reason": h_reason,
            }

        return {
            "category": h_cat,
            "confidence": h_conf,
            "source": "heuristic",
            "reason": h_reason,
        }

    def _classify_with_gemini_once(
        self,
        client: Any,
        excerpt: str,
        headings: List[str],
        doc_metadata: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        categories_str = "\n".join(f"- {c}" for c in DOCUMENT_CATEGORIES)
        headings_str = ", ".join(headings[:15]) if headings else "None identified"
        meta_str = ", ".join(
            f"{k}: {doc_metadata[k]}"
            for k in ("title", "chapter_name", "subject", "author")
            if doc_metadata.get(k)
        ) or "None"

        prompt = (
            "Classify the uploaded document into EXACTLY ONE of these categories based ONLY on its content, "
            "structure, headings, and metadata (do NOT guess from filenames).\n\n"
            f"Allowed Categories:\n{categories_str}\n\n"
            f"Extracted Metadata: {meta_str}\n"
            f"Headings: {headings_str}\n\n"
            f"=== DOCUMENT EXCERPT ===\n{excerpt}\n========================\n\n"
            "If the document lacks clear domain signals or confidence is low, choose 'General Document'.\n"
            'Return STRICT JSON ONLY:\n'
            '{"category": "<exact category name>", "confidence": 0.85, "reason": "<concise 1-sentence reason>"}'
        )

        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                max_output_tokens=256,
                temperature=0.0,
            )
            raw_model = (settings.GEMINI_MODEL or "gemini-3.5-flash").replace("models/", "")
            response = client.models.generate_content(
                model=raw_model,
                contents=prompt,
                config=config,
            )
            if response and response.text:
                cleaned = response.text.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                elif cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                parsed = json.loads(cleaned.strip())
                cat = self._normalize_category(parsed.get("category"))
                conf = float(parsed.get("confidence", 0.5))
                conf = round(max(0.0, min(1.0, conf)), 2)
                reason = str(parsed.get("reason") or "Classified from document content.").strip()
                return {"category": cat, "confidence": conf, "reason": reason}
        except Exception as e:
            logger.warning(f"Controlled AI document classification skipped/failed ({type(e).__name__}: {e})")
        return None


classification_service = DocumentClassificationService()
