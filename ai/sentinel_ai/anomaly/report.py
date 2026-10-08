"""Artefacts lisibles d'un entraînement : figures PNG, rapport HTML autonome, model card."""
from __future__ import annotations

import html
import logging
from pathlib import Path
from typing import Any

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

from .. import plotting as P
from ..data.dataset import Dataset, extract_features
from ..data.scenarios import SCENARIOS, inject
from .evaluate import (SITE_SHIFT, STATIC_RULE_TEXT, EvalContext, RecoveryResult, confirm)
from .models import ALGORITHMS, ModelBundle

log = logging.getLogger(__name__)

SENSORS = [("temp", "Température", "°C"), ("hum", "Humidité", "%"), ("gas", "Gaz MQ-2", "ADC")]
FEATURE_SHORT = {
    "temp_dev": "écart temp.", "hum_dev": "écart hum.", "gas_dev": "écart gaz",
    "d_temp": "Δ temp. 30 s", "d_hum": "Δ hum. 30 s", "d_gas": "Δ gaz 30 s",
    "gas_std": "instabilité gaz",
}
HHMM = mdates.DateFormatter("%H:%M")


# ----------------------------------------------------------------------------- helpers
def _gapped(df: pd.DataFrame, max_gap_s: float = 10) -> pd.DataFrame:
    """Insère une ligne vide aux coupures de flux pour ne pas relier deux sessions
    par une droite trompeuse."""
    dt = df["time"].diff().dt.total_seconds().to_numpy()
    cuts = np.where(dt > max_gap_s)[0]
    if not len(cuts):
        return df
    pieces, prev = [], 0
    num = df.select_dtypes("number").columns
    for i in cuts:
        pieces.append(df.iloc[prev:i])
        hole = df.iloc[[i - 1]].copy()
        hole[num] = np.nan
        hole["time"] = df["time"].iloc[i - 1] + (df["time"].iloc[i] - df["time"].iloc[i - 1]) / 2
        pieces.append(hole)
        prev = i
    pieces.append(df.iloc[prev:])
    return pd.concat(pieces)


def _shade_labels(ax, df: pd.DataFrame) -> None:
    """Fond coloré sur les périodes « anomalie » et « transition »."""
    style = {"anomalie": dict(color=P.CRITICAL, alpha=0.10),
             "transition": dict(color=P.MUTED, alpha=0.18)}
    lab = df["label"].to_numpy()
    t = df["time"].to_numpy()
    start = 0
    for i in range(1, len(lab) + 1):
        if i == len(lab) or lab[i] != lab[start]:
            if lab[start] in style:
                ax.axvspan(t[start], t[i - 1], lw=0, **style[lab[start]])
            start = i


def _label_legend(ax) -> None:
    ax.legend(handles=[Patch(color=P.CRITICAL, alpha=0.25, label="Session anomalie"),
                       Patch(color=P.MUTED, alpha=0.35, label="Transition (exclue)")],
              loc="upper left", fontsize=8, ncol=2)


def _bar_labels(ax, bars, fmt: str, horizontal: bool = True) -> None:
    for b in bars:
        v = b.get_width() if horizontal else b.get_height()
        if np.isnan(v):
            continue
        if horizontal:
            ax.annotate(fmt.format(v), (v, b.get_y() + b.get_height() / 2), xytext=(4, 0),
                        textcoords="offset points", va="center", fontsize=9, color=P.INK)
        else:
            ax.annotate(fmt.format(v), (b.get_x() + b.get_width() / 2, v), xytext=(0, 3),
                        textcoords="offset points", ha="center", fontsize=9, color=P.INK)


# ----------------------------------------------------------------------------- figures
def fig_dataset(ds: Dataset, ctx: EvalContext, path: Path) -> Path:
    device = ctx.test["device_id"].value_counts().idxmax()
    df = ds.raw[ds.raw["device_id"] == device]
    line = _gapped(df)
    fig, axes = plt.subplots(3, 1, figsize=(10, 6.4), sharex=True)
    for ax, (col, title, unit) in zip(axes, SENSORS):
        ax.plot(line["time"], line[col], color=P.BLUE, lw=1.5)
        _shade_labels(ax, df)
        ax.set_title(title, fontsize=10)
        ax.set_ylabel(unit)
    bounds = [ctx.train["time"].min(), ctx.calib["time"].min(), ctx.test["time"].min(),
              ctx.test["time"].max()]
    names = ["entraînement", "calibration", "test"]
    for ax in axes:
        for b in bounds[1:3]:
            ax.axvline(b, color=P.INK2, lw=1)
    trans = mtransforms.blended_transform_factory(axes[0].transData, axes[0].transAxes)
    for a, b, n in zip(bounds[:-1], bounds[1:], names):
        axes[0].text(a + (b - a) / 2, 1.02, n, transform=trans, ha="center", va="bottom",
                     fontsize=9, color=P.INK2)
    _label_legend(axes[2])
    axes[-1].xaxis.set_major_formatter(HHMM)
    fig.suptitle("Jeu de données : télémétrie du boîtier SX-001 (une mesure toutes les 2 s)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold", color=P.INK, y=1.03)
    fig.tight_layout()
    return P.save(fig, path)


