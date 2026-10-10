"""Synthetic transitions for judge probes.

These cases are not part of the held-out gold metric. Expected labels below
are the labels the frozen rank rule assigns; tests check the rule still
assigns them. They were chosen before any model verifier was run.
"""

from __future__ import annotations

from swrag.types import GoldQuestion
from swrag.verification.v2.examples import Example
from swrag.verification.v2.gold_transition import label_answers
from swrag.verification.v2.transitions import StateView, Transition

ABSTAIN = "I do not know based on the retrieved documents."


def adversarial_examples() -> tuple[Example, ...]:
    cases = (
        _case(
            "longer_worse",
            gold=_gold("Where is the Northport Archive?", ("Northport",), True),
            before="Northport",
            after=(
                "A careful reading of the surrounding civic history suggests the archive "
                "was relocated several times and is now generally associated with the east bank."
            ),
            before_evidence="The Northport Archive is in Northport.",
            after_evidence="The Northport Archive is in Northport.",
        ),
        _case(
            "shorter_better",
            gold=_gold("Where is the Northport Archive?", ("Northport",), True),
            before="It depends on which century of civic history you have in mind, and the east bank is often mentioned.",
            after="Northport",
            before_evidence="The Northport Archive is in Northport.",
            after_evidence="The Northport Archive is in Northport.",
        ),
        _case(
            "fluent_hallucination",
            gold=_gold("What is the archive code?", ("1842",), True),
            before="1842",
            after="The celebrated archive code is certainly 1999, as any careful reader of the notice would conclude.",
            before_evidence="The archive code is 1842.",
            after_evidence="The archive code is 1842.",
        ),
        _case(
            "copies_question",
            gold=_gold("Where is the Northport Archive kept?", ("west vault",), True),
            before="Where is the Northport Archive kept?",
            after="The question asks where the archive is kept, which is a location question.",
            before_evidence="The Northport Archive is kept in the west vault.",
            after_evidence="The Northport Archive is kept in the west vault.",
        ),
        _case(
            "distractor_context",
            gold=_gold("What is the archive code?", ("1842",), True),
            before="1999",
            after="1842",
            before_evidence="A superseded draft mentioned 1999. The archive code is 1842.",
            after_evidence="A superseded draft mentioned 1999. The archive code is 1842.",
        ),
        _case(
            "partial_support",
            gold=_gold("Who founded the Northport Archive?", ("Ada Quill",), True),
            before="The archive was founded in 1842.",
            after="Ada Quill",
            before_evidence="Ada Quill founded the archive in 1842.",
            after_evidence="Ada Quill founded the archive in 1842.",
        ),
        _case(
            "unsupported_number",
            gold=_gold("Who founded the Northport Archive?", ("Ada Quill",), True),
            before="Ada Quill",
            after="The founder is recorded as 1999.",
            before_evidence="Ada Quill founded the archive in 1842.",
            after_evidence="Ada Quill founded the archive in 1842.",
        ),
        _case(
            "correct_abstention",
            gold=_gold("Who is the director of the Northport Archive?", (), False),
            before="Ada Quill",
            after=ABSTAIN,
            before_evidence="Ada Quill founded the archive in 1842.",
            after_evidence="Ada Quill founded the archive in 1842. No director is named.",
        ),
        _case(
            "unnecessary_abstention",
            gold=_gold("Where is the Northport Archive?", ("Northport",), True),
            before="Northport",
            after=ABSTAIN,
            before_evidence="The Northport Archive is in Northport.",
            after_evidence="The Northport Archive is in Northport.",
        ),
        _case(
            "generated_versus_controller_abstention",
            gold=_gold("Who is the director of the Northport Archive?", (), False),
            before=ABSTAIN,
            after=ABSTAIN,
            before_evidence="No director is named.",
            after_evidence="No director is named.",
            before_relation="abstained",
            after_relation="generated",
            before_source="probe",
            after_source="judge",
        ),
        _case(
            "nearly_identical",
            gold=_gold("Where is the Northport Archive?", ("Northport",), True),
            before="Northport",
            after="The answer is Northport.",
            before_evidence="The Northport Archive is in Northport.",
            after_evidence="The Northport Archive is in Northport.",
        ),
        _case(
            "both_wrong",
            gold=_gold("Where is the Northport Archive?", ("Northport",), True),
            before="Eastport",
            after="Southport",
            before_evidence="The Northport Archive is in Northport.",
            after_evidence="The Northport Archive is in Northport.",
        ),
        _case(
            "subtle_degradation",
            gold=_gold("Where is the Northport Archive?", ("Northport",), True),
            before="Northport",
            after="North port city",
            before_evidence="The Northport Archive is in Northport.",
            after_evidence="The Northport Archive is in Northport.",
        ),
        _case(
            "evidence_up_answer_down",
            gold=_gold("Where is the Northport Archive?", ("Northport",), True),
            before="Eastport",
            after="The civic notice describes a long east-bank relocation and a superseded draft.",
            before_evidence="Old draft.",
            after_evidence="The civic notice describes a long east-bank relocation and a superseded draft. The archive is in Northport.",
        ),
        _case(
            "answer_up_score_down",
            gold=_gold("Where is the Northport Archive?", ("Northport",), True),
            before="Eastport",
            after="Northport",
            before_evidence="Unrelated shuttle timetable.",
            after_evidence="The Northport Archive is in Northport.",
            before_score=0.95,
            after_score=0.05,
        ),
        _case(
            "answerable_wrong_to_abstain",
            gold=_gold("Where is the Northport Archive?", ("Northport",), True),
            before="Eastport",
            after=ABSTAIN,
            before_evidence="The Northport Archive is in Northport.",
            after_evidence="The Northport Archive is in Northport.",
        ),
        _case(
            "kept_previous_answer",
            gold=_gold("Where is the Northport Archive?", ("Northport",), True),
            before="Eastport",
            after="Eastport",
            before_evidence="Unrelated shuttle timetable.",
            after_evidence="The civic notice describes a long east-bank relocation and a superseded draft.",
            after_relation="kept_previous",
            after_evidence_relation="widened",
        ),
    )
    return tuple(cases)


