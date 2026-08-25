"""Dual-corpus retrieval without weakening executable grounding."""

from __future__ import annotations

from backend.knowledge.market_risk_kb import MarketRiskKnowledgeBase
from backend.knowledge.vector_store import Hit
from backend.providers.base import MockDataProvider

from agents.a2a.runtime import AgentNetwork
from agents.contracts import KnowledgeChunk, ToolCatalogue, ToolSpec
from agents.domain_expert_agent import DomainExpertAgent


EXECUTABLE_TEXT = (
    "Historical simulation reads a fixed lookback window of 250 trading days "
    "of daily observations."
)


class RecordingKnowledge:
    def __init__(self, collection: str) -> None:
        self.collection = collection
        self.queries: list[tuple[str, int]] = []

    def retrieve(self, query: str, n_results: int = 3) -> list[dict]:
        self.queries.append((query, n_results))
        if self.collection == "market_risk_kb":
            key_rate = "key-rate" in query
            return [{
                "domain": "market_risk_kb",
                "source": "04_Interest_Rate_Risk",
                "heading": ("5. Key Rate Risk > 5.4 Formula" if key_rate
                            else "4. DV01 and PV01"),
                "text": ("Key Rate DV01 attributes interest-rate sensitivity "
                         "to individual maturity buckets." if key_rate else
                         "DV01 (also called PV01 or BPV) is interest-rate "
                         "sensitivity to a one-basis-point move."),
                "distance": 0.08 if key_rate else 0.12,
                "score": 0.92 if key_rate else 0.88,
                "collection": "market_risk_kb",
                "chunk_id": "market/key-rate" if key_rate else "market/dv01",
                "document_path": "04_Interest_Rate_Risk.md",
                "line_start": 100 if key_rate else 40,
                "line_end": 110 if key_rate else 50,
            }]
        return [{
            "domain": "market_risk",
            "source": "dv01",
            "heading": "Observation window",
            "text": EXECUTABLE_TEXT,
            "distance": 0.1,
            "score": 0.9,
            "collection": "quant_knowledge",
            "chunk_id": "market_risk/dv01::3",
        }]


class OneHitStore:
    def __init__(self) -> None:
        self.queries: list[tuple[str, int, dict | None]] = []

    def query(self, query: str, n_results: int = 3,
              where: dict | None = None) -> list[Hit]:
        self.queries.append((query, n_results, where))
        return [Hit(
            id="market_risk_kb/04_Interest_Rate_Risk.md::0048::key-rate",
            document="DV01, PV01 and Key Rate DV01 measure interest-rate sensitivity.",
            metadata={
                "domain": "market_risk_kb",
                "source": "04_Interest_Rate_Risk",
                "heading": "5. Key Rate Risk > 5.4 Formula",
                "document_path": "04_Interest_Rate_Risk.md",
                "line_start": 480,
                "line_end": 495,
            },
            distance=0.07,
        )]


CATALOGUE = ToolCatalogue(
    tools=[ToolSpec("compute_dv01_tool", "DV01", "risk", executable=True)],
    fields=["observation_date", "rate_percent", "quote_basis"],
    tenors=["y2", "y10", "y30"],
    can_calculate=True,
)


def requirement_payload(**overrides):
    payload = {
        "task_understood": "calculate DV01 for a Treasury portfolio",
        "answerable": True,
        "unanswerable_reason": None,
        "fields": ["observation_date", "rate_percent", "quote_basis"],
        "candidate_fields": ["observation_date", "rate_percent", "quote_basis"],
        "field_notes": [],
        "rows": 250,
        "row_quote": EXECUTABLE_TEXT,
        "row_reason": "The executable corpus states the window.",
        "tenors": ["y2", "y10"],
        "calculation": "compute_dv01_tool",
        "calculation_params": {"confidence_level": None, "horizon_days": None},
        "curve_family": "nominal",
        "open_questions": [],
        "assumptions": [],
        "limitations": [],
        "decision": None,
    }
    payload.update(overrides)
    return payload