def fig_real_anomaly(timeline: pd.DataFrame, path: Path) -> Path | None:
    if timeline.empty:
        return None
    df = timeline
    line = _gapped(df)
    fig, axes = plt.subplots(4, 1, figsize=(10, 7.2), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1, 1, 1.3]})
    for ax, (col, title, unit) in zip(axes, SENSORS):
        ax.plot(line["time"], line[col], color=P.BLUE, lw=1.5)
        _shade_labels(ax, df)
        ax.set_title(title, fontsize=10)
        ax.set_ylabel(unit)
    ax = axes[3]
    ax.plot(line["time"], line["score"], color=P.BLUE, lw=1.5)
    _shade_labels(ax, df)
    ax.axhline(0, color=P.INK2, lw=1)
    ax.text(df["time"].iloc[0], 0, " seuil appris", va="bottom", fontsize=8, color=P.INK2)
    alarm = df[df["level"] == "alarm"]
    ax.scatter(alarm["time"], alarm["score"], s=22, color=P.CRITICAL, edgecolor=P.SURFACE,
               linewidth=1.2, zorder=3, label="Alarme confirmée")
    # Instant(s) où la sirène est déclenchée, relatif au début de la période anormale
    abnormal = df["label"] != "normal"
    period_start = df["time"].where(abnormal & ~abnormal.shift(fill_value=False)).ffill()
    for _, row in df[df["alarm_triggered"]].iterrows():
        t0 = period_start.loc[row.name]
        rel = (f" (+{(row['time'] - t0).total_seconds():.0f} s)"
               if abnormal.loc[row.name] and pd.notna(t0) else "")
        ax.annotate(f"sirène déclenchée{rel}", (row["time"], row["score"]), xytext=(10, 22),
                    textcoords="offset points", fontsize=9, color=P.INK,
                    arrowprops=dict(arrowstyle="-", color=P.INK2, lw=1))
    ax.set_title("Score d'anomalie (< 0 = anormal)", fontsize=10)
    ax.legend(loc="lower left", fontsize=8)
    _label_legend(axes[0])
    axes[-1].xaxis.set_major_formatter(HHMM)
    fig.suptitle("Session anomalie réelle rejouée dans le détecteur de production",
                 x=0.01, ha="left", fontsize=12, fontweight="bold", color=P.INK, y=1.02)
    fig.tight_layout()
    return P.save(fig, path)


def fig_scenarios(metrics: dict[str, Any], path: Path) -> Path:
    sc = metrics["scenarios"]
    keys = [k for k in SCENARIOS if k in sc][::-1]
    vals = [sc[k]["median_delay_s"] if sc[k]["median_delay_s"] is not None else np.nan for k in keys]
    fig, ax = plt.subplots(figsize=(9, 3.4))
    bars = ax.barh([SCENARIOS[k].title for k in keys], vals, height=0.42, color=P.BLUE)
    _bar_labels(ax, bars, "{:.0f} s")
    xmax = np.nanmax(vals) if np.isfinite(np.nanmax(vals)) else 10
    ax.set_xlim(0, xmax * 1.75)
    ax.set_xticks([t for t in ax.get_xticks() if t <= xmax * 1.1])
    for i, k in enumerate(keys):
        d = sc[k]
        txt = (f"IA {d['detected']}/{d['runs']}  ·  règle fixe : "
               + ("jamais" if d["static_detected"] == 0
                  else f"{d['static_detected']}/{d['runs']} ({d['static_median_delay_s']:.0f} s)"))
        ax.text(xmax * 1.22, i, txt, va="center", fontsize=8.5, color=P.INK2)
    ax.set_xlabel("secondes après le début de la dérive")
    ax.grid(axis="y", visible=False)
    ax.set_title("Délai médian avant alarme confirmée — pannes simulées sur données réelles")
    fig.text(0.01, -0.04, f"Règle fixe de comparaison : {STATIC_RULE_TEXT}. "
             "5 injections par scénario sur la période de test.", fontsize=8, color=P.MUTED)
    fig.tight_layout()
    return P.save(fig, path)


