from datetime import date, datetime

import pytest

from twlab.master import (
    AmbiguousSymbol, OverlappingSegment, SecurityMaster, SecurityVersion, TerminalEvent, UnknownSymbol,
    classify_coverage,
)
from twlab.timeutil import TAIPEI


def R(y, m, d):
    return datetime(y, m, d, 18, 0, tzinfo=TAIPEI)


def sv(**kw):
    base = dict(issuer_id="I", name_zh="名", market="TWSE", board="main", instrument_type="ordinary_equity",
                valid_to=None, source_id="test", recorded_at=R(2020, 1, 1))
    base.update(kw)
    return SecurityVersion(**base)


def test_uni03_reused_symbol_does_not_concatenate_histories():
    m = SecurityMaster()
    m.add(sv(security_id="SEC-A", issuer_id="A", symbol="1234", valid_from=date(2010, 1, 4),
             valid_to=date(2018, 6, 1), recorded_at=R(2010, 1, 4)))
    m.add(sv(security_id="SEC-B", issuer_id="B", symbol="1234", valid_from=date(2020, 3, 2), recorded_at=R(2020, 3, 2)))
    assert m.resolve_symbol("1234", as_of=date(2015, 5, 5)).security_id == "SEC-A"
    assert m.resolve_symbol("1234", as_of=date(2021, 5, 5)).security_id == "SEC-B"
    with pytest.raises(UnknownSymbol):
        m.resolve_symbol("1234", as_of=date(2019, 1, 1))
    assert [v.security_id for v in m.versions_of("SEC-A")] == ["SEC-A"]


def test_uni02_market_change_keeps_identity():
    m = SecurityMaster()
    m.add(sv(security_id="SEC-Y", symbol="5555", market="TPEX", valid_from=date(2015, 1, 5), recorded_at=R(2015, 1, 5)))
    m.change_segment("SEC-Y", new=sv(security_id="SEC-Y", symbol="5555", market="TWSE", valid_from=date(2022, 3, 1),
                                      recorded_at=R(2022, 2, 20)), recorded_at=R(2022, 2, 20), source_id="S01")
    before = m.resolve_symbol("5555", as_of=date(2021, 6, 1))
    after = m.resolve_symbol("5555", as_of=date(2023, 6, 1))
    assert before.security_id == after.security_id == "SEC-Y"
    assert before.market == "TPEX" and after.market == "TWSE"
    # antes de registrarse el cambio, el segmento antiguo seguía abierto
    assert m.resolve_symbol("5555", as_of=date(2023, 6, 1), known_at=R(2022, 1, 1)).market == "TPEX"


def test_uni01_delisted_security_stays_in_history():
    m = SecurityMaster()
    m.add(sv(security_id="SEC-X", symbol="2867", valid_from=date(2019, 1, 2), recorded_at=R(2019, 1, 2)))
    m.close_version("SEC-X", valid_to=date(2026, 9, 1), recorded_at=R(2026, 8, 20), source_id="S01:suspendListing",
                    terminal=TerminalEvent("SEC-X", "delisting", date(2026, 9, 1), R(2026, 8, 20), "S01:suspendListing"))
    assert any(v.security_id == "SEC-X" for v in m.universe(as_of=date(2026, 8, 25), known_at=R(2026, 8, 10)))
    assert any(v.security_id == "SEC-X" for v in m.universe(as_of=date(2026, 8, 25)))
    assert not any(v.security_id == "SEC-X" for v in m.universe(as_of=date(2026, 9, 2)))
    assert m.terminal_event("SEC-X").kind == "delisting"
    assert m.terminal_event("SEC-X", known_at=R(2026, 8, 10)) is None
    assert len(m.versions_of("SEC-X")) == 2  # nada se borra


def test_r01_06_overlapping_segments_are_rejected_and_closed_segments_do_not_resurrect():
    m = SecurityMaster()
    m.add(sv(security_id="A", symbol="1111", valid_from=date(2020, 1, 1)))
    with pytest.raises(OverlappingSegment):
        m.add(sv(security_id="A", symbol="2222", valid_from=date(2022, 1, 1), recorded_at=R(2022, 1, 1)))
    m.change_segment("A", new=sv(security_id="A", symbol="2222", valid_from=date(2022, 1, 1), recorded_at=R(2022, 1, 1)),
                     recorded_at=R(2022, 1, 1), source_id="s")
    m.close_version("A", valid_to=date(2023, 1, 1), recorded_at=R(2022, 12, 1), source_id="s")
    assert m.universe(as_of=date(2024, 1, 1)) == []
    with pytest.raises(UnknownSymbol):
        m.resolve_symbol("1111", as_of=date(2024, 1, 1))
    assert m.resolve_symbol("1111", as_of=date(2021, 6, 1)).symbol == "1111"


