"""Query-rewrite prompt guard. No live API calls."""

from swrag.recovery.rewrite import _REWRITE_PROMPT, guard_rewritten_query


def test_prompt_forbids_abbreviation_expansion() -> None:
    assert "Do not expand abbreviations" in _REWRITE_PROMPT
    assert "DKU" in _REWRITE_PROMPT
    assert "Do not invent institution names" in _REWRITE_PROMPT


def test_guard_rejects_dongkuk_university_for_dku() -> None:
    question = "is there an engineering major at dku"
    rewritten = "Is there an engineering major offered at Dongkuk University (DKU)?"
    assert guard_rewritten_query(question, rewritten) == question


def test_guard_keeps_rewrite_when_institute_is_already_in_the_question() -> None:
    question = "When is the Harbor Institute Library open on Saturday?"
    rewritten = "Harbor Institute Library Saturday hours term time"
    assert guard_rewritten_query(question, rewritten) == rewritten


def test_guard_falls_back_on_empty_rewrite() -> None:
    question = "When does the library close?"
    assert guard_rewritten_query(question, "  ") == question