def fig_scenario_example(bundle: ModelBundle, ctx: EvalContext, path: Path) -> Path | None:
    runs = [r for r in ctx.scenario_runs if r.scenario.key == "surchauffe_lente"]
    if not runs:
        return None
    run = runs[len(runs) // 2]
    sc = run.scenario
    mod = inject(ctx.stream, run.start, sc)
    feats = extract_features(mod, **ctx.feature_params)
    lo, hi = max(0, run.start - 45), min(len(mod), run.start + sc.length)
    view = feats.loc[feats.index.intersection(range(lo, hi))]
    score = bundle.score(view)
    in_sc = view.index >= run.start
    al = np.zeros(len(view), bool)
    al[in_sc] = confirm(score[in_sc] < 0, ctx.consecutive)
    raw = mod.iloc[lo:hi]
    t_start = mod["time"].iloc[run.start]

    fig, axes = plt.subplots(3, 1, figsize=(10, 6), sharex=True)
    axes[0].plot(raw["time"], raw["temp"], color=P.BLUE, lw=1.5)
    axes[0].set_title("Température (°C)", fontsize=10)
    axes[1].plot(raw["time"], raw["gas"], color=P.BLUE, lw=1.5)
    axes[1].set_title("Gaz MQ-2 (ADC)", fontsize=10)
    axes[2].plot(view["time"], score, color=P.BLUE, lw=1.5)
    axes[2].axhline(0, color=P.INK2, lw=1)
    axes[2].set_title("Score d'anomalie (< 0 = anormal)", fontsize=10)
    for ax in axes:
        ax.axvline(t_start, color=P.INK2, lw=1)
    axes[0].annotate("début de la dérive", (t_start, axes[0].get_ylim()[1]), xytext=(4, -12),
                     textcoords="offset points", fontsize=8.5, color=P.INK2)
    if al.any():
        i = int(np.argmax(al))
        td = view["time"].iloc[i]
        off = sc.offsets()
        k = int(view.index[i]) - run.start
        axes[2].scatter([td], [score[i]], s=40, color=P.CRITICAL, edgecolor=P.SURFACE,
                        linewidth=1.5, zorder=3)
        axes[2].annotate(
            f"alarme après {(td - t_start).total_seconds():.0f} s\n"
            f"(+{off['temp'][k]:.2f} °C, +{off['gas'][k]:.1f} gaz seulement)",
            (td, score[i]), xytext=(40, 34), textcoords="offset points", fontsize=9,
            color=P.INK, va="bottom",
            arrowprops=dict(arrowstyle="-", color=P.INK2, lw=1))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
    fig.suptitle(f"Exemple : {sc.title.lower()} — {sc.description}", x=0.01, ha="left",
                 fontsize=11.5, fontweight="bold", color=P.INK, y=1.02)
    fig.tight_layout()
    return P.save(fig, path)


def fig_scores(bundle: ModelBundle, ctx: EvalContext, path: Path) -> Path | None:
    if not len(ctx.anomaly):
        return None
    s_n, s_a = bundle.score(ctx.test), bundle.score(ctx.anomaly)
    bins = np.linspace(min(s_n.min(), s_a.min()), max(s_n.max(), s_a.max()), 45)
    fig, ax = plt.subplots(figsize=(9, 3.6))
    for s, color, lab in ((s_n, P.BLUE, f"Test normal ({len(s_n)} mesures)"),
                          (s_a, P.ORANGE, f"Anomalie réelle ({len(s_a)} mesures)")):
        ax.hist(s, bins=bins, color=color, alpha=0.12, histtype="stepfilled")
        ax.hist(s, bins=bins, color=color, lw=1.5, histtype="step", label=lab)
    ax.axvline(0, color=P.INK2, lw=1)
    ax.text(0, ax.get_ylim()[1] * 0.95, " seuil appris", fontsize=8.5, color=P.INK2, va="top")
    ax.set_xlabel("score d'anomalie (< 0 = anormal)")
    ax.set_ylabel("nombre de mesures")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=8.5)
    ax.set_title("Séparation des scores : données normales jamais vues vs anomalie réelle")
    fig.tight_layout()
    return P.save(fig, path)


def fig_benchmark(benchmark: pd.DataFrame, production: str, path: Path) -> Path:
    df = benchmark.iloc[::-1]
    colors = [P.BLUE if a == production else P.OTHER for a in df["algorithm"]]
    names = [n + (" ★" if a == production else "") for a, n in zip(df["algorithm"], df["name"])]
    panels = [
        ("false_alarms_per_hour", 1, "{:.1f}", "Alarmes confirmées à tort", "par heure (test)"),
        ("test_fpr", 100, "{:.1f} %", "Mesures isolées suspectes", "% avant confirmation"),
        ("slow_overheat_delay_s", 1, "{:.0f} s", "Détection surchauffe lente", "délai médian (s)"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.4), sharey=True)
    for ax, (col, k, fmt, title, xlabel) in zip(axes, panels):
        vals = df[col].astype(float) * k
        _bar_labels(ax, ax.barh(names, vals, height=0.45, color=colors), fmt)
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_xlim(0, max(float(np.nanmax(vals)) * 1.35, 1))
        ax.grid(axis="y", visible=False)
    fig.suptitle("Comparaison de 4 algorithmes non supervisés (mêmes données, même protocole)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold", color=P.INK, y=1.04)
    fig.tight_layout()
    return P.save(fig, path)


def fig_site_shift(metrics: dict[str, Any], legacy: dict[str, Any], path: Path) -> Path | None:
    if metrics.get("site_shift_fpr") is None:
        return None
    groups = ["Features adaptatives\n(production)", "Niveaux absolus\n(ancienne version)"]
    same = [metrics["test_fpr"] * 100, legacy["test_fpr"] * 100]
    other = [metrics["site_shift_fpr"] * 100, legacy["site_shift_fpr"] * 100]
    x = np.arange(2)
    fig, ax = plt.subplots(figsize=(8, 3.8))
    _bar_labels(ax, ax.bar(x - 0.12, same, 0.22, color=P.BLUE, label="Même salle"), "{:.0f} %", False)
    shift = f"Autre salle (+{SITE_SHIFT['temp']:.0f} °C, {SITE_SHIFT['hum']:.0f} % HR, +{SITE_SHIFT['gas']:.0f} gaz)"
    _bar_labels(ax, ax.bar(x + 0.12, other, 0.22, color=P.ORANGE, label=shift), "{:.0f} %", False)
    ax.set_xticks(x, groups)
    ax.set_ylim(0, 110)
    ax.set_ylabel("% de mesures normales signalées")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", fontsize=8.5)
    ax.set_title("Robustesse au changement de salle (ex. salle de soutenance)")
    fig.tight_layout()
    return P.save(fig, path)


