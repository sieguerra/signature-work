from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from swrag.api.app import create_app
from swrag.evaluation.quality_metrics import score_trace, scores_from_labels
from swrag.tracing.tracer import write_trace
from swrag.types import TraceRecord

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "datasets" / "corpus"
CHUNKS = [
    {"chunk_id": "doc::c1", "doc_id": "doc", "title": "Doc", "text": "Pemberley is Darcy's estate.", "score": 0.6},
    {"chunk_id": "doc::c2", "doc_id": "doc", "title": "Doc", "text": "Unrelated.", "score": 0.5},
]


class FakeChat:
    def __init__(self, replies: list[dict]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.prompts.append(kwargs["messages"][1]["content"])
        content = json.dumps(self.replies.pop(0))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=None)


def test_scores_come_from_the_labels() -> None:
    labels = {
        "claims": [
            {"claim": "The estate is Pemberley.", "supported": True, "passage": 1},
            {"claim": "It is in Derbyshire.", "supported": False, "passage": None},
        ],
        "answer_relevance": 5,
        "answer_relevance_reason": "Answers the question directly.",
        "passages": [{"passage": 1, "relevant": True}, {"passage": 2, "relevant": False}],
    }
    scored = scores_from_labels(labels, answer="Pemberley, in Derbyshire.", chunks=CHUNKS)
    assert scored.faithfulness == 0.5
    assert scored.answer_relevance == 1.0
    assert scored.context_relevance == 0.5
    assert scored.claims[0]["chunk_id"] == "doc::c1"
    assert scored.claims[1]["chunk_id"] is None


def test_abstention_has_no_faithfulness_or_relevance_score() -> None:
    labels = {
        "claims": [{"claim": "It does not know.", "supported": True, "passage": None}],
        "answer_relevance": 1,
        "passages": [{"passage": 1, "relevant": True}],
    }
    scored = scores_from_labels(labels, answer="I do not know based on the retrieved documents.", chunks=CHUNKS)
    assert scored.faithfulness is None
    assert scored.answer_relevance is None
    assert scored.context_relevance == 0.5


def test_out_of_range_passage_numbers_are_ignored() -> None:
    labels = {
        "claims": [{"claim": "x", "supported": True, "passage": 9}],
        "answer_relevance": 9,
        "passages": [{"passage": 0, "relevant": True}, {"passage": True, "relevant": True}],
    }
    scored = scores_from_labels(labels, answer="x", chunks=CHUNKS)
    assert scored.claims[0]["chunk_id"] is None
    assert scored.answer_relevance == 1.0
    assert scored.context_relevance == 0.0


def test_recovered_trace_scores_first_try_and_final() -> None:
    reply = {"claims": [], "answer_relevance": 3, "passages": []}
    chat = FakeChat([reply, reply])
    payload = {
        "run_id": "r1",
        "query": "What is Darcy's estate?",
        "answer": "Pemberley.",
        "retrieved_chunks": CHUNKS,
        "previous_answer": "Maybe Longbourn.",
        "previous_retrieved_chunks": CHUNKS[1:],
        "recovery_attempts": [{"action": "expand"}],
    }
    scores = score_trace(payload, client=chat, model="fake")
    assert scores["first"] is not None
    assert "Maybe Longbourn." in chat.prompts[1]
    assert all("gold" not in prompt.lower() for prompt in chat.prompts)


def test_quality_endpoint_scores_saves_and_feeds_the_overview(tmp_path: Path) -> None:
    write_trace(
        TraceRecord(
            run_id="q1",
            timestamp="2026-09-28T06:00:00+00:00",
            query="What is Darcy's estate?",
            retrieved_chunks=(),
            answer="Pemberley.",
            model="gpt",
            embedding_model="fake-hash",
            top_k=2,
        ),
        tmp_path,
    )
    chat = FakeChat(
        [
            {
                "claims": [{"claim": "Pemberley", "supported": True, "passage": None}],
                "answer_relevance": 4,
                "passages": [],
            }
        ]
    )
    app = create_app(corpus_dir=CORPUS, traces_dir=tmp_path)
    app.state.quality_scorer = lambda: (chat, "fake-model")
    with TestClient(app) as client:
        assert client.get("/api/traces/q1/quality").json() == {"quality": None}
        scored = client.post("/api/traces/q1/quality").json()["quality"]
        assert scored["final"]["faithfulness"] == 1.0
        assert scored["final"]["answer_relevance"] == 0.75
        assert scored["model"] == "fake-model"
        assert client.get("/api/traces/q1/quality").json()["quality"]["final"]["faithfulness"] == 1.0
        runs = client.get("/api/eval").json()["runs"]
        assert len(runs) == 1
        assert runs[0]["quality"]["faithfulness"] == 1.0
        assert client.get("/api/traces").json()["traces"][0]["run_id"] == "q1"
        client.delete("/api/traces/q1")
        assert not (tmp_path / "quality" / "q1.quality.json").exists()


def test_quality_endpoint_404s_for_unknown_run(tmp_path: Path) -> None:
    with TestClient(create_app(corpus_dir=CORPUS, traces_dir=tmp_path)) as client:
        assert client.post("/api/traces/nope/quality").status_code == 404
