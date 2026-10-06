"""Runtime-only evidence check used by the gap-aware recovery policy.

The labels describe the chunks in hand after a bounded search. They do not
claim the rest of the corpus was proved empty. Uncertain cases stop. That
fallback was chosen before the Phase 8C evaluation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CONFLICT = "CONFLICT"
NEIGHBOR_FACT = "NEIGHBOR_FACT"
LIKELY_CORPUS_GAP = "LIKELY_CORPUS_GAP"
LIKELY_QUERY_MISMATCH = "LIKELY_QUERY_MISMATCH"
UNCERTAIN = "UNCERTAIN"

# Frozen before holdout scoring. Uncertain evidence does not earn another rewrite.
UNCERTAIN_FALLBACK = "safe_stop"
DECISION_SOURCE = "deterministic_b1"

_STOP = frozenset(
    """
    what when where which who whom whose how does did do the a an of for to and
    or is are was were be been being in on at by from with per its own not this
    that these those into over than then also only
    """.split()
)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_VERSION_ASK = re.compile(r"\b(?:current|latest|now)\b", re.IGNORECASE)
_PHONE = re.compile(r"\b\d{3}-\d{4}\b|\b\d{4}-\d{7,8}\b|\(\d{4}\)\s*\d{4}-\d{4}")
_DATE = re.compile(
    r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\b",
    re.IGNORECASE,
)
_RANGE = re.compile(r"\b\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\b")
_UNIT = re.compile(
    r"\b\d+(?:\.\d+)?\s+(?:reed tokens|leaf tokens|marks|minutes|million gallons|harbor credits|mg/L)\b",
    re.IGNORECASE,
)
_OMISSION = re.compile(
    r"omitted(?:\s+on purpose)?|not listed|does not list|does not publish|"
    r"does not quote|are not listed|is not listed|no closing time is printed|"
    r"no [\w\s-]{0,40} is printed",
    re.IGNORECASE,
)
_DENIAL = re.compile(r"not printed here|only to say|is not answered", re.IGNORECASE)
_PROPER = re.compile(r"\b(?:[A-Z]{2,}|[A-Z][a-z]+)(?:\s+(?:[A-Z]{2,}|[A-Z][a-z]+))+\b")
_NOT_ENTITY = re.compile(r"\b(?:is not|not the|not a)\b\s+([^.]{0,80})")
_TOKEN = re.compile(r"[a-z0-9]+")

_PHONE_ASK = frozenset({"phone", "telephone", "number"})
_DATE_ASK = frozenset({"when", "date", "opener", "begin", "begins", "reopen"})
_HOUR_ASK = frozenset({"hours", "hour", "time", "open", "opens", "close", "closes", "saturday", "sunday"})
_UNIT_ASK = frozenset(
    {"headway", "minutes", "minute", "levy", "hire", "rental", "fee", "tokens", "fare", "price", "capacity", "cost"}
)


@dataclass(frozen=True)
class GapAssessment:
    """What the bounded evidence supports doing next. Not a corpus proof."""

    label: str
    reason: str
    excerpt: str = ""

    @property
    def allows_rewrite(self) -> bool:
        return self.label == LIKELY_QUERY_MISMATCH

    def as_parameters(self, *, forced_stop: bool) -> dict[str, object]:
        return {
            "recovery_opportunity": self.label,
            "stop_reason": self.reason if not forced_stop else (
                "expand did not repair the failure; this policy stops instead of rewriting"
            ),
            "gap_signal": self.label == LIKELY_CORPUS_GAP,
            "conflict_signal": self.label == CONFLICT,
            "neighbor_signal": self.label == NEIGHBOR_FACT,
            "decision_source": DECISION_SOURCE,
            "safe_answer": safe_abstention(self, forced_stop=forced_stop),
            "uncertain_fallback": UNCERTAIN_FALLBACK,
        }


def assess_evidence(question: str, evidence_texts: tuple[str, ...] | list[str]) -> GapAssessment:
    """Classify the chunks already retrieved. Never reads offline labels."""
    chunks = [text for text in evidence_texts if text and text.strip()]
    if _conflict(question, chunks):
        return GapAssessment(
            CONFLICT,
            "the retrieved sources give more than one value and the question does not choose one",
        )
    excerpt = _omission_excerpt(question, chunks)
    if excerpt:
        return GapAssessment(
            LIKELY_CORPUS_GAP,
            "the retrieved sources say the requested information is not provided",
            excerpt,
        )
    if _neighbor(question, chunks):
        return GapAssessment(
            NEIGHBOR_FACT,
            "the retrieved figure is about a different entity than the question asks",
        )
    if _denial_cluster(question, chunks):
        return GapAssessment(
            LIKELY_QUERY_MISMATCH,
            "the top retrieved text mentions the question only to say that card does not contain it",
        )
    return GapAssessment(
        UNCERTAIN,
        "recovery searched the configured evidence budget and did not find sufficient support",
    )


def blocking_assessment(
    question: str,
    answer: str,
    evidence_texts: tuple[str, ...] | list[str],
) -> GapAssessment | None:
    """Return an assessment when a substantive answer should be replaced by a stop.

    A refusal is already a stop. Query-mismatch and uncertainty do not throw
    away an answer the judge accepted; conflict and neighbor-fact do.
    """
    if _is_refusal(answer):
        return None
    assessment = assess_evidence(question, list(evidence_texts))
    if assessment.label == CONFLICT and _mentions_exactly_one(answer, _contested_values(question, list(evidence_texts))):
        return assessment
    if assessment.label == NEIGHBOR_FACT and _repeats_neighbor_value(answer, question, list(evidence_texts)):
        return assessment
    return None


_USER_STOP = (
    "I do not know based on the retrieved documents. "
    "I couldn't find sufficient support for that answer in the available sources."
)


def safe_abstention(assessment: GapAssessment, *, forced_stop: bool = False) -> str:
    """The answer shown to the user. The diagnosis stays on the trace.

    A conflict label is not asserted in this sentence. Phase 8C sometimes
    stopped safely while naming the wrong reason, so the answer only says
    that bounded search did not find sufficient support.
    """
    base = "I do not know based on the retrieved documents."
    if assessment.label == LIKELY_CORPUS_GAP and assessment.excerpt and not forced_stop:
        return base + " The retrieved sources say: " + assessment.excerpt
    if assessment.label == NEIGHBOR_FACT and not forced_stop:
        return (
            base
            + " The closest figure in the retrieved sources is about a different entity than the question asks."
        )
    return _USER_STOP


def _contested_values(question: str, chunks: list[str]) -> set[str]:
    blob = "\n".join(chunks)
    asks = set(_TOKEN.findall(question.lower()))
    found: set[str] = set()
    if asks & _PHONE_ASK:
        found |= _distinct(_PHONE, blob)
    if asks & _DATE_ASK:
        found |= _distinct(_DATE, blob)
    if asks & _HOUR_ASK:
        found |= _distinct(_RANGE, blob)
    if asks & _UNIT_ASK:
        found |= _distinct(_UNIT, blob)
    return found


def _mentions_exactly_one(answer: str, values: set[str]) -> bool:
    if len(values) < 2:
        return False
    folded = answer.lower()
    present = [value for value in values if value.lower() in folded]
    return len(present) == 1


def _repeats_neighbor_value(answer: str, question: str, chunks: list[str]) -> bool:
    folded = answer.lower()
    for chunk in chunks:
        if not _is_neighbor_chunk(question, chunk):
            continue
        for value in _distinct(_PHONE, chunk) | _distinct(_RANGE, chunk) | _distinct(_UNIT, chunk):
            if value.lower() in folded:
                return True
    return False


def _is_neighbor_chunk(question: str, chunk: str) -> bool:
    if not (_UNIT.search(chunk) or _RANGE.search(chunk) or _PHONE.search(chunk)):
        return False
    phrases = _PROPER.findall(question)
    denial = _NOT_ENTITY.search(chunk)
    if denial and phrases and any(phrase in denial.group(1) for phrase in phrases):
        return True
    return bool(phrases) and not any(phrase in chunk for phrase in phrases) and bool(_PROPER.findall(chunk))


def _conflict(question: str, chunks: list[str]) -> bool:
    if _VERSION_ASK.search(question) or _YEAR.search(question):
        return False
    blob = "\n".join(chunks)
    asks = set(_TOKEN.findall(question.lower()))
    if asks & _PHONE_ASK and len(_distinct(_PHONE, blob)) >= 2:
        return True
    if asks & _DATE_ASK and len(_distinct(_DATE, blob)) >= 2:
        return True
    if asks & _HOUR_ASK and len(_distinct(_RANGE, blob)) >= 2 and _YEAR.search(blob):
        return True
    if asks & _UNIT_ASK and len(_distinct(_UNIT, blob)) >= 2 and _YEAR.search(blob):
        return True
    return False


def _neighbor(question: str, chunks: list[str]) -> bool:
    return any(_is_neighbor_chunk(question, chunk) for chunk in chunks)


def _omission_excerpt(question: str, chunks: list[str]) -> str:
    wanted = set(_content(question))
    for chunk in chunks:
        match = _OMISSION.search(chunk)
        if not match:
            continue
        sentence = _sentence_around(chunk, match.start())
        if wanted & set(_content(sentence)):
            return " ".join(sentence.split())[:240]
    return ""


def _denial_cluster(question: str, chunks: list[str]) -> bool:
    wanted = set(_content(question))
    hits = 0
    for chunk in chunks[:4]:
        if _DENIAL.search(chunk) and wanted & set(_content(chunk)):
            hits += 1
    return hits >= 3


def _distinct(pattern: re.Pattern[str], text: str) -> set[str]:
    return {" ".join(match.group(0).lower().split()) for match in pattern.finditer(text)}


def _content(text: str) -> list[str]:
    return [token for token in _TOKEN.findall(text.lower()) if len(token) >= 4 and token not in _STOP]


def _sentence_around(text: str, index: int) -> str:
    start = text.rfind(".", 0, index)
    end = text.find(".", index)
    left = 0 if start < 0 else start + 1
    right = len(text) if end < 0 else end + 1
    return text[left:right].strip()


def _is_refusal(answer: str) -> bool:
    return answer.strip().lower().startswith("i do not know")
