from automation.portal_common import resolve_candidates


def test_resolve_candidates_known_method_code():
    candidates = resolve_candidates("methods", "ЗЦП")
    assert "ЗЦП" in candidates
    assert any("запроса ценовых предложений" in c for c in candidates)


def test_resolve_candidates_known_priority_code():
    candidates = resolve_candidates("priorities", "ТП")
    assert "ТП" in candidates
    assert any("товаропроизводителей" in c for c in candidates)


def test_resolve_candidates_known_incoterm_code():
    candidates = resolve_candidates("incoterms", "DDP")
    assert "DDP" in candidates
    assert any("Delivered Duty Paid" in c for c in candidates)


def test_resolve_candidates_unknown_code_falls_back_to_code_only():
    candidates = resolve_candidates("methods", "НЕИЗВЕСТНЫЙ_КОД")
    assert candidates == ["НЕИЗВЕСТНЫЙ_КОД"]


def test_resolve_candidates_empty_code():
    assert resolve_candidates("methods", None) == []
    assert resolve_candidates("methods", "") == []
