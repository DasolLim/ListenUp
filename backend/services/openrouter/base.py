"""Enhanced (cultural) translation: translation + register + slang notes.

OpenRouter LLM behind a strict-JSON contract. Never on the live-caption
critical path (INTRODUCTION §5 progressive enhancement).
"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class SlangNote:
    phrase: str
    meaning: str
    cultural_context: str = ""
    equivalent: str = ""
    # True when the slang KB supplied a definition for this phrase, rather than
    # the model recalling one. An ungrounded note is the model's memory, which
    # is fixed at its training cutoff — so it is right about established slang
    # and confidently wrong about anything coined since.
    grounded: bool = False
    # The same fact in the vocabulary `/genz/explain` already uses, so both
    # surfaces describe trust identically and the client needs one renderer.
    # Derived from `grounded` at a single write site (`_mark_grounding`); the two
    # are never set independently and a test pins that they cannot disagree.
    confidence: str = "low"


@dataclass(frozen=True)
class EnhancedTranslation:
    translation: str
    register: str  # e.g. "casual", "formal", "slang-heavy"
    slang_notes: list[SlangNote] = field(default_factory=list)
    cached: bool = False
    model: str = ""
    tokens: int = 0  # total tokens billed (cost audit)

    def to_dict(self) -> dict:
        return asdict(self)


class EnhancedTranslationService(ABC):
    @abstractmethod
    async def translate(
        self, text: str, target_lang: str
    ) -> EnhancedTranslation | None:
        """None = LLM unavailable/unparseable after retry — callers must treat
        the fast Google translation as the final answer."""


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_llm_json(raw: str) -> dict | None:
    """Defensive parse: strip code fences/prose, extract the first balanced
    JSON object, tolerate trailing junk. Returns None if hopeless."""
    text = _FENCE.sub("", raw.strip())
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(text[start:], start):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
        elif ch == '"' and not escaped:
            in_string = not in_string
        elif not in_string:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start : i + 1])
                        return parsed if isinstance(parsed, dict) else None
                    except json.JSONDecodeError:
                        return None
    return None


def coerce_enhanced(data: dict, model: str, tokens: int) -> EnhancedTranslation | None:
    """Validate/coerce the LLM dict into our schema; None if unusable."""
    translation = data.get("translation")
    if not isinstance(translation, str) or not translation.strip():
        return None
    notes = []
    for item in data.get("slang_notes") or []:
        if isinstance(item, dict) and item.get("phrase") and item.get("meaning"):
            notes.append(
                SlangNote(
                    phrase=str(item["phrase"]),
                    meaning=str(item["meaning"]),
                    cultural_context=str(item.get("cultural_context") or ""),
                    equivalent=str(item.get("equivalent") or ""),
                )
            )
    return EnhancedTranslation(
        translation=translation.strip(),
        register=str(data.get("register") or "unknown"),
        slang_notes=notes,
        model=model,
        tokens=tokens,
    )