def test_market_risk_adapter_preserves_retrieval_provenance():
    store = OneHitStore()
    kb = MarketRiskKnowledgeBase(store=store)

    hits = kb.retrieve("What is DV01?", n_results=3)

    assert store.queries == [("What is DV01?", 3, None)]
    assert "DV01" in hits[0]["text"]
    assert hits[0]["collection"] == "market_risk_kb"
    assert hits[0]["chunk_id"].endswith("::key-rate")
    assert hits[0]["score"] == 0.93
    assert hits[0]["document_path"] == "04_Interest_Rate_Risk.md"
    assert hits[0]["line_start"] == 480


def test_existing_executable_retrieval_remains_authoritative():
    executable = RecordingKnowledge("quant_knowledge")
    expert = DomainExpertAgent(executable)

    chunks = expert.retrieve("historical VaR")

    assert len(executable.queries) == 2
    assert chunks[0].collection == "quant_knowledge"
    assert chunks[0].chunk_id == "market_risk/dv01::3"
    assert EXECUTABLE_TEXT in chunks[0].text


def test_reference_number_cannot_ground_an_executable_window():
    expert = DomainExpertAgent(knowledge=None)
    reference = KnowledgeChunk(
        domain="market_risk_kb", source="11_VaR", heading="Typical windows",
        text="A reference example uses exactly 500 observations.", distance=0.1,
        collection="market_risk_kb", chunk_id="market/var-window")

    built = expert._build(
        requirement_payload(
            rows=500,
            row_quote="A reference example uses exactly 500 observations."),
        [reference], CATALOGUE, requested_rows=None)

    assert built.rows is None
    assert built.row_quote is None
    assert built.grounded is False
    assert any("citation is not in" in warning for warning in built.warnings)


def test_one_domain_turn_uses_both_corpora_with_separate_prompt_roles(monkeypatch):
    executable = RecordingKnowledge("quant_knowledge")
    reference = RecordingKnowledge("market_risk_kb")
    expert = DomainExpertAgent(
        executable, market_risk_knowledge=reference,
        market_risk_n_results=3, max_reference_chunks=4)
    captured: dict[str, str] = {}

    def fake_structured_call(*, system, prompt, **_kwargs):
        captured["system"] = system
        captured["prompt"] = prompt
        return requirement_payload()

    monkeypatch.setattr(
        "agents.domain_expert_agent.structured_call", fake_structured_call)

    requirement, chunks = expert.derive(
        "How do I calculate DV01 for a Treasury portfolio and what data do I need?",
        "calculate DV01 for a Treasury portfolio", CATALOGUE, [], None)

    assert len(reference.queries) == 2
    assert len(executable.queries) == 2
    assert {chunk.collection for chunk in chunks} == {
        "market_risk_kb", "quant_knowledge"}
    assert {c["collection"] for c in requirement.citations} == {
        "market_risk_kb", "quant_knowledge"}
    assert requirement.rows == 250
    assert requirement.grounded is True
    assert "MARKET RISK REFERENCE CONTEXT" in captured["prompt"]
    assert "EXECUTABLE KNOWLEDGE CONTEXT" in captured["prompt"]
    assert captured["prompt"].index("MARKET RISK REFERENCE CONTEXT") < \
        captured["prompt"].index("EXECUTABLE KNOWLEDGE CONTEXT")
    assert "never authorizes an executable number" in captured["system"]


def test_bounded_interpretation_query_surfaces_key_rate_material():
    reference = RecordingKnowledge("market_risk_kb")
    expert = DomainExpertAgent(
        knowledge=None, market_risk_knowledge=reference,
        market_risk_n_results=3, max_reference_chunks=2)

    chunks = expert.retrieve_market_risk(
        "Which maturity is driving my interest-rate risk?")

    assert len(reference.queries) == 2
    assert "key-rate" in reference.queries[1][0]
    assert len(chunks) <= 2
    assert chunks[0].heading == "5. Key Rate Risk > 5.4 Formula"
    assert chunks[0].retrieval_query == reference.queries[1][0]


def test_agent_network_injects_both_process_wide_knowledge_sources():
    executable = RecordingKnowledge("quant_knowledge")
    reference = RecordingKnowledge("market_risk_kb")
    network = AgentNetwork(
        executable, MockDataProvider(), market_risk_knowledge=reference)
    try:
        expert = network._domain_expert_agent
        assert expert.kb is executable
        assert expert.market_risk_kb is reference
        assert len(network.apps) == 3
    finally:
        network.shutdown()
