"""Generate chart images for Telegram — segment trends, etc."""

import platform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.dates as mdates
from datetime import datetime
from pathlib import Path

from src.segment_history import load_recent

# Korean font: NanumGothic on Linux (apt install fonts-nanum), Malgun Gothic on Windows
_KR_FONT = "NanumGothic" if platform.system() != "Windows" else "Malgun Gothic"
if any(_KR_FONT == f.name for f in fm.fontManager.ttflist):
    plt.rcParams["font.family"] = _KR_FONT
plt.rcParams["axes.unicode_minus"] = False

CHART_DIR = Path("/tmp")

SEGMENT_KR = {
    "pure_play_quantum": "양자컴퓨팅",
    "optical_transceiver": "광모듈",
    "fabless_ai_chip": "AI 팹리스",
    "gpu_accelerator": "GPU 가속기",
    "hbm_dram": "HBM 메모리",
    "edge_inference_soc": "엣지 추론칩",
    "power_grid_utility": "전력 유틸리티",
    "ai_dc_operator": "AI 데이터센터 운영사",
    "semiconductor_compute": "반도체 연산",
    "semiconductor_memory": "반도체 메모리",
    "crypto_to_ai_dc": "가상화폐→AI 전환",
    "ai_native_cloud": "AI 클라우드",
    "hyperscaler": "하이퍼스케일러",
    "colocation": "코로케이션",
    "epc_construction": "전력 EPC",
    "power_equipment": "전력장비",
    "switch_optical": "광스위치",
    "retail_brokerage": "모바일 거래 플랫폼",
}


def generate_segment_trend(days: int = 14, top_n: int = 8) -> Path | None:
    """Line chart of segment daily change_pct. Returns image path or None if no data.
    Shows top_n most volatile segments to keep the chart readable."""
    data = load_recent(days)
    if len(data) < 2:
        return None

    dates = [datetime.strptime(d, "%Y-%m-%d") for d in data.keys()]
    all_segments = set()
    for day_data in data.values():
        all_segments.update(day_data.keys())

    seg_volatility = {}
    for seg in all_segments:
        values = [data[d].get(seg, 0) for d in data.keys()]
        seg_volatility[seg] = max(values) - min(values)
    top_segments = sorted(seg_volatility, key=seg_volatility.get, reverse=True)[:top_n]

    fig, ax = plt.subplots(figsize=(10, 6))
    for seg in top_segments:
        values = [data[d].get(seg, 0) for d in data.keys()]
        label = SEGMENT_KR.get(seg, seg)
        ax.plot(dates, values, marker="o", markersize=4, label=label, linewidth=1.8)

    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.5)
    ax.set_ylabel("일별 등락률 (%)")
    ax.set_title(f"AI 산업 세그먼트 트렌드 (최근 {len(data)}일, 상위 {top_n})")
    ax.legend(loc="best", fontsize=8, ncol=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax.grid(axis="y", alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()

    path = CHART_DIR / "segment_trend.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
