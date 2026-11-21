"""Shared figure style so every chart in the report looks the same.

Design rules we follow (see the report, Section 4.4):
  * light, solid hairline grid and axes so the data stands out
  * one colour per entity, used the same way in every figure
  * colour-blind-safe palette, plus direct labels where we can
  * log scale for time, because time taken is very right-skewed
  * titles that say what the chart shows, captions that say what to look at
"""
from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter

from . import config as C

TEXT_WIDTH_IN = 6.5          # width of the text block in the report


def apply_style() -> None:
    """Set matplotlib defaults for all report figures."""
    mpl.rcParams.update({
        "figure.dpi": 110,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.04,
        "font.family": "DejaVu Sans",
        "font.size": 8,
        "axes.titlesize": 9,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.labelsize": 8,
        "axes.labelcolor": C.INK_2,
        "axes.edgecolor": C.AXIS,
        "axes.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": C.GRID,
        "grid.linewidth": 0.5,
        "grid.linestyle": "-",
        "xtick.color": C.MUTED,
        "ytick.color": C.MUTED,
        "xtick.labelcolor": C.INK_2,
        "ytick.labelcolor": C.INK_2,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "legend.fontsize": 7,
        "legend.frameon": False,
        "lines.linewidth": 1.6,
        "lines.markersize": 4,
        "text.color": C.INK,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })


SEQ_CMAP = LinearSegmentedColormap.from_list("seq_blue", C.SEQ_CMAP_COLORS)


def minutes_formatter():
    """Tick labels for a log time axis: 0.5, 1, 2, 5, 10, 30, 60 ..."""
    def fmt(x, _pos):
        if x >= 1440:
            return f"{x / 1440:g} d"
        if x >= 60:
            return f"{x / 60:g} h"
        return f"{x:g}"
    return FuncFormatter(fmt)


def set_time_axis(ax, axis: str = "x", ticks=(0.5, 1, 2, 5, 10, 20, 60),
                  label: str = "Time taken (minutes, log scale)") -> None:
    """Log-scale a time axis with readable ticks."""
    if axis == "x":
        ax.set_xscale("log")
        ax.set_xticks(list(ticks))
        ax.xaxis.set_major_formatter(minutes_formatter())
        ax.xaxis.set_minor_locator(mpl.ticker.NullLocator())
        ax.set_xlabel(label)
    else:
        ax.set_yscale("log")
        ax.set_yticks(list(ticks))
        ax.yaxis.set_major_formatter(minutes_formatter())
        ax.yaxis.set_minor_locator(mpl.ticker.NullLocator())
        ax.set_ylabel(label)


def save(fig, name: str) -> None:
    """Save a figure as both PDF (for the report) and PNG (for previews)."""
    C.FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(C.FIG_DIR / f"{name}.pdf")
    fig.savefig(C.FIG_DIR / f"{name}.png", dpi=200)
    plt.close(fig)


def label_end(ax, x, y, text, color, dx=4, **kw):
    """Direct label at the end of a line (avoids a separate legend)."""
    ax.annotate(text, (x, y), xytext=(dx, 0), textcoords="offset points",
                va="center", ha="left", fontsize=7, color=C.INK_2,
                fontweight="bold", **kw)
    ax.plot([], [], color=color)   # keeps colour list consistent


def note(ax, text, loc=(0.0, -0.22), **kw):
    """Small grey note under an axis (sample size, source, etc.)."""
    ax.text(*loc, text, transform=ax.transAxes, fontsize=6.5, color=C.MUTED,
            ha="left", va="top", **kw)