def test_r02_03_no_overlap_in_historical_views_either():
    m = SecurityMaster()
    m.add(sv(security_id="A", symbol="1111", valid_from=date(2020, 1, 1)))
    m.close_version("A", valid_to=date(2022, 1, 1), recorded_at=R(2022, 1, 1), source_id="s")
    # una fila registrada en 2021 abriría 2222 cuando, para quien consultaba en 2021, 1111 seguía abierto
    with pytest.raises(OverlappingSegment):
        m.add(sv(security_id="A", symbol="2222", valid_from=date(2022, 1, 1), recorded_at=R(2021, 1, 1)))
    m.add(sv(security_id="A", symbol="2222", valid_from=date(2022, 1, 1), recorded_at=R(2022, 1, 1)))
    for known in (R(2021, 6, 1), R(2022, 6, 1), None):
        covering = [v for v in m._effective(known) if v.security_id == "A" and v.covers(date(2023, 1, 1))]
        assert len(covering) <= 1, known


def test_r03_07_no_overlap_in_any_intermediate_historical_view():
    m = SecurityMaster()
    for recorded, end in [(2020, 2021), (2022, 2023), (2024, 2021)]:
        m.add(sv(security_id="A", symbol="1111", valid_from=date(2020, 1, 1), valid_to=date(end, 1, 1), recorded_at=R(recorded, 1, 1)))
    # visto en 2022-06, 1111 cubre hasta 2023: un 2222 desde 2021 registrado en 2021 solaparía en esa vista intermedia
    with pytest.raises(OverlappingSegment):
        m.add(sv(security_id="A", symbol="2222", valid_from=date(2021, 1, 1), recorded_at=R(2021, 1, 1)))
    m.add(sv(security_id="A", symbol="2222", valid_from=date(2023, 1, 1), recorded_at=R(2025, 1, 1)))
    for known in (R(2020, 6, 1), R(2021, 6, 1), R(2022, 6, 1), R(2024, 6, 1), R(2025, 6, 1), None):
        covering = [v for v in m._effective(known) if v.security_id == "A" and v.covers(date(2022, 7, 1))]
        assert len(covering) <= 1, known


def test_r03_16_change_segment_does_not_extend_an_already_closed_segment():
    m = SecurityMaster()
    m.add(sv(security_id="A", symbol="1111", valid_from=date(2020, 1, 1)))
    m.close_version("A", valid_to=date(2021, 1, 1), recorded_at=R(2021, 1, 1), source_id="s")
    assert m.universe(as_of=date(2022, 1, 1)) == []
    with pytest.raises(ValueError):
        m.change_segment("A", new=sv(security_id="A", symbol="2222", valid_from=date(2023, 1, 1), recorded_at=R(2023, 1, 1)),
                         recorded_at=R(2023, 1, 1), source_id="s")
    assert m.universe(as_of=date(2022, 1, 1)) == []
    # después de un hueco se usa add(); si el nuevo segmento empieza exactamente al cierre, change_segment vale
    m.add(sv(security_id="A", symbol="2222", valid_from=date(2023, 1, 1), recorded_at=R(2023, 1, 1)))
    assert m.universe(as_of=date(2022, 1, 1)) == [] and m.resolve_symbol("2222", as_of=date(2024, 1, 1)).security_id == "A"


def test_r04_12_same_key_cannot_rewrite_known_history():
    m = SecurityMaster()
    args = dict(security_id="A", valid_from=date(2020, 1, 1), recorded_at=R(2020, 1, 1))
    m.add(sv(symbol="1111", **args))
    before = m.universe(as_of=date(2020, 6, 1), known_at=R(2020, 6, 1))
    with pytest.raises(ValueError):
        m.add(sv(symbol="2222", **args))
    assert m.universe(as_of=date(2020, 6, 1), known_at=R(2020, 6, 1)) == before
    m.add(sv(symbol="1111", **args))          # la misma fila repetida es inocua
    assert len(m.versions_of("A")) == 2 and m.resolve_symbol("1111", as_of=date(2020, 6, 1)).symbol == "1111"


