import re
from typing import Optional


class TextCleaner:
    """
    Handles normalization, cleaning, and sanitization of text extracted from PDF documents.
    Preserves meaningful paragraphs, headings, mathematical notation, and punctuation
    while eliminating extraction artifacts, control characters, and line-break hyphenations.
    """

    # Characters that should be converted to a space (page breaks, vertical tabs, form feeds)
    _SPACE_CONTROL_CHARS = re.compile(r"[\x0b\x0c\r]")

    # Non-printable control characters and zero-width artifacts to remove entirely
    _REMOVE_CONTROL_CHARS = re.compile(r"[\x00\x01-\x08\x0e-\x1f\x7f\xad\ufeff]")

    # Word broken by line hyphenation: e.g. "com-\nputer" -> "computer"
    _HYPHENATION_PATTERN = re.compile(r"(\b[a-zA-Z]{2,})-\n\s*([a-zA-Z]{2,}\b)")

    # Multiple horizontal whitespaces (spaces and tabs, but not newlines)
    _HORIZONTAL_WHITESPACE_PATTERN = re.compile(r"[^\S\n\r]+")

    # 3 or more consecutive newlines (collapse to 2 for clean paragraph break)
    _EXCESSIVE_NEWLINES_PATTERN = re.compile(r"\n{3,}")

    @classmethod
    def clean(cls, text: Optional[str]) -> str:
        """
        Normalize and sanitize extracted text.
        Returns a clean string with preserved structural paragraphs.
        """
        if not text:
            return ""

        # 1. Normalize line endings to standard Unix newline
        normalized = text.replace("\r\n", "\n")

        # 2. Convert form feeds / vertical tabs to spaces (page boundaries)
        normalized = cls._SPACE_CONTROL_CHARS.sub(" ", normalized)

        # 3. Remove non-printable control characters and soft hyphens
        normalized = cls._REMOVE_CONTROL_CHARS.sub("", normalized)

        # 4. De-hyphenate words split across line breaks (e.g. "re-\nsponsibility" -> "responsibility")
        normalized = cls._HYPHENATION_PATTERN.sub(r"\1\2", normalized)

        # 5. Collapse multiple horizontal spaces and tabs into a single space
        normalized = cls._HORIZONTAL_WHITESPACE_PATTERN.sub(" ", normalized)

        # 6. Trim trailing whitespace from each line while keeping structural line breaks
        lines = [line.strip() for line in normalized.split("\n")]
        normalized = "\n".join(lines)

        # 7. Normalize excessive blank lines (3+ newlines -> 2 newlines for paragraph separation)
        normalized = cls._EXCESSIVE_NEWLINES_PATTERN.sub("\n\n", normalized)

        return normalized.strip()

    @classmethod
    def is_meaningful_text(cls, text: Optional[str], min_chars: int = 15) -> bool:
        """
        Check if the text contains meaningful content rather than just headers/page numbers/noise.
        """
        if not text:
            return False
        # Count alphanumeric characters
        alnum_chars = sum(1 for c in text if c.isalnum())
        return alnum_chars >= min_chars