def fig_envelope(metrics: dict[str, Any], bare: dict[str, Any], path: Path) -> Path | None:
    keys = [k for k in SCENARIOS if k in metrics["scenarios"] and k in bare["scenarios"]][::-1]
    if not keys:
        return None
    y = np.arange(len(keys))
    with_env = [100 * metrics["scenarios"][k]["plateau_coverage"] for k in keys]
    without = [100 * bare["scenarios"][k]["plateau_coverage"] for k in keys]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    _bar_labels(ax, ax.barh(y + 0.13, with_env, 0.24, color=P.BLUE,
                            label="Isolation Forest + enveloppe apprise (production)"), "{:.0f} %")
    _bar_labels(ax, ax.barh(y - 0.13, without, 0.24, color=P.ORANGE,
                            label="Isolation Forest seul"), "{:.0f} %")
    ax.set_yticks(y, [SCENARIOS[k].title for k in keys])
    ax.set_xlim(0, 118)
    ax.set_xlabel("% des mesures encore en alerte pendant la dernière minute de l'incident")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.4, -0.2), ncol=2, fontsize=8.5)
    ax.set_title("Maintien de l'alerte tant que l'incident dure")
    fig.tight_layout()
    return P.save(fig, path)


def fig_explain(explain: pd.DataFrame, path: Path) -> Path | None:
    if explain.empty:
        return None
    cmap = LinearSegmentedColormap.from_list("blue", P.BLUE_RAMP)
    data = explain.to_numpy()
    vmax = max(10.0, float(np.nanpercentile(data, 95)))
    fig, ax = plt.subplots(figsize=(10, 0.55 * len(explain) + 1.6))
    ax.imshow(np.clip(data, 0, vmax), cmap=cmap, vmin=0, vmax=vmax, aspect="auto")
    ax.set_xticks(range(data.shape[1]), [FEATURE_SHORT.get(c, c) for c in explain.columns])
    ax.set_yticks(range(data.shape[0]), explain.index)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            ax.text(j, i, f"{v:.0f}" if v >= 10 else f"{v:.1f}", ha="center", va="center",
                    fontsize=8.5, color="white" if v > vmax * 0.55 else P.INK)
    ax.tick_params(length=0)
    ax.set_title("Explicabilité : écart à la normale de chaque feature au moment de l'alarme "
                 "(en écarts-types)")
    fig.tight_layout()
    return P.save(fig, path)


def fig_recovery(rec: RecoveryResult, path: Path) -> Path:
    a, b = rec.traces["avec_gel"], rec.traces["sans_gel"]
    fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
    axes[0].plot(a["time"], a["gas"], color=P.BLUE, lw=1.5)
    axes[0].set_title("Gaz MQ-2 (ADC) — bouffée de gaz de 60 s", fontsize=10)
    for name, df, color in (("avec gel de la ligne de base (production)", a, P.BLUE),
                            ("sans gel", b, P.ORANGE)):
        sec = rec.seconds["avec_gel" if df is a else "sans_gel"]
        lab = f"{name} : normal {sec:.0f} s après" if sec is not None else f"{name} : pas de retour"
        axes[1].plot(df["time"], df["score"], color=color, lw=1.5, label=lab)
    axes[1].axhline(0, color=P.INK2, lw=1)
    axes[1].set_title("Score d'anomalie (< 0 = anormal)", fontsize=10)
    axes[1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, fontsize=8.5)
    for ax in axes:
        ax.axvspan(rec.pulse_start, rec.pulse_end, color=P.CRITICAL, alpha=0.08, lw=0)
    axes[-1].xaxis.set_major_formatter(HHMM)
    fig.suptitle("Retour à la normale après l'incident", x=0.01, ha="left", fontsize=12,
                 fontweight="bold", color=P.INK, y=1.02)
    fig.tight_layout()
    return P.save(fig, path)


# ----------------------------------------------------------------------------- documents
def _pct(x: float | None, digits: int = 1) -> str:
    return "—" if x is None else f"{100 * x:.{digits}f} %"


def _sec(x: float | None) -> str:
    return "—" if x is None else f"{x:.0f} s"


def _labels(counts: dict[str, int]) -> str:
    return ", ".join(f"{k} : {v}" for k, v in counts.items())