def test_r02_12_change_segment_is_atomic():
    m = SecurityMaster()
    m.add(sv(security_id="A", symbol="1111", valid_from=date(2020, 1, 1)))
    before = m.versions_of("A")
    bad = sv(security_id="A", symbol="2222", valid_from=date(2022, 1, 1), valid_to=date(2021, 1, 1), recorded_at=R(2022, 1, 1))
    with pytest.raises(ValueError):
        m.change_segment("A", new=bad, recorded_at=R(2022, 1, 1), source_id="s")
    assert m.versions_of("A") == before
    with pytest.raises(ValueError):
        m.change_segment("A", new=sv(security_id="B", symbol="2222", valid_from=date(2022, 1, 1)), recorded_at=R(2022, 1, 1), source_id="s")
    with pytest.raises(ValueError):
        m.change_segment("A", new=sv(security_id="A", symbol="2222", valid_from=date(2019, 1, 1)), recorded_at=R(2022, 1, 1), source_id="s")
    assert m.versions_of("A") == before


def test_r01_07_terminal_event_revisions_are_versioned():
    m = SecurityMaster()
    m.add(sv(security_id="A", symbol="1111", valid_from=date(2020, 1, 1)))
    for day, end in [(1, 10), (5, 20)]:
        ev = TerminalEvent("A", "delisting", date(2026, 9, end), R(2026, 9, day), "s")
        m.close_version("A", valid_to=ev.effective, recorded_at=ev.recorded_at, source_id="s", terminal=ev)
    assert m.terminal_event("A", known_at=R(2026, 9, 3)).effective == date(2026, 9, 10)
    assert m.terminal_event("A").effective == date(2026, 9, 20)
    assert len(m.terminal_events("A")) == 2


def test_superseding_row_cannot_predate_the_row_it_supersedes():
    m = SecurityMaster()
    m.add(sv(security_id="A", symbol="1111", valid_from=date(2020, 1, 1), recorded_at=R(2021, 1, 1)))
    with pytest.raises(ValueError):
        m.add(sv(security_id="A", symbol="1111", valid_from=date(2020, 1, 1), valid_to=date(2022, 1, 1),
                 recorded_at=R(2020, 6, 1)))


def test_symbol_ambiguity_is_an_error():
    m = SecurityMaster()
    m.add(sv(security_id="S1", symbol="9999", valid_from=date(2020, 1, 1)))
    m.add(sv(security_id="S2", symbol="9999", valid_from=date(2020, 1, 1)))
    with pytest.raises(AmbiguousSymbol):
        m.resolve_symbol("9999", as_of=date(2021, 1, 1))


def test_universe_excludes_etfs_by_default():
    m = SecurityMaster()
    m.add(sv(security_id="E", symbol="0050", instrument_type="etf", valid_from=date(2003, 6, 30)))
    m.add(sv(security_id="C", symbol="2330", valid_from=date(1994, 9, 5)))
    assert {v.security_id for v in m.universe(as_of=date(2026, 9, 8))} == {"C"}


def test_uni05_new_listing_visible_but_not_eligible():
    v = sv(security_id="NEW", symbol="7855", valid_from=date(2026, 8, 11))
    c = classify_coverage(v, price_history_sessions=20, min_history_sessions=120, liquidity_ok=True)
    assert c.in_catalog and not c.numerically_scorable and not c.simulation_eligible
    assert any(r.startswith("insufficient_history") for r in c.reasons)


def test_liquidity_rule_not_frozen_blocks_eligibility_explicitly():
    v = sv(security_id="OK", symbol="2330", valid_from=date(1994, 9, 5))
    c = classify_coverage(v, price_history_sessions=500, min_history_sessions=120, liquidity_ok=None)
    assert c.numerically_scorable and not c.simulation_eligible
    assert "liquidity_rule_not_frozen" in c.reasons


def test_r01_08_esb_and_non_equity_never_execution_eligible():
    esb = sv(security_id="E", symbol="9999", market="ESB", board="emerging", valid_from=date(2020, 1, 1))
    c = classify_coverage(esb, price_history_sessions=500, min_history_sessions=120, liquidity_ok=True)
    assert not c.simulation_eligible and any(r.startswith("market_out_of_simulation_scope") for r in c.reasons)
    etf = sv(security_id="F", symbol="0050", instrument_type="etf", valid_from=date(2003, 6, 30))
    c2 = classify_coverage(etf, price_history_sessions=500, min_history_sessions=120, liquidity_ok=True)
    assert not c2.simulation_eligible and any(r.startswith("instrument_out_of_simulation_scope") for r in c2.reasons)
