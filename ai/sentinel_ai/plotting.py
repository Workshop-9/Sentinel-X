"""Style graphique commun (charte EPSI : encre #261E48 ; palette catégorielle validée
daltonisme ; rouge « critique » réservé aux alarmes)."""
from __future__ import annotations

import base64
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

INK = "#261E48"          # texte principal (charte)
INK2 = "#52514e"         # texte secondaire
MUTED = "#898781"        # graduations
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"
BLUE = "#2a78d6"         # série 1 / IA en production
ORANGE = "#eb6834"       # série 2
AQUA = "#1baf7a"         # série 3
OTHER = "#c3c2b7"        # éléments non mis en avant
CRITICAL = "#d03b3b"     # alarme (statut, jamais une série)
GOOD = "#0ca30c"
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def setup() -> None:
    available = {f.name for f in font_manager.fontManager.ttflist}
    family = [f for f in ("Montserrat", "Segoe UI", "DejaVu Sans") if f in available]
    plt.rcParams.update({
        "font.family": family or ["sans-serif"],
        "font.size": 10,
        "text.color": INK,
        "axes.labelcolor": INK2,
        "axes.edgecolor": AXIS,
        "axes.linewidth": 1,
        "axes.facecolor": SURFACE,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlecolor": INK,
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 1,
        "grid.linestyle": "-",
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK2,
        "ytick.labelcolor": INK2,
        "lines.linewidth": 2,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "legend.frameon": False,
        "legend.labelcolor": INK2,
        "figure.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "savefig.dpi": 160,
        "savefig.bbox": "tight",
    })


def save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