def _gold(question: str, answers: tuple[str, ...], answerable: bool) -> GoldQuestion:
    return GoldQuestion(
        question_id="adversarial",
        question=question,
        answerable=answerable,
        answers=answers,
    )


def _case(
    name: str,
    *,
    gold: GoldQuestion,
    before: str,
    after: str,
    before_evidence: str,
    after_evidence: str,
    before_relation: str | None = None,
    after_relation: str | None = "generated",
    before_source: str | None = None,
    after_source: str = "judge",
    before_score: float = 0.4,
    after_score: float = 0.4,
    after_evidence_relation: str = "unchanged",
) -> Example:
    transition = Transition(
        level="attempt",
        question=gold.question,
        before=StateView(
            answer=before,
            chunks=(_chunk(before_evidence, before_score),),
            evidence_known=True,
            answer_relation=before_relation,
            evaluation_source=before_source,
        ),
        after=StateView(
            answer=after,
            chunks=(_chunk(after_evidence, after_score),),
            evidence_known=True,
            answer_relation=after_relation,
            evidence_relation=after_evidence_relation,
            evaluation_source=after_source,
        ),
        action="rewrite",
        executed=True,
        schema_version=2,
        question_id=name,
        corpus_id="adversarial",
        attempt_index=0,
    )
    return Example(
        transition=transition,
        gold_label=label_answers(before, after, gold),
        v1_outcome=None,
        answerable=gold.answerable,
        panel="adversarial",
        split="adversarial",
        source=name,
    )


def _chunk(text: str, score: float) -> dict:
    return {
        "chunk_id": "adv::c000",
        "doc_id": "adv",
        "title": "Notice",
        "text": text,
        "score": score,
    }