def selection_text(benchmark: pd.DataFrame, production: str) -> str:
    """Justification du choix d'algorithme, déduite des résultats (reste vraie après ré-entraînement)."""
    b = benchmark.set_index("algorithm")
    p = b.loc[production]
    clean = b[b["false_alarms_per_hour"].fillna(np.inf) == 0]
    slow = clean["slow_overheat_delay_s"].astype(float).fillna(np.inf)
    if production in clean.index and len(slow) and slow.idxmin() == production:
        return (f"{p['name']} est retenu : parmi les algorithmes sans alarme confirmée à tort, "
                f"c'est celui qui détecte le plus tôt la surchauffe lente "
                f"({p['slow_overheat_delay_s']:.0f} s), le cas le plus difficile. Sa latence "
                f"({p['latency_ms']:.1f} ms par mesure) reste négligeable devant la cadence de 2 s.")
    best = b.loc[slow.idxmin(), "name"] if len(slow) and np.isfinite(slow.min()) else None
    hint = f" Sur cet entraînement, {best} obtient un meilleur compromis." if best else ""
    return (f"{p['name']} est l'algorithme configuré (anomaly.model.algorithm dans "
            f"config/settings.toml).{hint}")


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    th = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>"
                  for r in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


CSS = """
:root{--bg:#E4E6F3;--card:#ffffff;--ink:#261E48;--ink2:#52514e;--muted:#6f6d68;--line:#d9dbe9;
--accent:#A1A6D4;--good:#0a7f0a;--bad:#b42f2f;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15132a;--card:#1f1c38;
--ink:#f1f0fb;--ink2:#c9c7dd;--muted:#a3a1b8;--line:#35325a;--accent:#6d72b8;--good:#3ccf3c;
--bad:#ff7b7b;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#15132a;--card:#1f1c38;--ink:#f1f0fb;--ink2:#c9c7dd;--muted:#a3a1b8;
--line:#35325a;--accent:#6d72b8;--good:#3ccf3c;--bad:#ff7b7b;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:Montserrat,"Segoe UI",system-ui,sans-serif;line-height:1.55}
main{max-width:1060px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:1.9rem;margin:0 0 4px}h2{font-size:1.25rem;margin:40px 0 12px;padding-bottom:6px;
border-bottom:2px solid var(--accent)}h3{font-size:1rem;margin:20px 0 8px}
.sub{color:var(--ink2);margin:0 0 24px}.card{background:var(--card);border-radius:12px;
padding:18px 20px;margin:14px 0;box-shadow:0 1px 2px rgba(38,30,72,.08)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.kpi{background:var(--card);border-radius:12px;padding:14px 16px}
.kpi .l{font-size:.8rem;color:var(--ink2)}.kpi .v{font-size:1.7rem;font-weight:700}
.kpi .d{font-size:.78rem;color:var(--muted)}
figure{margin:14px 0;background:#fcfcfb;border-radius:12px;padding:12px;overflow:hidden}
figure img{width:100%;height:auto;display:block}figcaption{color:#52514e;font-size:.85rem;
padding:8px 4px 0}table{border-collapse:collapse;width:100%;font-size:.88rem;
font-variant-numeric:tabular-nums}th,td{text-align:left;padding:7px 10px;
border-bottom:1px solid var(--line)}th{color:var(--ink2);font-weight:600}
.scroll{overflow-x:auto}.ok{color:var(--good);font-weight:700}.ko{color:var(--bad);font-weight:700}
code{background:rgba(161,166,212,.25);padding:1px 5px;border-radius:4px;font-size:.88em}
ul{padding-left:20px}footer{color:var(--muted);font-size:.8rem;margin-top:40px}
@media print{body{background:#fff}.card,.kpi{box-shadow:none;border:1px solid #ddd}}
"""


