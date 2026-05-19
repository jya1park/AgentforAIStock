"""Fetch all ontology + ETF tickers via yfinance, save Excel + analyzer markdown.

Run locally (cloud env blocks Yahoo outbound):
    python scripts/snapshot.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analyzer import analyze, to_markdown
from src.data_fetcher import fetch_quotes
from src.ontology import EtfCatalog, Ontology


def main():
    ontology = Ontology.load()
    etfs = EtfCatalog.load()
    tickers = list(ontology.all_tickers) + etfs.all_tickers()
    print(f"fetching {len(tickers)} tickers...")
    df = fetch_quotes(tickers)
    xlsx_out = f"quotes_{date.today().isoformat()}.xlsx"
    df.to_excel(xlsx_out)
    print(f"saved {len(df)}/{len(tickers)} rows to {xlsx_out}")

    if df.empty:
        return

    md = to_markdown(analyze(df, ontology, etfs))
    md_out = f"snapshot_{date.today().isoformat()}.md"
    Path(md_out).write_text(md, encoding="utf-8")
    print(f"saved analyzer output to {md_out}")
    print("\n--- preview ---")
    print("\n".join(md.splitlines()[:25]))


if __name__ == "__main__":
    main()
