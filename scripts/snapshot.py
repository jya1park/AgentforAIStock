"""Fetch all ontology + ETF tickers via yfinance and save to Excel.

Run locally (cloud env blocks Yahoo outbound):
    python scripts/snapshot.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_fetcher import fetch_quotes
from src.ontology import EtfCatalog, Ontology


def main():
    tickers = list(Ontology.load().all_tickers) + EtfCatalog.load().all_tickers()
    print(f"fetching {len(tickers)} tickers...")
    df = fetch_quotes(tickers)
    out = f"quotes_{date.today().isoformat()}.xlsx"
    df.to_excel(out)
    print(f"saved {len(df)}/{len(tickers)} rows to {out}")
    if not df.empty:
        print("\ntop 5 by change_pct:")
        print(df.nlargest(5, "change_pct")[["close", "change_pct"]].to_string())
        print("\nbottom 5 by change_pct:")
        print(df.nsmallest(5, "change_pct")[["close", "change_pct"]].to_string())


if __name__ == "__main__":
    main()