def build_html(r: dict[str, Any], ds: Dataset, benchmark: pd.DataFrame,
               figs: dict[str, Path | None]) -> str:
    m, legacy = r["metrics"], r["legacy_metrics"]
    sc = m["scenarios"]
    det = sum(d["detected"] for d in sc.values())
    runs = sum(d["runs"] for d in sc.values())
    static = sum(d["static_detected"] for d in sc.values())
    slow = sc.get("surchauffe_lente", {})

    def fig(key: str, caption: str) -> str:
        p = figs.get(key)
        if not p:
            return ""
        return (f'<figure><img src="{P.data_uri(p)}" alt="{html.escape(caption)}">'
                f"<figcaption>{html.escape(caption)}</figcaption></figure>")

    kpis = [
        ("Alarmes à tort (test)", str(m["test_false_alarms"]),
         f"sur {m['test_minutes']} min jamais vues"),
        ("Anomalie réelle détectée", _pct(m.get("anomaly_recall"), 0),
         f"AUC {m['auc']:.3f}" if m.get("auc") is not None else ""),
        ("Pannes simulées détectées", f"{det}/{runs}", f"règle fixe : {static}/{runs}"),
        ("Surchauffe lente", _sec(slow.get("median_delay_s")), "délai médian avant alarme"),
        ("Alerte maintenue", _pct(m.get("plateau_coverage"), 0), "tant que l'incident dure"),
        ("Retour à la normale", _sec(r["recovery_s"].get("avec_gel")), "après la fin d'un incident"),
    ]
    kpi_html = "".join(f'<div class="kpi"><div class="l">{html.escape(l)}</div>'
                       f'<div class="v">{html.escape(v)}</div><div class="d">{html.escape(d)}</div></div>'
                       for l, v, d in kpis)

    gates = _table(["Contrôle", "Valeur", "Exigence", "Résultat"], [
        [g["name"], f"{g['value']:.3f}", f"{g['op']} {g['limit']}", "OK" if g["passed"] else "ÉCHEC"]
        for g in r["gates"]]).replace("<td>OK</td>", '<td class="ok">OK</td>').replace(
        "<td>ÉCHEC</td>", '<td class="ko">ÉCHEC</td>')

    splits = _table(["Jeu", "Mesures", "Début", "Fin"], [
        [k, v["rows"], v["start"][11:19], v["end"][11:19]] for k, v in r["splits"].items()])
    rep = ds.report
    ann = _table(["Plage", "Nouvelle étiquette", "Mesures", "Justification"], [
        [f"{a['start'][11:19]} → {a['end'][11:19]}", a["label"], a["rows"], a["reason"]]
        for a in rep["annotations"]]) if rep["annotations"] else "<p>Aucune.</p>"
    scen = _table(["Scénario", "Description", "IA détecte", "Délai médian", "Alerte maintenue",
                   "Règle fixe"], [
        [SCENARIOS[k].title, SCENARIOS[k].description, f"{d['detected']}/{d['runs']}",
         _sec(d["median_delay_s"]), _pct(d["plateau_coverage"], 0),
         "jamais" if d["static_detected"] == 0 else f"{d['static_detected']}/{d['runs']}"]
        for k, d in sc.items()])
    bench = _table(["Algorithme", "Mesures suspectes", "Alarmes à tort/h", "Anomalie réelle",
                    "Scénarios", "Surchauffe lente", "Alerte maintenue", "Latence"], [
        [row["name"] + (" ★" if row["algorithm"] == r["algorithm"] else ""), _pct(row["test_fpr"]),
         f"{row['false_alarms_per_hour']:.1f}", _pct(row["anomaly_recall"], 0),
         _pct(row["scenario_detection_rate"], 0), _sec(row["slow_overheat_delay_s"]),
         _pct(row["plateau_coverage"], 0), f"{row['latency_ms']:.2f} ms"]
        for row in benchmark.to_dict("records")])
    n_test, n_an = m["test_samples"], m.get("anomaly_samples", 0)
    fp = round(m["test_fpr"] * n_test)
    tp = round((m.get("anomaly_recall") or 0) * n_an)
    confusion = _table(["", "Prédit normal", "Prédit anomalie"], [
        ["Réellement normal (test)", n_test - fp, fp],
        ["Réellement anomalie", n_an - tp, tp]])
    feats = ", ".join(f"<code>{f}</code>" for f in r["features"])
    md = r["metadata"]

    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rapport IA Sentinel-X</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><main>
<h1>Sentinel-X — Maintenance prédictive</h1>
<p class="sub">Rapport d'entraînement du modèle <code>{html.escape(r['version'])}</code> ·
{html.escape(ALGORITHMS[r['algorithm']])} · {md['trained_at'].replace('T', ' ')} ·
{'promu en production' if r['promoted'] else 'NON promu'}</p>
<div class="kpis">{kpi_html}</div>

<h2>1. Ce que fait le modèle</h2>
<div class="card"><p>Le boîtier envoie température, humidité et gaz toutes les 2 s. Le cahier des
charges interdit les seuils fixes (<code>if temp &gt; 40</code>) : le modèle apprend donc, sans
étiquettes, à quoi ressemble le <b>fonctionnement normal</b>, et signale tout ce qui s'en écarte.</p>
<ul><li><b>Features en flux</b> ({feats}) : écart à une ligne de base qui s'adapte au site
(demi-vie {r['feature_params']['baseline_halflife'] * 2 / 60:.0f} min), vitesse de variation sur
{r['feature_params']['window'] * 2} s, instabilité du gaz. Le <b>même code</b> calcule les features
à l'entraînement et en direct.</li>
<li><b>Modèle</b> : {html.escape(ALGORITHMS[r['algorithm']])} entraîné uniquement sur des données
normales, puis <b>seuil calibré</b> sur une période distincte pour viser {r['target_fpr']:.0%} de
mesures isolées suspectes.</li>
<li><b>Enveloppe statistique apprise</b> : un Isolation Forest « sature » hors de son domaine
d'entraînement (un écart énorme sur une seule feature n'est pas mieux isolé qu'un point de bordure).
Chaque feature est donc aussi bornée à {r['envelope']['z_max']:.1f} écarts-types, borne apprise
(1,5 × le plus grand écart vu en fonctionnement normal). Sans elle, l'alerte retomberait pendant
un incident qui dure (voir section 3).</li>
<li><b>Confirmation</b> : alarme (sirène) seulement après {r['consecutive']} mesures anormales
consécutives ({r['consecutive'] * 2} s), ce qui filtre les glitchs ponctuels de l'ADC du MQ-2.</li>
<li><b>Gel de la ligne de base</b> pendant un incident : une fuite ne devient pas « la nouvelle
normale » ; ré-apprentissage seulement si la situation dure plus de 5 min.</li>
<li><b>Explicabilité</b> : chaque alerte publiée contient ses causes probables
(ex. « gaz en hausse rapide »).</li></ul></div>

