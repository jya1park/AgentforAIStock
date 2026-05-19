from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE_DIR = Path("/tmp")


def fetch_quotes(tickers: list[str], today: date | None = None) -> pd.DataFrame:
    """Fetch latest quotes for tickers via yfinance, cache per-day.

    Columns: close, prev_close, change_pct, volume, ma5, ma20,
             vol_avg20 (20d avg volume), volatility20 (20d daily-return stddev %).
    Index: ticker. Tickers with no data are dropped.
    """
    today = today or date.today()
    cache_path = CACHE_DIR / f"yf_cache_{today.isoformat()}.pkl"
    if cache_path.exists():
        return pd.read_pickle(cache_path)

    hist = yf.download(
        tickers=" ".join(tickers),
        period="40d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    rows = []
    for t in tickers:
        try:
            close = hist[t]["Close"].dropna()
            volume = hist[t]["Volume"].dropna()
        except KeyError:
            continue
        if len(close) < 2:
            continue
        daily_ret = close.pct_change().dropna()
        rows.append({
            "ticker": t,
            "close": close.iloc[-1],
            "prev_close": close.iloc[-2],
            "change_pct": (close.iloc[-1] / close.iloc[-2] - 1) * 100,
            "volume": volume.iloc[-1] if len(volume) else 0,
            "ma5": close.tail(5).mean(),
            "ma20": close.tail(20).mean(),
            "vol_avg20": volume.tail(20).mean() if len(volume) else 0,
            "volatility20": daily_ret.tail(20).std() * 100,
        })

    cols = ["close", "prev_close", "change_pct", "volume", "ma5", "ma20", "vol_avg20", "volatility20"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows).set_index("ticker")
    df.to_pickle(cache_path)
    return df
