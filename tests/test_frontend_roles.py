from frontend.components import _evidence_maturity


def test_evidence_maturity_preserves_provenance_boundaries() -> None:
    assert _evidence_maturity({"created_by": "DEVELOPER_INPUT"}) == "Developer Input"
    assert _evidence_maturity({"created_by": "DETERMINISTIC_GIS"}) == "Deterministic Derived Evidence"
    assert _evidence_maturity({"created_by": "RAG_RETRIEVAL", "source_trust": "AUTHORITATIVE_POLICY"}) == "Observed / Authoritative Evidence"
    assert _evidence_maturity({"created_by": "RAG_RETRIEVAL", "evidence_state": "UNKNOWN"}) == "Confirmation Required"


def test_frontend_role_helpers_do_not_create_decision_fields() -> None:
    assert "score" not in _evidence_maturity({}).casefold()
    assert "decision" not in _evidence_maturity({}).casefold()