<h2>2. Données</h2>
<div class="card"><p>{rep['rows']} mesures valides du {rep['start'][:16]} au {rep['end'][11:16]}
({_labels(rep['labels'])}).
{rep['duplicates_removed']} doublon(s) et {rep['invalid_removed']} mesure(s) hors plage physique retirés.
Empreinte des données : <code>{rep['fingerprint']}</code>.</p>
<h3>Découpage chronologique (jamais aléatoire sur une série temporelle)</h3>{splits}
<h3>Corrections d'étiquettes (data/annotations.csv)</h3><div class="scroll">{ann}</div></div>
{fig('dataset', "Les trois capteurs sur toute la collecte. Les bornes verticales séparent entraînement, calibration et test.")}

<h2>3. Résultats</h2>
<h3>Anomalie réelle</h3>
{fig('real', "La session « anomalie » (gaz + chaleur) rejouée dans le détecteur de production, avec 5 min de contexte normal.")}
{fig('scores', "Les scores des données normales jamais vues et ceux de l'anomalie réelle ne se chevauchent pas.")}
<div class="card"><h3>Matrice de confusion (par mesure, avant confirmation)</h3>{confusion}</div>
<h3>Pannes simulées : détection précoce</h3>
<div class="card"><p>Impossible de provoquer une vraie fuite de gaz en salle : des dérives réalistes
sont <b>ajoutées à de vraies mesures normales</b> de la période de test (bruit capteur conservé),
à 5 instants différents. Comparaison avec la règle fixe « {html.escape(STATIC_RULE_TEXT)} ».</p>
<div class="scroll">{scen}</div></div>
{fig('scenarios', "Délai médian avant alarme confirmée pour chaque type de panne.")}
{fig('example', "La surchauffe lente (exemple du cahier des charges) est signalée bien avant tout seuil critique.")}
<h3>Robustesse et comportement</h3>
{fig('envelope', "Sans l'enveloppe apprise, l'Isolation Forest seul laisse retomber l'alerte alors que l'incident continue.")}
{fig('site', "Avec des niveaux absolus, changer de salle déclencherait des alarmes en continu ; les features adaptatives ne bougent pas.")}
{fig('recovery', "Après une bouffée de gaz, le système revient à la normale rapidement grâce au gel de la ligne de base.")}
{fig('explain', "Chaque type de panne est reconnu par une dynamique différente : le modèle est explicable.")}

<h2>4. Choix de l'algorithme</h2>
<div class="card"><p>Quatre algorithmes non supervisés de scikit-learn ont été entraînés et évalués
sur exactement les mêmes données, chacun avec son enveloppe apprise. ★ = modèle en production.</p><div class="scroll">{bench}</div>
<p>{html.escape(selection_text(benchmark, r['algorithm']))}</p></div>
{fig('benchmark', "Compromis entre mesures suspectes et rapidité de détection.")}

<h2>5. Contrôles qualité avant mise en production</h2>
<div class="card">{gates}</div>

<h2>6. Limites et perspectives</h2>
<div class="card"><ul>
<li>{rep['rows']} mesures (≈ {rep['rows'] * 2 / 60:.0f} min) dans une seule salle : le taux de fausses
alarmes est estimé sur seulement {m['test_minutes']} min. Collecter plusieurs heures (jour/nuit)
affinerait le seuil.</li>
<li>Les scénarios sont synthétiques (dérives ajoutées à du signal réel) : ils mesurent la
sensibilité, pas la physique exacte d'une vraie fuite.</li>
<li>Le MQ-2 n'est pas calibré : « gaz » est une valeur ADC brute, pas des ppm.</li>
<li>Perspectives : fusion avec le PIR et la vision, ré-entraînement automatique, suivi de dérive
des données.</li></ul></div>

