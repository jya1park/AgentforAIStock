from dataclasses import dataclass
from pathlib import Path

import yaml

ONTOLOGY_PATH = Path(__file__).resolve().parent.parent / "ontology" / "ai_industry_ontology.yaml"
ETFS_PATH = Path(__file__).resolve().parent.parent / "data" / "etfs.yaml"


@dataclass(frozen=True)
class Tag:
    domain: str
    layer: str
    segment: str


class Ontology:
    def __init__(self, raw: dict):
        self.raw = raw

    @classmethod
    def load(cls, path: Path = ONTOLOGY_PATH) -> "Ontology":
        with open(path) as f:
            return cls(yaml.safe_load(f))

    @property
    def all_tickers(self) -> set[str]:
        return {c["ticker"] for _, _, _, c in self._iter_companies()}

    def tickers_by_segment(self, segment: str) -> list[str]:
        return [c["ticker"] for _, _, s, c in self._iter_companies() if s == segment]

    def tags(self, ticker: str) -> list[Tag]:
        return [Tag(d, l, s) for d, l, s, c in self._iter_companies() if c["ticker"] == ticker]

    def _iter_companies(self):
        for d, dom in self.raw["domains"].items():
            for l, layer in dom.get("layers", {}).items():
                for s, seg in layer.get("segments", {}).items():
                    for c in seg.get("companies", []):
                        yield d, l, s, c


class EtfCatalog:
    def __init__(self, raw: dict):
        self.raw = raw

    @classmethod
    def load(cls, path: Path = ETFS_PATH) -> "EtfCatalog":
        with open(path) as f:
            return cls(yaml.safe_load(f))

    def all_tickers(self) -> list[str]:
        return [e["ticker"] for e in self.entries()]

    def entries(self) -> list[dict]:
        return self.raw.get("us", []) + self.raw.get("kr", [])
