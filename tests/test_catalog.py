from twlab.sources.catalog import ENDPOINTS, by_source


def test_catalog_entries_are_unique_and_well_formed():
    keys = [(e.source_id, e.dataset) for e in ENDPOINTS]
    assert len(keys) == len(set(keys))
    for e in ENDPOINTS:
        assert e.url.startswith("https://"), e
        assert e.source_id in ("twse", "tpex", "finmind"), e
        assert e.date_format in ("roc_compact", "roc_slash", "greg_compact", "iso"), e
        assert e.instrument_scope in ("companies", "mixed", "esb", "index", "calendar"), e


def test_revenue_endpoints_declare_thousands_of_twd():
    """A5: la unidad de ingresos mensuales oficiales es miles de TWD; FinMind entrega TWD."""
    for e in ENDPOINTS:
        if e.dataset in ("t187ap05_L", "t187ap05_O", "t187ap05_R"):
            assert e.units.get("營業收入-當月營收") == "TWD_thousands", e.dataset


def test_by_source_covers_all_three_sources():
    assert {e.source_id for e in ENDPOINTS} == {"twse", "tpex", "finmind"}
    assert len(by_source("twse")) + len(by_source("tpex")) + len(by_source("finmind")) == len(ENDPOINTS)