<h2>7. Reproductibilité</h2>
<div class="card"><ul>
<li>Commande : <code>python -m sentinel_ai train</code> (paramètres dans <code>config/settings.toml</code>)</li>
<li>Python {md['python']} · scikit-learn {md['sklearn']} · sentinel_ai {md['sentinel_ai']}</li>
<li>Seuil appris : <code>{r['threshold']:.5f}</code> · graine aléatoire fixe</li>
<li>SHA-256 du modèle : <code>{r['sha256']}</code> (vérifié à chaque chargement)</li></ul></div>
<footer>Généré automatiquement par sentinel_ai — Workshop EPSI M1 2026, groupe Sentinel-X.</footer>
</main></body></html>"""


def build_model_card(r: dict[str, Any], ds: Dataset) -> str:
    m = r["metrics"]
    lines = [
        f"# Model card — {r['version']}",
        "",
        f"**Tâche** : détection d'anomalies cinétiques (maintenance prédictive) sur la télémétrie "
        f"du boîtier Sentinel-X (température, humidité, gaz MQ-2, une mesure / 2 s).  ",
        f"**Algorithme** : {ALGORITHMS[r['algorithm']]} (scikit-learn {r['metadata']['sklearn']}), "
        f"non supervisé, entraîné sur le fonctionnement normal uniquement.  ",
        f"**Statut** : {'en production' if r['promoted'] else 'non promu'} · "
        f"SHA-256 `{r['sha256'][:16]}…`",
        "",
        "## Entrées",
        f"Features calculées en flux (fenêtre {r['feature_params']['window']} mesures, "
        f"ligne de base demi-vie {r['feature_params']['baseline_halflife']} mesures) : "
        + ", ".join(f"`{f}`" for f in r["features"]) + ".",
        "",
        "## Sortie (topic `sentinel/<id>/anomaly`)",
        "`score` (< 0 = anormal), `is_anomaly`, `streak`, `level` (normal/suspect/alarm), "
        "`causes` (features les plus anormales). Alarme confirmée après "
        f"{r['consecutive']} anomalies consécutives.",
        "",
        "## Données",
        f"{ds.report['rows']} mesures valides ({_labels(ds.report['labels'])}), "
        f"empreinte `{ds.report['fingerprint']}`. Split chronologique : "
        + ", ".join(f"{k} {v['rows']}" for k, v in r["splits"].items()) + ".",
        "",
        "## Performances (données jamais vues)",
        f"- Alarmes confirmées à tort : {m['test_false_alarms']} sur {m['test_minutes']} min "
        f"({_pct(m['test_fpr'])} de mesures isolées suspectes)",
    ]
    if m.get("anomaly_recall") is not None:
        lines.append(f"- Session anomalie réelle : {_pct(m['anomaly_recall'], 0)} des mesures "
                     f"signalées, AUC {m['auc']:.3f}")
    for k, d in m["scenarios"].items():
        lines.append(f"- {SCENARIOS[k].title} : {d['detected']}/{d['runs']}, délai médian "
                     f"{_sec(d['median_delay_s'])} (règle fixe : {d['static_detected']}/{d['runs']})")
    lines += [
        f"- Changement de salle : {_pct(m.get('site_shift_fpr'))} de mesures suspectes "
        f"(ancienne version à niveaux absolus : {_pct(r['legacy_metrics'].get('site_shift_fpr'))})",
        f"- Retour à la normale après incident : {_sec(r['recovery_s'].get('avec_gel'))}",
        f"- Alerte maintenue pendant un incident qui dure : {_pct(m.get('plateau_coverage'), 0)} "
        f"(sans enveloppe : {_pct(r['no_envelope_metrics'].get('plateau_coverage'), 0)})",
        "",
        "## Enveloppe apprise",
        f"Chaque feature est bornée à {r['envelope']['z_max']:.1f} écarts-types (1,5 × le plus grand "
        "écart observé en fonctionnement normal) pour compenser la saturation de l'Isolation Forest "
        "hors de son domaine d'entraînement.",
        "",
        "## Limites",
        "- Peu de données (une seule salle, une matinée) ; scénarios de panne synthétiques.",
        "- Gaz = valeur ADC brute non calibrée ; ne remplace pas un détecteur de gaz certifié.",
        "- Le modèle détecte un écart au comportement habituel, pas la cause physique exacte.",
        "",
        "## Contrôles qualité",
    ]
    lines += [f"- {g['name']} : {g['value']:.3f} {g['op']} {g['limit']} → "
              f"{'OK' if g['passed'] else 'ÉCHEC'}" for g in r["gates"]]
    return "\n".join(lines) + "\n"


def build_report(vdir: Path, r: dict[str, Any], ds: Dataset, ctx: EvalContext,
                 benchmark: pd.DataFrame, explain: pd.DataFrame, timeline: pd.DataFrame,
                 recovery: RecoveryResult, bundle: ModelBundle) -> Path:
    P.setup()
    fd = vdir / "figures"
    figs = {
        "dataset": fig_dataset(ds, ctx, fd / "01_dataset.png"),
        "real": fig_real_anomaly(timeline, fd / "02_anomalie_reelle.png"),
        "scores": fig_scores(bundle, ctx, fd / "03_distribution_scores.png"),
        "scenarios": fig_scenarios(r["metrics"], fd / "04_scenarios_delais.png"),
        "example": fig_scenario_example(bundle, ctx, fd / "05_exemple_surchauffe_lente.png"),
        "site": fig_site_shift(r["metrics"], r["legacy_metrics"], fd / "06_robustesse_salle.png"),
        "recovery": fig_recovery(recovery, fd / "07_retour_normale.png"),
        "explain": fig_explain(explain, fd / "08_explicabilite.png"),
        "benchmark": fig_benchmark(benchmark, r["algorithm"], fd / "09_benchmark_modeles.png"),
        "envelope": fig_envelope(r["metrics"], r["no_envelope_metrics"],
                                 fd / "10_maintien_alerte.png"),
    }
    (vdir / "model_card.md").write_text(build_model_card(r, ds), encoding="utf-8")
    out = vdir / "report.html"
    out.write_text(build_html(r, ds, benchmark, figs), encoding="utf-8")
    log.info("Rapport : %s (%d figures)", out, sum(1 for v in figs.values() if v))
    return out
