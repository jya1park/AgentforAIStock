from src.ontology import Ontology


def test_load():
    ont = Ontology.load()
    assert ont.raw["version"] == 4


def test_all_tickers_dedup():
    ont = Ontology.load()
    tickers = ont.all_tickers
    assert len(tickers) > 100
    assert "NVDA" in tickers
    assert "005930.KS" in tickers


def test_tickers_by_segment():
    ont = Ontology.load()
    gpu = ont.tickers_by_segment("gpu_accelerator")
    assert {"NVDA", "AMD", "INTC", "AVGO"} <= set(gpu)


def test_cross_tag_samsung():
    ont = Ontology.load()
    layers = {t.layer for t in ont.tags("005930.KS")}
    assert "semiconductor_memory" in layers
    assert "semiconductor_foundry" in layers


def test_tags_returns_empty_for_unknown():
    ont = Ontology.load()
    assert ont.tags("NOT_A_TICKER") == []
