import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date
import numpy as np
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

from backtest_config import DEFAULT_PARAMS
from fotmob_api import (
    FOTMOB_LIGA_IDS, FOTMOB_HEADERS, TEAM_NAME_OVERRIDES,
    _normalize, resolve_team, _parse_table_row,
    hent_fotmob_tabell as _hent_fotmob_tabell,
    hent_fotmob_team as _hent_fotmob_team,
    hent_fotmob_xg as _hent_fotmob_xg,
    beregn_styrke, beregn_form_styrke, beregn_dyp_poisson,
)

st.set_page_config(page_title="Modelltipset", page_icon="⚽", layout="wide")

# ─────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────
_GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');

/* ── Global theme ── */
html, body, [data-testid="stAppViewContainer"] {
    font-family: 'DM Sans', sans-serif !important;
}
[data-testid="stAppViewContainer"] {
    background: #f5f4f0 !important;
}
[data-testid="stHeader"] {
    background: #f5f4f0 !important;
}
[data-testid="stSidebar"] {
    background: #eeedea !important;
}

/* ── Brand header ── */
.brand-header {
    color: #5a9e74; font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 2px; margin-bottom: 2px;
}
.kupong-title { font-size: 28px; font-weight: 700; color: #2c2c30; margin: 0; }
.kupong-meta { font-size: 13px; color: #8a8a90; margin-top: 2px; }

/* ── Legend ── */
.legend {
    display: flex; gap: 18px; align-items: center; flex-wrap: wrap;
    font-size: 11px; color: #8a8a90; padding: 6px 0 10px 0;
    border-bottom: 1px solid #e8e6e1; margin-bottom: 8px;
}
.legend-item { display: inline-flex; align-items: center; gap: 4px; }
.legend-swatch {
    display: inline-block; width: 14px; height: 10px; border-radius: 2px;
}

/* ── Prob bar ── */
.prob-bar {
    display: flex; height: 15px; border-radius: 3px; overflow: hidden;
    font-size: 10px; font-weight: 700; line-height: 15px;
}
.prob-bar.model-bar { border: 1px solid rgba(74,140,100,0.3); }
.prob-seg-h { background: #7bac8e; color: #fff; text-align: center; text-shadow: 0 1px 3px rgba(0,0,0,0.25); }
.prob-seg-u { background: #b8af88; color: #fff; text-align: center; text-shadow: 0 1px 3px rgba(0,0,0,0.25); }
.prob-seg-b { background: #be9484; color: #fff; text-align: center; text-shadow: 0 1px 3px rgba(0,0,0,0.25); }
/* Modell-bar: sterkere farger */
.model-bar .prob-seg-h { background: #4a8c64; }
.model-bar .prob-seg-u { background: #9e9460; }
.model-bar .prob-seg-b { background: #ad6e58; }

/* ── Score badge ── */
.score-badge {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 14px; font-weight: 700; font-family: 'DM Sans', monospace;
}
.score-badge .goals {
    background: #eeedea; border-radius: 5px;
    padding: 1px 7px; min-width: 28px; text-align: center; color: #2c2c30;
}
.score-badge .dash { color: #b0b0b0; }

/* ── Signal ── */
.signal-wrap {
    display: inline-flex; align-items: center; gap: 5px;
}
.signal-dot {
    display: inline-block; width: 10px; height: 10px;
    border-radius: 50%;
}
.signal-dot.sterk { background: #c0392b; box-shadow: 0 0 6px rgba(192,57,43,0.45); }
.signal-dot.mild  { background: #d4a34a; }
.signal-dot.noytral { background: #b0b0b0; }
.signal-label { font-size: 11px; font-weight: 600; }
.signal-label.sterk { color: #c0392b; }
.signal-label.mild  { color: #d4a34a; }
.signal-label.noytral { color: #b0b0b0; }

/* ── Modellnivå badge ── */
.modell-badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 11px; font-weight: 600;
}

/* ── Kamprad (integrert visning) ── */
.kamprad {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px;
    border: 1px solid #e8e6e1;
    border-radius: 10px 10px 0 0;
    margin-top: 10px;
    background: #ffffff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.kamprad .kamp-navn {
    flex: 1.5; font-weight: 600; font-size: 14px; line-height: 1.3;
    color: #2c2c30;
}
.kamprad .kamp-navn .liga { font-size: 11px; color: #a0a0a5; font-weight: 400; }
.kamprad .kamp-col { flex: 1; text-align: center; }
.kamprad .kamp-col .col-label {
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px;
    color: #a0a0a5; margin-bottom: 3px;
}

/* ── Kommentar-rad ── */
.kommentar-rad {
    display: flex; align-items: center; justify-content: space-between;
    padding: 4px 14px 6px 14px;
    background: #ffffff;
    border-left: 1px solid #e8e6e1;
    border-right: 1px solid #e8e6e1;
}
.kommentar-tekst {
    font-size: 12px; color: #8a8a90; font-style: italic;
    flex: 1; line-height: 1.4;
}
.avvik-badge {
    font-size: 10px; font-weight: 600; color: #b08a30;
    background: rgba(176,138,48,0.07);
    padding: 2px 8px; border-radius: 8px;
    white-space: nowrap; margin-left: 10px;
}

/* ── Expander: visuelt tilknyttet kamprad ── */
[data-testid="stExpander"] {
    margin-top: 0 !important;
    margin-bottom: 6px !important;
    border: 1px solid #e8e6e1 !important;
    border-top: none !important;
    border-radius: 0 0 10px 10px !important;
    background: #ffffff !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
    overflow: hidden;
}
[data-testid="stExpander"] summary {
    padding: 5px 14px !important;
    font-size: 12px !important;
    color: #8a8a90 !important;
}
[data-testid="stExpander"] summary p {
    font-size: 12px !important;
    color: #8a8a90 !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    background: #faf9f7 !important;
    padding: 10px 14px !important;
}

/* ── Styrkerating progress bars (detaljpanel) ── */
.styrke-bar-wrap { margin: 4px 0; }
.styrke-bar-label {
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.3px;
    color: #a0a0a5; margin-bottom: 2px;
}
.styrke-bar-bg {
    height: 4px; background: #eeecea; border-radius: 2px; overflow: hidden;
}
.styrke-bar-fill { height: 4px; border-radius: 2px; }
.styrke-bar-fill.angrep { background: #5a9e74; }
.styrke-bar-fill.forsvar { background: #7a8ea8; }

/* ── Kupong-tabell ── */
.kupong-table {
    width: 100%; border-collapse: separate; border-spacing: 0;
    border-radius: 8px; overflow: hidden;
    border: 1px solid #e8e6e1;
    margin: 8px 0 16px 0;
}
.kupong-table th {
    padding: 10px 12px; text-align: center; font-size: 12px;
    font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
    background: #faf9f7; color: #2c2c30;
    border-bottom: 2px solid #e8e6e1;
}
.kupong-table th:first-child { text-align: left; }
.kupong-table td {
    padding: 8px 12px; border-bottom: 1px solid #eeedea;
    font-size: 14px; vertical-align: middle;
}
.kupong-table tr:last-child td { border-bottom: none; }
.kupong-row-singel { background: transparent; }
.kupong-row-dobbel { background: rgba(37,99,235,0.04); }
.kupong-row-trippel { background: rgba(220,38,38,0.04); }

/* Tegn-badge i kupong */
.tegn-badge {
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 8px;
    font-weight: 700; font-size: 14px;
}
.tegn-badge.aktiv { color: #fff; }
.tegn-badge.aktiv-modell { background: #1a6b3c; }
.tegn-badge.aktiv-verdi  { background: #b8860b; }
.tegn-badge.inaktiv { color: rgba(128,128,128,0.25); }

/* Type chip */
.type-chip {
    display: inline-block; padding: 3px 12px; border-radius: 12px;
    font-size: 12px; font-weight: 600; color: #fff; letter-spacing: 0.3px;
}
.type-chip.singel  { background: #6b7280; }
.type-chip.dobbel  { background: #2563eb; }
.type-chip.trippel { background: #dc2626; }

/* Begrunnelse chip */
.begrunnelse-chip {
    display: inline-block; padding: 3px 10px; border-radius: 8px;
    font-size: 12px; background: rgba(128,128,128,0.08);
    color: inherit; max-width: 260px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* ── KPI-kort ── */
.kpi-row {
    display: flex; gap: 12px; margin: 8px 0 16px 0; flex-wrap: wrap;
}
.kpi-card {
    flex: 1; min-width: 100px; padding: 14px 18px;
    border-radius: 10px; text-align: center;
    background: #ffffff;
    border: 1px solid #e8e6e1;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.kpi-card .kpi-icon { font-size: 20px; margin-bottom: 2px; }
.kpi-card .kpi-value { font-size: 26px; font-weight: 700; color: #2c2c30; }
.kpi-card .kpi-label { font-size: 12px; color: #a0a0a5; margin-top: 2px; }
</style>
"""
st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# KONSTANTER
# ─────────────────────────────────────────────

NT_API = "https://api.norsk-tipping.no/PoolGamesSportInfo/v1/api/tipping/live-info"

# ─────────────────────────────────────────────
# DATAHENTING: NORSK TIPPING TIPPEKUPONG
# ─────────────────────────────────────────────

@st.cache_data(ttl=180)
def hent_nt_data():
    try:
        r = requests.get(NT_API, timeout=10)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)

def prosesser_nt(json_data):
    kamper = []
    for dag in json_data.get("gameDays", []):
        dag_navn = {"MIDWEEK": "Midtuke", "SATURDAY": "Lørdag", "SUNDAY": "Søndag"}.get(
            dag.get("dayType", ""), dag.get("dayType", ""))
        game = dag.get("game", {})
        matches = game.get("matches", [])
        folk_ft = game.get("tips", {}).get("fullTime", {}).get("peoples", [])

        for i, m in enumerate(matches):
            folk = folk_ft[i] if i < len(folk_ft) else {}
            liga = m.get("arrangement", {}).get("name", "")
            dato_raw = m.get("date", "")
            dato = dato_raw[:10] if dato_raw else ""

            kamper.append({
                "Dag": dag_navn,
                "Kamp": m.get("name", ""),
                "Hjemmelag": m.get("teams", {}).get("home", {}).get("webName", ""),
                "Bortelag": m.get("teams", {}).get("away", {}).get("webName", ""),
                "Liga": liga,
                "Dato": dato,
                "Folk H%": folk.get("home", 0),
                "Folk U%": folk.get("draw", 0),
                "Folk B%": folk.get("away", 0),
                "FotmobLigaId": FOTMOB_LIGA_IDS.get(liga),
            })
    return pd.DataFrame(kamper)

# ─────────────────────────────────────────────
# FOTMOB CACHED WRAPPERS
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def hent_fotmob_tabell(liga_id):
    return _hent_fotmob_tabell(liga_id)

@st.cache_data(ttl=3600)
def hent_fotmob_team(team_id):
    return _hent_fotmob_team(team_id)

@st.cache_data(ttl=3600)
def hent_fotmob_xg(liga_id):
    return _hent_fotmob_xg(liga_id)

# ─────────────────────────────────────────────
# INNBYRDES HISTORIKK (H2H)
# ─────────────────────────────────────────────

def finn_h2h(h_fixtures, b_fixtures, h_team_id, b_team_id):
    """Finner innbyrdes kamper mellom to lag fra fixture-listene."""
    if not h_fixtures or not b_fixtures:
        return []

    h2h = []
    sett = set()
    for fx in h_fixtures:
        opp_id = fx["away_id"] if fx["is_home"] else fx["home_id"]
        if opp_id == b_team_id:
            key = f"{fx['home_name']}-{fx['away_name']}-{fx['home_goals']}-{fx['away_goals']}"
            if key not in sett:
                sett.add(key)
                h2h.append(fx)

    # Sorter nyeste først (de er allerede i kronologisk rekkefølge, reverser)
    h2h.reverse()
    return h2h[:5]

def h2h_oppsummering(h2h_kamper, h_team_id):
    """Lager tekstlig oppsummering av H2H."""
    if not h2h_kamper:
        return None
    seire, uavgjort, tap = 0, 0, 0
    scoret, innsluppet = 0, 0
    for fx in h2h_kamper:
        if fx["is_home"]:
            hg, ag = fx["home_goals"], fx["away_goals"]
        else:
            hg, ag = fx["away_goals"], fx["home_goals"]
        scoret += hg
        innsluppet += ag
        if hg > ag:
            seire += 1
        elif hg == ag:
            uavgjort += 1
        else:
            tap += 1
    return {
        "seire": seire, "uavgjort": uavgjort, "tap": tap,
        "scoret": scoret, "innsluppet": innsluppet,
        "kamper": len(h2h_kamper),
    }

# ─────────────────────────────────────────────
# HJELPEFUNKSJONER VISNING
# ─────────────────────────────────────────────

def maal_snitt(scoret, spilt):
    try:
        s, p = int(scoret), int(spilt)
        return round(s / max(p, 1), 3)
    except Exception:
        return None

def farge(avvik):
    if avvik is None:
        return "gray"
    if avvik > 8:
        return "green"
    if avvik < -8:
        return "red"
    return "gray"

def pil(avvik):
    if avvik is None:
        return "–"
    if avvik > 8:
        return "🟢"
    if avvik < -8:
        return "🔴"
    return "⚪"

def form_bokser(form_liste):
    """Returnerer form som fargede W/D/L-bokser i HTML."""
    if not form_liste:
        return ""
    farger = {"W": "#3a7d5c", "D": "#a09478", "L": "#b06060"}
    html = ""
    for f in form_liste[:5]:
        r = f.get("result", "?")
        c = farger.get(r, "#9ca3af")
        tooltip = f"{f.get('score', '')} vs {f.get('opponent', '')}"
        html += (
            f'<span title="{tooltip}" style="display:inline-block;width:22px;height:22px;'
            f'line-height:22px;text-align:center;border-radius:4px;margin:1px;'
            f'background:{c};color:white;font-weight:bold;font-size:11px">'
            f'{r}</span>'
        )
    return html

def modell_nivaa_badge(nivaa):
    """Returnerer en farget badge for modellnivå."""
    farger = {
        "Dyp (form+xG)": "#5a9e74",
        "Dyp (form)": "#5a86a8",
        "Basis (sesongsnitt)": "#b8a050",
        "Ingen modell": "#b0b0b0",
    }
    bg = farger.get(nivaa, "#b0b0b0")
    return (
        f'<span style="background:{bg};color:white;padding:2px 8px;'
        f'border-radius:10px;font-size:12px;font-weight:bold">{nivaa}</span>'
    )

# ─────────────────────────────────────────────
# SPILLFORSLAG
# ─────────────────────────────────────────────

SPILLFORSLAG_PROFILER = [
    {"navn": "Lite", "rader": 72, "pris": 72},
    {"navn": "Middels", "rader": 256, "pris": 256},
    {"navn": "Stort", "rader": 384, "pris": 384},
]


def generer_spillforslag(analyse_resultater, maal_rader):
    """Genererer spillforslag for en gitt budsjettgrense (maks rader).

    Algoritme:
    1. Klassifiser hver kamp: ønsket antall tegn (1/2/3) + hvilke tegn
    2. Optimaliser: juster opp/ned garderinger så produktet ≤ maal_rader
    3. Prioriter: helgarder usikre kamper, singel på sikre verdikamper

    Returns: (forslag_liste, faktisk_rader)
    """
    n = len(analyse_resultater)
    if n == 0:
        return [], 0

    # ── Steg 1: Analyser hver kamp ──
    kamper = []
    for i, a in enumerate(analyse_resultater):
        pr = a["poisson_res"]
        folk_h, folk_u, folk_b = a["folk_h"], a["folk_u"], a["folk_b"]

        if pr:
            probs = {"H": pr["H"], "U": pr["U"], "B": pr["B"]}
            avvik = {"H": pr["H"] - folk_h, "U": pr["U"] - folk_u, "B": pr["B"] - folk_b}
        else:
            probs = {"H": folk_h, "U": folk_u, "B": folk_b}
            avvik = {"H": 0, "U": 0, "B": 0}

        # Sortér utfall: mest sannsynlig først
        sortert = sorted(probs.items(), key=lambda x: -x[1])
        topp_prob = sortert[0][1]
        nest_prob = sortert[1][1]
        confidence = topp_prob - nest_prob
        max_avvik = max(avvik.values())
        max_neg_avvik = min(avvik.values())
        value_spread = max_avvik - max_neg_avvik

        # Klassifisér ønsket gardering
        if topp_prob >= 60 and confidence >= 20:
            onsket = 1  # Svært sikker → singel
        elif topp_prob >= 45 and confidence >= 10:
            onsket = 1  # Ganske sikker → singel
        elif confidence <= 5 or (topp_prob < 38):
            onsket = 3  # Svært jevn → trippel
        else:
            onsket = 2  # Middels → dobbel

        # Velg tegn i prioritert rekkefølge
        # Primært: høyest modell-sannsynlighet
        # Sekundært: best verdi (størst positivt avvik mot folk) — spill mot folket!
        # Tertiært: gjenværende utfall
        primaer = sortert[0][0]
        andre = [s for s in sortert[1:]]
        # Blant de to resterende: velg den med størst verdi (avvik) som sekundær
        andre_med_verdi = sorted(andre, key=lambda x: -avvik[x[0]])
        sekundaer = andre_med_verdi[0][0]
        tertiaer = andre_med_verdi[1][0]

        # Hvis sekundær har mye bedre verdi enn primær, og primær er usikker,
        # kan vi bytte rekkefølge for singel-tegn (spill verdi!)
        singel_tegn = primaer
        if avvik[sekundaer] > avvik[primaer] + 8 and probs[sekundaer] >= 25:
            singel_tegn = sekundaer  # Verdi-spill: velg det undertippede utfallet

        # Begrunnelse
        if onsket == 1:
            if avvik[singel_tegn] > 5:
                begrunnelse = f"Sikker + verdi på {singel_tegn} ({avvik[singel_tegn]:+.0f}pp vs folk)"
            elif confidence >= 20:
                begrunnelse = f"Klar favoritt ({primaer} {topp_prob:.0f}%)"
            else:
                begrunnelse = f"Modell-favoritt ({primaer} {topp_prob:.0f}%)"
        elif onsket == 3:
            begrunnelse = f"Svært jevn kamp — helgardert"
        else:
            if avvik[sekundaer] > 5:
                begrunnelse = f"Verdi på {sekundaer} ({avvik[sekundaer]:+.0f}pp vs folk)"
            elif confidence <= 8:
                begrunnelse = f"Usikker — gardert {primaer}+{sekundaer}"
            else:
                begrunnelse = f"Gardert med {sekundaer} ({probs[sekundaer]:.0f}%)"

        kamper.append({
            "idx": i,
            "probs": probs,
            "avvik": avvik,
            "confidence": confidence,
            "value_spread": value_spread,
            "topp_prob": topp_prob,
            "onsket": onsket,
            "primaer": primaer,
            "sekundaer": sekundaer,
            "tertiaer": tertiaer,
            "singel_tegn": singel_tegn,
            "begrunnelse": begrunnelse,
            "har_modell": pr is not None,
        })

    # ── Steg 2: Finn eksakt fordeling av singler/dobler/tripler ──
    # Finn beste kombinasjon av dobler (2) og tripler (3) slik at 2^d * 3^t = maal_rader
    best_fordeling = (0, 0, 0)  # (produkt, antall_dobler, antall_tripler)
    for tripler in range(min(n, 8) + 1):
        for dobler in range(n - tripler + 1):
            prod = (3 ** tripler) * (2 ** dobler)
            if prod <= maal_rader and prod > best_fordeling[0]:
                best_fordeling = (prod, dobler, tripler)
            if prod > maal_rader:
                break
    faktisk_rader = best_fordeling[0]
    antall_dobler = best_fordeling[1]
    antall_tripler = best_fordeling[2]

    # Ranger kamper: høy score = bør garderes (usikker + verdi-spredning)
    gardering_rank = sorted(
        range(n),
        key=lambda j: -kamper[j]["confidence"] + kamper[j]["value_spread"] * 0.5,
        reverse=True,
    )

    # Tildel: tripler til de som bør garderes mest, dobler til neste, resten singler
    tegn_per_kamp = [1] * n
    for rank, j in enumerate(gardering_rank):
        if rank < antall_tripler:
            tegn_per_kamp[j] = 3
        elif rank < antall_tripler + antall_dobler:
            tegn_per_kamp[j] = 2

    # ── Steg 3: Bygg forslag med valgte tegn og begrunnelse ──
    forslag = []
    for j, k in enumerate(kamper):
        ant = tegn_per_kamp[j]
        avvik = k["avvik"]
        if ant == 1:
            tegn_str = k["singel_tegn"]
            type_str = "singel"
            av = avvik.get(tegn_str, 0)
            if av > 5:
                begrunnelse = f"Sikker + verdi på {tegn_str} ({av:+.0f}pp vs folk)"
            elif k["confidence"] >= 20:
                begrunnelse = f"Klar favoritt ({k['primaer']} {k['topp_prob']:.0f}%)"
            else:
                begrunnelse = f"Modell-favoritt ({k['primaer']} {k['topp_prob']:.0f}%)"
        elif ant == 2:
            tegn_str = "".join(sorted([k["primaer"], k["sekundaer"]], key="HUB".index))
            type_str = "dobbel"
            sek = k["sekundaer"]
            av_sek = avvik.get(sek, 0)
            if av_sek > 5:
                begrunnelse = f"Verdi på {sek} ({av_sek:+.0f}pp vs folk)"
            elif k["confidence"] <= 8:
                begrunnelse = f"Jevn kamp — gardert {k['primaer']}+{sek}"
            else:
                begrunnelse = f"Gardert med {sek} ({k['probs'][sek]:.0f}%)"
        else:
            tegn_str = "HUB"
            type_str = "trippel"
            begrunnelse = f"Svært jevn kamp — helgardert"

        forslag.append({
            "tegn": tegn_str,
            "type": type_str,
            "begrunnelse": begrunnelse,
            "probs": k["probs"],
            "avvik": k["avvik"],
        })

    return forslag, faktisk_rader


# ─────────────────────────────────────────────
# GOOGLE SHEETS — HISTORIKK
# ─────────────────────────────────────────────

def sheets_available():
    """Sjekker om Google Sheets er konfigurert."""
    return GSPREAD_AVAILABLE and "gcp_service_account" in st.secrets

def get_gsheet_client():
    """Kobler til Google Sheets via service account fra Streamlit secrets."""
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(creds)

def get_historikk_sheet():
    """Returnerer historikk-arket. Oppretter header-rad hvis arket er tomt."""
    client = get_gsheet_client()
    sheet_url = st.secrets.get("sheets", {}).get("spreadsheet_url", "")
    if sheet_url:
        sh = client.open_by_url(sheet_url)
    else:
        sh = client.open("TippingAnalyse Historikk")
    try:
        ws = sh.worksheet("Historikk")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Historikk", rows=1000, cols=30)

    # Opprett header hvis arket er tomt
    existing_headers = ws.row_values(1)
    if not existing_headers:
        headers = [
            "kupong_id", "dato", "dag", "hjemmelag", "bortelag", "liga",
            "h_team_id", "b_team_id",
            "folk_h", "folk_u", "folk_b",
            "modell_h", "modell_u", "modell_b",
            "modell_nivaa", "lambda_h", "lambda_b",
            "max_avvik", "modell_tips", "verdi_tips",
            "resultat_h_maal", "resultat_b_maal", "resultat",
            "modell_korrekt", "verdi_korrekt", "folk_korrekt",
            "lagret_tidspunkt",
            "spill_lite", "spill_medium", "spill_stor",
            "spill_lite_korrekt", "spill_medium_korrekt", "spill_stor_korrekt",
        ]
        ws.append_row(headers)
    else:
        # Migrer: legg til spillforslag-kolonner hvis de mangler
        spill_headers = [
            "spill_lite", "spill_medium", "spill_stor",
            "spill_lite_korrekt", "spill_medium_korrekt", "spill_stor_korrekt",
        ]
        missing = [h for h in spill_headers if h not in existing_headers]
        if missing:
            start_col = len(existing_headers) + 1
            needed_cols = start_col + len(missing) - 1
            if ws.col_count < needed_cols:
                ws.resize(cols=needed_cols)
            for j, h in enumerate(missing):
                ws.update_cell(1, start_col + j, h)
    return ws

def lagre_kupong_til_sheets(analyse_resultater, spillforslag=None):
    """Lagrer kupong til Google Sheets. Returnerer (antall_lagret, allerede_lagret).
    spillforslag: dict med nøkler 'lite', 'medium', 'stor' → list of forslag-dicts.
    """
    if not sheets_available() or not analyse_resultater:
        return 0, False

    try:
        ws = get_historikk_sheet()

        # Generer kupong_id
        datoer = [a["rad"]["Dato"] for a in analyse_resultater if a["rad"]["Dato"]]
        dager = [a["rad"]["Dag"] for a in analyse_resultater]
        første_dato = min(datoer) if datoer else datetime.now().strftime("%Y-%m-%d")
        dag_label = dager[0] if dager else "Ukjent"
        kupong_id = f"{første_dato}_{dag_label}"

        # Duplikat-sjekk: hent alle kupong_id-er
        existing_ids = ws.col_values(1)[1:]  # Skip header
        if kupong_id in existing_ids:
            return 0, True

        # Bygg rader
        nå = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rader = []
        for i, a in enumerate(analyse_resultater):
            rad = a["rad"]
            pr = a["poisson_res"]
            folk_h, folk_u, folk_b = a["folk_h"], a["folk_u"], a["folk_b"]

            modell_h = pr["H"] if pr else ""
            modell_u = pr["U"] if pr else ""
            modell_b = pr["B"] if pr else ""
            lambda_h = pr["lambda_h"] if pr else ""
            lambda_b = pr["lambda_b"] if pr else ""

            # Modell-tips: utfall med høyest modell-%
            modell_tips = ""
            if pr:
                m = {"H": pr["H"], "U": pr["U"], "B": pr["B"]}
                modell_tips = max(m, key=m.get)

            # Verdi-tips: utfall med størst positivt avvik vs folk
            verdi_tips = ""
            if pr:
                avvik = {"H": pr["H"] - folk_h, "U": pr["U"] - folk_u, "B": pr["B"] - folk_b}
                beste = max(avvik, key=avvik.get)
                if avvik[beste] > value_threshold:
                    verdi_tips = beste

            max_avvik = round(a["max_poi_avvik"], 1)

            # Folk-favoritt
            folk_fav = max({"H": folk_h, "U": folk_u, "B": folk_b}, key={"H": folk_h, "U": folk_u, "B": folk_b}.get)

            # Spillforslag-tegn for denne kampen
            sf_lite = ""
            sf_medium = ""
            sf_stor = ""
            if spillforslag:
                sf_l = spillforslag.get("lite", [])
                sf_m = spillforslag.get("medium", [])
                sf_s = spillforslag.get("stor", [])
                if i < len(sf_l) and sf_l[i]:
                    sf_lite = sf_l[i]["tegn"]
                if i < len(sf_m) and sf_m[i]:
                    sf_medium = sf_m[i]["tegn"]
                if i < len(sf_s) and sf_s[i]:
                    sf_stor = sf_s[i]["tegn"]

            rader.append([
                kupong_id, rad["Dato"], rad["Dag"],
                rad["Hjemmelag"], rad["Bortelag"], rad["Liga"],
                str(a["h_team_id"] or ""), str(a["b_team_id"] or ""),
                str(folk_h), str(folk_u), str(folk_b),
                str(modell_h), str(modell_u), str(modell_b),
                a["modell_nivaa"], str(lambda_h), str(lambda_b),
                str(max_avvik), modell_tips, verdi_tips,
                "", "", "",  # resultat_h_maal, resultat_b_maal, resultat
                "", "", "",  # modell_korrekt, verdi_korrekt, folk_korrekt
                nå,
                sf_lite, sf_medium, sf_stor,
                "", "", "",  # spill_lite/medium/stor_korrekt
            ])

        if rader:
            ws.append_rows(rader)

        return len(rader), False
    except Exception as e:
        st.warning(f"Kunne ikke lagre kupong: {e}")
        return 0, False

@st.cache_data(ttl=1800)
def hent_historikk_data():
    """Henter all historikkdata fra Google Sheets. Cachet i 30 min."""
    if not sheets_available():
        return pd.DataFrame()
    try:
        ws = get_historikk_sheet()
        data = ws.get_all_records()
        if not data:
            return pd.DataFrame()
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()

def oppdater_resultater():
    """Oppdaterer resultater for kamper som er ferdigspilt. Returnerer antall oppdatert."""
    if not sheets_available():
        return 0
    try:
        ws = get_historikk_sheet()
        all_data = ws.get_all_records()
        if not all_data:
            return 0

        i_dag = date.today().isoformat()
        oppdatert = 0
        batch_updates = []

        for idx, row in enumerate(all_data):
            row_num = idx + 2  # +2 for header + 0-index
            # Kun kamper uten resultat med dato før i dag
            if row.get("resultat") or not row.get("dato") or str(row["dato"]) >= i_dag:
                continue

            h_team_id = row.get("h_team_id")
            b_team_id = row.get("b_team_id")
            if not h_team_id or not b_team_id:
                continue

            try:
                h_team_id = int(h_team_id)
                b_team_id = int(b_team_id)
            except (ValueError, TypeError):
                continue

            # Hent lagdata for hjemmelaget
            team_data = hent_fotmob_team(h_team_id)
            if not team_data:
                continue

            # Finn kampen mot bortelaget
            for fx in reversed(team_data.get("fixtures", [])):
                if fx["home_id"] == h_team_id and fx["away_id"] == b_team_id:
                    hm = fx["home_goals"]
                    bm = fx["away_goals"]
                    if hm > bm:
                        res = "H"
                    elif hm == bm:
                        res = "U"
                    else:
                        res = "B"

                    modell_tips = str(row.get("modell_tips", ""))
                    verdi_tips = str(row.get("verdi_tips", ""))
                    # Folk-favoritt
                    try:
                        folk = {"H": float(row.get("folk_h", 0)), "U": float(row.get("folk_u", 0)), "B": float(row.get("folk_b", 0))}
                        folk_fav = max(folk, key=folk.get)
                    except (ValueError, TypeError):
                        folk_fav = ""

                    modell_korrekt = "true" if modell_tips == res else "false"
                    verdi_korrekt = "true" if verdi_tips and verdi_tips == res else ("false" if verdi_tips else "")
                    folk_korrekt = "true" if folk_fav == res else "false"

                    # Batch: kolonner U-Z (21-26) = resultat_h_maal..folk_korrekt
                    batch_updates.append({
                        "range": f"U{row_num}:Z{row_num}",
                        "values": [[str(hm), str(bm), res, modell_korrekt, verdi_korrekt, folk_korrekt]],
                    })

                    # Spillforslag-korrekthet (kolonner AD-AF)
                    spill_lite = str(row.get("spill_lite", ""))
                    spill_medium = str(row.get("spill_medium", ""))
                    spill_stor = str(row.get("spill_stor", ""))
                    if spill_lite or spill_medium or spill_stor:
                        sl_ok = "true" if res in spill_lite else "false" if spill_lite else ""
                        sm_ok = "true" if res in spill_medium else "false" if spill_medium else ""
                        ss_ok = "true" if res in spill_stor else "false" if spill_stor else ""
                        batch_updates.append({
                            "range": f"AD{row_num}:AF{row_num}",
                            "values": [[sl_ok, sm_ok, ss_ok]],
                        })
                    oppdatert += 1
                    break

        if batch_updates:
            ws.batch_update(batch_updates)

        return oppdatert
    except Exception as e:
        st.warning(f"Feil ved oppdatering av resultater: {e}")
        return 0

# ─────────────────────────────────────────────
# APP START
# ─────────────────────────────────────────────

st.title("⚽ Modelltipset")
st.caption("Folkerekke · Dyp Poisson-analyse · Form · H2H · Verdianalyse · Historikk")

st.markdown(
    "Modellen estimerer sannsynligheten for hjemmeseier, uavgjort og borteseier "
    "ved å kombinere flere faktorer: "
    "**lagstyrke** (historiske prestasjoner), "
    "**kampform** (nylige resultater), "
    "**forventet målproduksjon** og "
    "**hjemmebanefordel**. "
    "Resultatet sammenlignes med folkerekka for å identifisere verdispill."
)

# Last NT-data
with st.spinner("Henter tippekupong fra Norsk Tipping..."):
    nt_json, nt_feil = hent_nt_data()

if nt_feil or not nt_json:
    st.error(f"Kunne ikke hente Norsk Tipping-data: {nt_feil}")
    st.stop()

df = prosesser_nt(nt_json)
st.success(f"Hentet {len(df)} kamper fra Norsk Tipping")

# Last FotMob-statistikk
liga_data_cache = {}  # liga → {"teams": {...}, "league_avg_home": ..., "league_avg_away": ...}
xg_cache = {}         # liga → {lagnavn: xg}
team_data_cache = {}   # team_id → team data

ligaer = df[df["FotmobLigaId"].notna()]["Liga"].unique()
if len(ligaer) > 0:
    with st.spinner("Henter lagstatistikk fra FotMob..."):
        # Parallell henting av ligatabell + xG
        def _hent_liga(liga):
            lid = FOTMOB_LIGA_IDS.get(liga)
            if not lid:
                return liga, None, None
            data = hent_fotmob_tabell(lid)
            xg = hent_fotmob_xg(lid)
            return liga, data, xg

        with ThreadPoolExecutor(max_workers=6) as pool:
            for liga, data, xg in pool.map(_hent_liga, ligaer):
                if data and data.get("teams"):
                    liga_data_cache[liga] = data
                if xg:
                    xg_cache[liga] = xg

    # Hent lagdata for alle lag som trengs
    needed_teams = set()
    for _, rad in df.iterrows():
        liga = rad["Liga"]
        ld = liga_data_cache.get(liga, {})
        teams = ld.get("teams", {})
        if teams:
            _, h_stats = resolve_team(teams, rad["Hjemmelag"])
            _, b_stats = resolve_team(teams, rad["Bortelag"])
            if h_stats and h_stats.get("team_id"):
                needed_teams.add(h_stats["team_id"])
            if b_stats and b_stats.get("team_id"):
                needed_teams.add(b_stats["team_id"])

    if needed_teams:
        with st.spinner(f"Henter detaljert lagdata for {len(needed_teams)} lag..."):
            # Parallell henting av lagdata — største flaskehals
            def _hent_team(tid):
                return tid, hent_fotmob_team(tid)

            with ThreadPoolExecutor(max_workers=8) as pool:
                for tid, td in pool.map(_hent_team, needed_teams):
                    if td:
                        team_data_cache[tid] = td

    if liga_data_cache:
        st.success(f"Hentet statistikk for {len(liga_data_cache)} ligaer fra FotMob")

# ─── Forklaring ───
with st.expander("Slik leser du analysen"):
    st.markdown("""
    ### Analysen sammenligner **Folkerekka** med en **Dyp Poisson-modell**:

    | Parameter | Kilde | Hva det er |
    |-----------|-------|------------|
    | **Folkerekka** | Norsk Tipping | Hva vanlige tippere tror (%) |
    | **Poisson-modell** | FotMob-statistikk | Matematisk beregnet sannsynlighet |

    ### Modellnivåer:
    - **Dyp (form+xG)**: Styrkeratings + siste 10 kamper + expected goals
    - **Dyp (form)**: Styrkeratings + siste 10 kamper
    - **Basis (sesongsnitt)**: Kun sesongens hjemme/borte-statistikk
    - **Ingen modell**: FotMob-data ikke tilgjengelig

    ### Verdisignal:
    - 🟢 **Grønn** = Modellen ser **mer** sannsynlighet enn folk (>8pp) → **potensiell verdi**
    - 🔴 **Rød** = Folk overtipper vs. modellen (>8pp) → **unngå**
    - ⚪ **Grå** = Lite avvik

    ### Dyp Poisson-modell:
    Beregner attack- og defense-styrke relativt til ligasnittet. Blender 60% siste 10 kamper
    med 40% sesongsnitt. Justerer med xG-data der tilgjengelig. Bruker Poisson-fordeling for
    å beregne sannsynlighet for alle mulige resultater.
    """)

# ─── Filter ───
st.sidebar.header("Filter")
dag_valg = st.sidebar.multiselect("Kupong", options=df["Dag"].unique(), default=df["Dag"].unique())
df_vis = df[df["Dag"].isin(dag_valg)].copy()
bare_verdi = st.sidebar.checkbox("Vis bare kamper med potensielt verdispill")
min_avvik = st.sidebar.slider("Minste modell-avvik å vise (pp)", 0, 20, 0)

# ─── Oppdater ───
if st.button("Oppdater alle data"):
    st.cache_data.clear()
    st.rerun()

st.divider()

# ─────────────────────────────────────────────
# MODELLPARAMETRE
# ─────────────────────────────────────────────

model_params = st.session_state.get("model_params", DEFAULT_PARAMS)
value_threshold = model_params.get("value_threshold_pp", DEFAULT_PARAMS["value_threshold_pp"])

# ─────────────────────────────────────────────
# BEREGN ANALYSE FOR ALLE KAMPER
# ─────────────────────────────────────────────

analyse_resultater = []

for _, rad in df_vis.iterrows():
    hjemmelag = rad["Hjemmelag"]
    bortelag = rad["Bortelag"]
    liga = rad["Liga"]
    folk_h, folk_u, folk_b = rad["Folk H%"], rad["Folk U%"], rad["Folk B%"]

    # Hent ligadata
    ld = liga_data_cache.get(liga, {})
    teams = ld.get("teams", {})
    league_avg_home = ld.get("league_avg_home", 1.4)
    league_avg_away = ld.get("league_avg_away", 1.1)

    # Resolve lag
    h_fm_navn, h_stats = resolve_team(teams, hjemmelag)
    b_fm_navn, b_stats = resolve_team(teams, bortelag)

    # Hent lagdata og form
    h_team_id = h_stats.get("team_id") if h_stats else None
    b_team_id = b_stats.get("team_id") if b_stats else None
    h_team_data = team_data_cache.get(h_team_id) if h_team_id else None
    b_team_data = team_data_cache.get(b_team_id) if b_team_id else None

    h_form = beregn_form_styrke(
        h_team_data["fixtures"] if h_team_data else None, h_team_id, True,
        form_window=model_params.get("form_window", DEFAULT_PARAMS["form_window"]),
    ) if h_team_data else None
    b_form = beregn_form_styrke(
        b_team_data["fixtures"] if b_team_data else None, b_team_id, False,
        form_window=model_params.get("form_window", DEFAULT_PARAMS["form_window"]),
    ) if b_team_data else None

    # xG
    xg_data = xg_cache.get(liga, {})
    h_xg = None
    b_xg = None
    if xg_data:
        # Prøv å matche xG-data med FotMob-navn
        if h_fm_navn and h_fm_navn in xg_data:
            h_xg = xg_data[h_fm_navn]
        if b_fm_navn and b_fm_navn in xg_data:
            b_xg = xg_data[b_fm_navn]

    # Poisson
    poisson_res = None
    modell_nivaa = "Ingen modell"
    if h_stats and b_stats:
        poisson_res = beregn_dyp_poisson(
            h_stats, b_stats, league_avg_home, league_avg_away,
            h_form, b_form, h_xg, b_xg,
            params=model_params,
        )
        if poisson_res:
            modell_nivaa = poisson_res["modell_nivaa"]

    # H2H
    h2h_kamper = finn_h2h(
        h_team_data["fixtures"] if h_team_data else None,
        b_team_data["fixtures"] if b_team_data else None,
        h_team_id, b_team_id,
    )
    h2h_opps = h2h_oppsummering(h2h_kamper, h_team_id) if h2h_kamper else None

    # Avvik
    poi_h = poisson_res["H"] if poisson_res else None
    poi_u = poisson_res["U"] if poisson_res else None
    poi_b = poisson_res["B"] if poisson_res else None
    avvik_poi = [
        (poi_h - folk_h) if poi_h else None,
        (poi_u - folk_u) if poi_u else None,
        (poi_b - folk_b) if poi_b else None,
    ]
    max_poi_avvik = max((abs(a) for a in avvik_poi if a is not None), default=0)

    analyse_resultater.append({
        "rad": rad,
        "h_stats": h_stats, "b_stats": b_stats,
        "h_fm_navn": h_fm_navn, "b_fm_navn": b_fm_navn,
        "h_team_data": h_team_data, "b_team_data": b_team_data,
        "h_team_id": h_team_id, "b_team_id": b_team_id,
        "h_form": h_form, "b_form": b_form,
        "poisson_res": poisson_res,
        "modell_nivaa": modell_nivaa,
        "h2h_kamper": h2h_kamper, "h2h_opps": h2h_opps,
        "avvik_poi": avvik_poi,
        "max_poi_avvik": max_poi_avvik,
        "folk_h": folk_h, "folk_u": folk_u, "folk_b": folk_b,
        "poi_h": poi_h, "poi_u": poi_u, "poi_b": poi_b,
        "league_avg_home": league_avg_home,
        "league_avg_away": league_avg_away,
    })

# ─────────────────────────────────────────────
# GENERER SPILLFORSLAG (kun neste kupong = 12 kamper)
# ─────────────────────────────────────────────

# Finn neste kupong: grupper analyse_resultater per dag, velg den tidligste
_kuponger_per_dag = {}
for a in analyse_resultater:
    dag = a["rad"]["Dag"]
    _kuponger_per_dag.setdefault(dag, []).append(a)

# Velg kupongen med tidligst dato (= neste kupong)
neste_kupong_dag = None
neste_kupong_dato = None
neste_kupong_analyser = []
for dag, kamper in _kuponger_per_dag.items():
    datoer = [a["rad"]["Dato"] for a in kamper if a["rad"]["Dato"]]
    min_dato = min(datoer) if datoer else "9999"
    if neste_kupong_dato is None or min_dato < neste_kupong_dato:
        neste_kupong_dato = min_dato
        neste_kupong_dag = dag
        neste_kupong_analyser = kamper

spillforslag_alle = {}
for profil in SPILLFORSLAG_PROFILER:
    forslag, rader = generer_spillforslag(neste_kupong_analyser, profil["rader"])
    spillforslag_alle[profil["navn"].lower()] = {
        "forslag": forslag,
        "rader": rader,
        "profil": profil,
        "dag": neste_kupong_dag,
        "dato": neste_kupong_dato,
        "analyser": neste_kupong_analyser,
    }

# ─────────────────────────────────────────────
# LAGRE KUPONG AUTOMATISK
# ─────────────────────────────────────────────

if sheets_available() and analyse_resultater:
    # Grupper analyser per kupong (dagtype)
    from collections import defaultdict as _defaultdict
    _kuponger = _defaultdict(list)
    for a in analyse_resultater:
        dag = a["rad"]["Dag"]
        _kuponger[dag].append(a)

    # Map spillforslag til neste-kupong
    _nk_set = set(id(a) for a in neste_kupong_analyser)
    _sf_lite = spillforslag_alle.get("lite", {}).get("forslag", [])
    _sf_mid = spillforslag_alle.get("middels", {}).get("forslag", [])
    _sf_stor = spillforslag_alle.get("stort", {}).get("forslag", [])

    _totalt_lagret = 0
    for _dag, _kamper in _kuponger.items():
        # Bygg spillforslag-mapping for denne kupongen
        _sf = {"lite": [], "medium": [], "stor": []}
        _nk_idx = 0
        for a in _kamper:
            if id(a) in _nk_set and _nk_idx < len(_sf_lite):
                _sf["lite"].append(_sf_lite[_nk_idx] if _nk_idx < len(_sf_lite) else None)
                _sf["medium"].append(_sf_mid[_nk_idx] if _nk_idx < len(_sf_mid) else None)
                _sf["stor"].append(_sf_stor[_nk_idx] if _nk_idx < len(_sf_stor) else None)
                _nk_idx += 1
            else:
                _sf["lite"].append(None)
                _sf["medium"].append(None)
                _sf["stor"].append(None)
        antall, duplikat = lagre_kupong_til_sheets(_kamper, _sf)
        _totalt_lagret += antall
    if _totalt_lagret > 0:
        st.toast(f"Kupong lagret til historikk ({_totalt_lagret} kamper)")

# ─────────────────────────────────────────────
# TABS: ANALYSE, HISTORIKK OG BACKTEST
# ─────────────────────────────────────────────

# Sjekk om backtest-resultater finnes
_backtest_results_path = os.path.join(os.path.dirname(__file__) or ".", "backtest_results.json")
_backtest_details_path = os.path.join(os.path.dirname(__file__) or ".", "backtest_details.csv")
_has_backtest = os.path.exists(_backtest_results_path)

tab_names = ["Analyse", "Spillforslag"]
if sheets_available():
    tab_names.append("Historikk")
# if _has_backtest:
#     tab_names.append("Backtest")

tabs = st.tabs(tab_names)
tab_analyse = tabs[0]
tab_spillforslag = tabs[1]
tab_historikk = tabs[tab_names.index("Historikk")] if "Historikk" in tab_names else None
tab_backtest = tabs[tab_names.index("Backtest")] if "Backtest" in tab_names else None

# ═══════════════════════════════════════════════
# ANALYSE-FANEN
# ═══════════════════════════════════════════════

with tab_analyse:

    # ─────────────────────────────────────────────
    # KAMPVISNING (integrert sammendrag + detaljer)
    # ─────────────────────────────────────────────

    def _kamprad_html(a):
        """Rendrer én kompakt kamprad som HTML-div med flex-layout."""
        rad = a["rad"]
        pr = a["poisson_res"]
        avvik = a["avvik_poi"]
        max_av = a["max_poi_avvik"]

        # Kampnavn + liga
        kamp_navn = (
            f'<div class="kamp-navn">{rad["Kamp"]}'
            f'<br><span class="liga">{rad["Liga"]} — {rad["Dato"]}</span></div>'
        )

        # Folk prob-bar (vis tall bare hvis segment > 8%)
        fh, fu, fb = a["folk_h"], a["folk_u"], a["folk_b"]
        fh_t = str(fh) if fh > 8 else ""
        fu_t = str(fu) if fu > 8 else ""
        fb_t = str(fb) if fb > 8 else ""
        folk_bar = (
            f'<div class="kamp-col">'
            f'<div class="col-label">Folk H / U / B</div>'
            f'<div class="prob-bar">'
            f'<div class="prob-seg-h" style="width:{fh}%">{fh_t}</div>'
            f'<div class="prob-seg-u" style="width:{fu}%">{fu_t}</div>'
            f'<div class="prob-seg-b" style="width:{fb}%">{fb_t}</div>'
            f'</div></div>'
        )

        # Modell prob-bar (vis tall bare hvis segment > 8%)
        if pr:
            mh, mu, mb = pr["H"], pr["U"], pr["B"]
            mh_t = str(mh) if mh > 8 else ""
            mu_t = str(mu) if mu > 8 else ""
            mb_t = str(mb) if mb > 8 else ""
            modell_bar = (
                f'<div class="kamp-col">'
                f'<div class="col-label">Modell H / U / B</div>'
                f'<div class="prob-bar model-bar">'
                f'<div class="prob-seg-h" style="width:{mh}%">{mh_t}</div>'
                f'<div class="prob-seg-u" style="width:{mu}%">{mu_t}</div>'
                f'<div class="prob-seg-b" style="width:{mb}%">{mb_t}</div>'
                f'</div></div>'
            )
        else:
            modell_bar = '<div class="kamp-col"><div class="col-label">Modell H / U / B</div><span style="color:#b0b0b0">–</span></div>'

        # Forventede mål
        if pr:
            maal_col = (
                f'<div class="kamp-col">'
                f'<div class="col-label">Forv. mål</div>'
                f'<span class="score-badge">'
                f'<span class="goals">{pr["lambda_h"]}</span>'
                f'<span class="dash">–</span>'
                f'<span class="goals">{pr["lambda_b"]}</span>'
                f'</span></div>'
            )
        else:
            maal_col = '<div class="kamp-col"><div class="col-label">Forv. mål</div><span style="color:rgba(128,128,128,0.4)">–</span></div>'

        # Modellnivå
        nivaa = a["modell_nivaa"]
        nivaa_farger = {
            "Dyp (form+xG)": "#5a9e74", "Dyp (form)": "#5a86a8",
            "Basis (sesongsnitt)": "#b8a050", "Ingen modell": "#b0b0b0",
        }
        nbg = nivaa_farger.get(nivaa, "#9ca3af")
        nivaa_col = (
            f'<div class="kamp-col">'
            f'<div class="col-label">Modellnivå</div>'
            f'<span class="modell-badge" style="background:{nbg};color:#fff">{nivaa}</span></div>'
        )

        # Verdisignal — prikk + tekstlabel
        if max_av >= 12:
            beste = max(avvik, key=lambda x: abs(x) if x else 0, default=None)
            sig_cls = "sterk"
            sig_label = "Sterk"
            tip = f"{abs(beste):.0f}pp avvik" if beste else ""
        elif max_av >= 8:
            sig_cls = "mild"
            sig_label = "Mild"
            beste = max(avvik, key=lambda x: abs(x) if x else 0, default=None)
            tip = f"{abs(beste):.0f}pp avvik" if beste else ""
        else:
            sig_cls = "noytral"
            sig_label = "Nøytral"
            tip = ""
        signal_col = (
            f'<div class="kamp-col">'
            f'<div class="col-label">Signal</div>'
            f'<span class="signal-wrap">'
            f'<span class="signal-dot {sig_cls}" title="{tip}"></span>'
            f'<span class="signal-label {sig_cls}">{sig_label}</span>'
            f'</span></div>'
        )

        return f'<div class="kamprad">{kamp_navn}{folk_bar}{modell_bar}{maal_col}{nivaa_col}{signal_col}</div>'

    def _kort_kommentar(a):
        """Genererer en kort faktabasert kommentar om styrkeforholdet i kampen."""
        pr = a["poisson_res"]
        if not pr:
            return None
        hjemme = a["rad"]["Hjemmelag"]
        borte = a["rad"]["Bortelag"]
        deler = []

        # Styrkerating — hvem har bedre angrep/forsvar basert på sesongstatistikk
        s = pr.get("styrke")
        if s:
            h_atk, h_def = s["home_attack"], s["home_defense"]
            b_atk, b_def = s["away_attack"], s["away_defense"]
            h_tot = h_atk + h_def
            b_tot = b_atk + b_def
            if h_tot > b_tot + 0.3:
                if h_atk > b_atk + 0.15 and h_def > b_def + 0.15:
                    deler.append(f"{hjemme} er sterkere både i angrep og forsvar denne sesongen")
                elif h_atk > b_atk + 0.15:
                    deler.append(f"{hjemme} har et klart sterkere angrep, men jevnere forsvar")
                else:
                    deler.append(f"{hjemme} har et solidere forsvar og hjemmebanefordel")
            elif b_tot > h_tot + 0.3:
                if b_atk > h_atk + 0.15 and b_def > h_def + 0.15:
                    deler.append(f"{borte} er sterkere i både angrep og forsvar, selv på bortebane")
                elif b_atk > h_atk + 0.15:
                    deler.append(f"{borte} har et sterkere angrep basert på sesongen")
                else:
                    deler.append(f"{borte} har et solidere forsvar til tross for bortebane")
            else:
                deler.append("Lagene er jevne på sesongstatistikken")

        # Form — hvem er i best form akkurat nå
        hf = a.get("h_form")
        bf = a.get("b_form")
        if hf and bf and hf.get("scoret_snitt") is not None and bf.get("scoret_snitt") is not None:
            h_form_score = hf["scoret_snitt"] - hf["innsluppet_snitt"]
            b_form_score = bf["scoret_snitt"] - bf["innsluppet_snitt"]
            if h_form_score > b_form_score + 0.8:
                deler.append(f"{hjemme} er i klart bedre form hjemme ({hf['scoret_snitt']:.1f} scoret, {hf['innsluppet_snitt']:.1f} innsluppet per kamp)")
            elif b_form_score > h_form_score + 0.8:
                deler.append(f"{borte} er i bedre form borte ({bf['scoret_snitt']:.1f} scoret, {bf['innsluppet_snitt']:.1f} innsluppet per kamp)")

        # Forventet mål — hvem forventes å dominere
        lh, lb = pr.get("lambda_h"), pr.get("lambda_b")
        if lh is not None and lb is not None:
            total = lh + lb
            if lh > lb + 0.5:
                deler.append(f"forventet målbilde {lh:.1f}–{lb:.1f} i favør {hjemme}")
            elif lb > lh + 0.5:
                deler.append(f"forventet målbilde {lh:.1f}–{lb:.1f} i favør {borte}")
            elif total > 3.0:
                deler.append(f"jevn kamp med høy forventet målsum ({total:.1f})")
            elif total < 2.0:
                deler.append(f"jevn kamp, men lav forventet målsum ({total:.1f})")

        # H2H — historisk dominans
        opps = a.get("h2h_opps")
        if opps and opps.get("kamper", 0) >= 3:
            seire = opps["seire"]
            tap = opps["tap"]
            kamper = opps["kamper"]
            if seire >= kamper * 0.7:
                deler.append(f"{hjemme} har vunnet {seire} av {kamper} innbyrdes oppgjør")
            elif tap >= kamper * 0.7:
                deler.append(f"{borte} har vunnet {tap} av {kamper} innbyrdes oppgjør")

        return ". ".join(deler[:3]) + "." if deler else None

    # ── Brand header ──
    st.markdown('<div class="brand-header">TipsMaskinen</div>', unsafe_allow_html=True)

    # ── Legend (fargekode-forklaring, vises én gang) ──
    st.markdown(
        '<div class="legend">'
        '<span class="legend-item"><span class="legend-swatch" style="background:#7bac8e"></span> H (hjemme)</span>'
        '<span class="legend-item"><span class="legend-swatch" style="background:#b8af88"></span> U (uavgjort)</span>'
        '<span class="legend-item"><span class="legend-swatch" style="background:#be9484"></span> B (borte)</span>'
        '<span style="color:#d0d0d0">|</span>'
        '<span class="legend-item"><span class="signal-dot sterk" style="width:8px;height:8px"></span> Sterk</span>'
        '<span class="legend-item"><span class="signal-dot mild" style="width:8px;height:8px"></span> Mild</span>'
        '<span class="legend-item"><span class="signal-dot noytral" style="width:8px;height:8px"></span> Nøytral</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    verdikamper = 0

    for dag in df_vis["Dag"].unique():
        dag_analyser = [a for a in analyse_resultater if a["rad"]["Dag"] == dag]
        datoer = [a["rad"]["Dato"] for a in dag_analyser if a["rad"]["Dato"]]
        dato_str = min(datoer) if datoer else ""
        # Kupong-header med metadata
        _nivaaer = set(a["modell_nivaa"] for a in dag_analyser)
        _nivaa_str = ", ".join(_nivaaer)
        st.markdown(
            f'<p class="kupong-title">{dag}kupong</p>'
            f'<p class="kupong-meta">{dato_str} · {len(dag_analyser)} kamper · {_nivaa_str}</p>',
            unsafe_allow_html=True,
        )

        for a in dag_analyser:
            rad = a["rad"]
            hjemmelag = rad["Hjemmelag"]
            bortelag = rad["Bortelag"]
            liga = rad["Liga"]
            folk_h, folk_u, folk_b = a["folk_h"], a["folk_u"], a["folk_b"]
            poisson_res = a["poisson_res"]
            avvik_poi = a["avvik_poi"]
            max_poi_avvik = a["max_poi_avvik"]

            if bare_verdi and max_poi_avvik < 8:
                continue
            if max_poi_avvik < min_avvik:
                continue
            if max_poi_avvik >= 8:
                verdikamper += 1

            # 1) Kompakt kamprad (alltid synlig)
            st.markdown(_kamprad_html(a), unsafe_allow_html=True)

            # Kort kommentar + avvik-badge
            _kommentar = _kort_kommentar(a)
            _avvik_html = ""
            if max_poi_avvik >= 8:
                _avvik_html = f'<span class="avvik-badge">{max_poi_avvik:.0f}pp avvik</span>'
            if _kommentar or _avvik_html:
                _tekst = f'💡 {_kommentar}' if _kommentar else ""
                st.markdown(
                    f'<div class="kommentar-rad">'
                    f'<span class="kommentar-tekst">{_tekst}</span>'
                    f'{_avvik_html}</div>',
                    unsafe_allow_html=True,
                )

            # 2) Expanderbart detaljpanel
            with st.expander("Vis detaljer"):

                # Modellnivå-badge
                st.markdown(modell_nivaa_badge(a["modell_nivaa"]), unsafe_allow_html=True)

                # ════ HOVEDDEL: to kolonner ════
                k1, k2 = st.columns(2)

                # ── Kolonne 1: Folkerekke ──
                with k1:
                    st.markdown("#### 👥 Folkerekka")
                    for label, val in [("Hjemme (H)", folk_h), ("Uavgjort (U)", folk_u), ("Borte (B)", folk_b)]:
                        st.markdown(f"**{label}:** {val}%")
                        st.progress(int(val))

                # ── Kolonne 2: Poisson-modell (Dyp Analyse) ──
                with k2:
                    st.markdown("#### 🔢 Poisson-modell (Dyp Analyse)")
                    if poisson_res:
                        poi_h = a["poi_h"]
                        poi_u = a["poi_u"]
                        poi_b = a["poi_b"]
                        for label, poi_val, folk_val in [
                            ("Hjemme (H)", poi_h, folk_h),
                            ("Uavgjort (U)", poi_u, folk_u),
                            ("Borte (B)", poi_b, folk_b),
                        ]:
                            avvik = round(poi_val - folk_val, 1)
                            av_pil = pil(avvik)
                            av_farge = farge(avvik)
                            prefix = "+" if avvik > 0 else ""
                            st.markdown(
                                f"**{label}:** {poi_val}% "
                                f"<span style='color:{av_farge}'>{av_pil} {prefix}{avvik}pp vs folk</span>",
                                unsafe_allow_html=True,
                            )
                        st.caption(f"Forventet mål: {poisson_res['lambda_h']} – {poisson_res['lambda_b']}")

                        # Mest sannsynlige resultater
                        topp = poisson_res.get("topp_resultater", [])
                        if topp:
                            topp_str = "  |  ".join(f"**{r[0]}** ({r[1]}%)" for r in topp)
                            st.markdown(f"Mest sannsynlig: {topp_str}")
                    else:
                        st.info("Ikke nok statistikk for Poisson-beregning")
                        if not a["h_stats"]:
                            st.caption(f"Fant ikke {hjemmelag} i FotMob-tabellen")
                        if not a["b_stats"]:
                            st.caption(f"Fant ikke {bortelag} i FotMob-tabellen")

                # ════ DETALJERT ANALYSE (under kolonnene) ════
                if poisson_res or a["h_team_data"] or a["b_team_data"]:
                    st.divider()

                    # Styrkerating
                    if poisson_res and poisson_res.get("styrke"):
                        st.markdown("#### Styrkerating")
                        s = poisson_res["styrke"]
                        sc1, sc2 = st.columns(2)
                        with sc1:
                            st.markdown(f"**{hjemmelag} (hjemme)**")
                            st.markdown(f"⚔️ Attack: **{s['home_attack']:.2f}**  |  🛡️ Defense: **{s['home_defense']:.2f}**")
                            if a["h_form"]:
                                hf = a["h_form"]
                                st.caption(f"Siste {hf['kamper']} hjemmekamper: {hf['scoret_snitt']:.1f} scoret, {hf['innsluppet_snitt']:.1f} innsluppet per kamp")
                        with sc2:
                            st.markdown(f"**{bortelag} (borte)**")
                            st.markdown(f"⚔️ Attack: **{s['away_attack']:.2f}**  |  🛡️ Defense: **{s['away_defense']:.2f}**")
                            if a["b_form"]:
                                bf = a["b_form"]
                                st.caption(f"Siste {bf['kamper']} bortekamper: {bf['scoret_snitt']:.1f} scoret, {bf['innsluppet_snitt']:.1f} innsluppet per kamp")

                    # Form (siste 5)
                    if a["h_team_data"] or a["b_team_data"]:
                        st.markdown("#### Form (siste 5)")
                        f1, f2 = st.columns(2)
                        with f1:
                            h_form_data = a["h_team_data"]["form"] if a["h_team_data"] else []
                            if h_form_data:
                                st.markdown(f"**{hjemmelag}:** {form_bokser(h_form_data)}", unsafe_allow_html=True)
                            else:
                                st.caption(f"{hjemmelag}: form ikke tilgjengelig")
                        with f2:
                            b_form_data = a["b_team_data"]["form"] if a["b_team_data"] else []
                            if b_form_data:
                                st.markdown(f"**{bortelag}:** {form_bokser(b_form_data)}", unsafe_allow_html=True)
                            else:
                                st.caption(f"{bortelag}: form ikke tilgjengelig")

                    # H2H
                    if a["h2h_kamper"]:
                        st.markdown("#### Innbyrdes (H2H)")
                        opps = a["h2h_opps"]
                        if opps:
                            st.markdown(
                                f"**{hjemmelag}** {opps['seire']}-{opps['uavgjort']}-{opps['tap']} "
                                f"({opps['scoret']} scoret, {opps['innsluppet']} innsluppet i {opps['kamper']} kamper)"
                            )
                        for fx in a["h2h_kamper"]:
                            st.caption(f"{fx['home_name']} {fx['home_goals']}-{fx['away_goals']} {fx['away_name']}")

                # ════ LAGSTATISTIKK ════
                if a["h_stats"] or a["b_stats"]:
                    st.divider()
                    st.markdown("#### Lagstatistikk fra FotMob (sesongen)")
                    s1, s2 = st.columns(2)

                    with s1:
                        st.markdown(f"**🏠 {hjemmelag} — hjemmekamper**")
                        h_stats = a["h_stats"]
                        if h_stats:
                            h_sc_snitt = maal_snitt(h_stats.get("hjemme_scoret", 0), h_stats.get("hjemme_spilt", 1))
                            h_in_snitt = maal_snitt(h_stats.get("hjemme_innsluppet", 0), h_stats.get("hjemme_spilt", 1))
                            hj_sp = h_stats.get("hjemme_spilt", "–")
                            hj_sc = h_stats.get("hjemme_scoret", "–")
                            hj_in = h_stats.get("hjemme_innsluppet", "–")
                            c1a, c1b, c1c = st.columns(3)
                            c1a.metric("Kamper", hj_sp)
                            c1b.metric("Scoret", f"{hj_sc} ({h_sc_snitt}/k)")
                            c1c.metric("Innsluppet", f"{hj_in} ({h_in_snitt}/k)")
                        else:
                            st.caption("Statistikk ikke tilgjengelig")

                    with s2:
                        st.markdown(f"**✈️ {bortelag} — bortekamper**")
                        b_stats = a["b_stats"]
                        if b_stats:
                            b_sc_snitt = maal_snitt(b_stats.get("borte_scoret", 0), b_stats.get("borte_spilt", 1))
                            b_in_snitt = maal_snitt(b_stats.get("borte_innsluppet", 0), b_stats.get("borte_spilt", 1))
                            bo_sp = b_stats.get("borte_spilt", "–")
                            bo_sc = b_stats.get("borte_scoret", "–")
                            bo_in = b_stats.get("borte_innsluppet", "–")
                            c2a, c2b, c2c = st.columns(3)
                            c2a.metric("Kamper", bo_sp)
                            c2b.metric("Scoret", f"{bo_sc} ({b_sc_snitt}/k)")
                            c2c.metric("Innsluppet", f"{bo_in} ({b_in_snitt}/k)")
                        else:
                            st.caption("Statistikk ikke tilgjengelig")

                # ════ VERDIOPPSUMMERING ════
                beste_poi = max(
                    [("Hjemme", avvik_poi[0]), ("Uavgjort", avvik_poi[1]), ("Borte", avvik_poi[2])],
                    key=lambda x: abs(x[1]) if x[1] is not None else 0,
                )
                if beste_poi[1] is not None and beste_poi[1] > 8:
                    st.success(f"🟢 **Mulig verdi:** Modellen ser {beste_poi[1]:.1f}pp MER sannsynlighet for **{beste_poi[0]}** enn folkerekka")
                elif beste_poi[1] is not None and beste_poi[1] < -8:
                    st.warning(f"🔴 **Obs:** Folk overtipper **{beste_poi[0]}** med {abs(beste_poi[1]):.1f}pp vs. modellen")

                # ════ KORT FORKLARING ════
                if poisson_res:
                    forklaring_deler = []

                    # Hvem modellen favoriserer
                    poi_h_v = a["poi_h"]
                    poi_u_v = a["poi_u"]
                    poi_b_v = a["poi_b"]
                    fav_map = {"H": hjemmelag, "U": "uavgjort", "B": bortelag}
                    modell_fav = max({"H": poi_h_v, "U": poi_u_v, "B": poi_b_v}, key={"H": poi_h_v, "U": poi_u_v, "B": poi_b_v}.get)

                    fav_pct = {"H": poi_h_v, "U": poi_u_v, "B": poi_b_v}[modell_fav]
                    if modell_fav == "U":
                        forklaring_deler.append(f"Modellen vurderer lagene som jevne og heller mot uavgjort ({poi_u_v:.0f}%)")
                    else:
                        forklaring_deler.append(f"Modellen favoriserer **{fav_map[modell_fav]}** ({fav_pct:.0f}%)")

                    # Styrkeforskjell
                    s = poisson_res.get("styrke")
                    if s:
                        h_total = s["home_attack"] + s["home_defense"]
                        b_total = s["away_attack"] + s["away_defense"]
                        if abs(h_total - b_total) > 0.3:
                            sterkere = hjemmelag if h_total > b_total else bortelag
                            forklaring_deler.append(f"{sterkere} har sterkere rating basert på sesongstatistikk")
                        else:
                            forklaring_deler.append("lagene har tilnærmet lik styrkerating")

                    # Form
                    hf = a.get("h_form")
                    bf = a.get("b_form")
                    if hf and bf and hf.get("scoret_snitt") is not None and bf.get("scoret_snitt") is not None:
                        h_form_score = hf["scoret_snitt"] - hf["innsluppet_snitt"]
                        b_form_score = bf["scoret_snitt"] - bf["innsluppet_snitt"]
                        if h_form_score > b_form_score + 0.5:
                            forklaring_deler.append(f"{hjemmelag} er i bedre form på hjemmebane")
                        elif b_form_score > h_form_score + 0.5:
                            forklaring_deler.append(f"{bortelag} er i bedre form på bortebane")

                    # Forventet mål
                    lh = poisson_res.get("lambda_h")
                    lb = poisson_res.get("lambda_b")
                    if lh is not None and lb is not None:
                        if lh > lb + 0.4:
                            forklaring_deler.append(f"{hjemmelag} forventes å score flere mål ({lh:.1f} vs {lb:.1f})")
                        elif lb > lh + 0.4:
                            forklaring_deler.append(f"{bortelag} forventes å score flere mål ({lb:.1f} vs {lh:.1f})")
                        else:
                            forklaring_deler.append(f"jevn forventet målproduksjon ({lh:.1f} – {lb:.1f})")

                    # Avvik mot folk
                    avvik_h = avvik_poi[0] if avvik_poi[0] is not None else 0
                    avvik_u = avvik_poi[1] if avvik_poi[1] is not None else 0
                    avvik_b = avvik_poi[2] if avvik_poi[2] is not None else 0
                    max_a = max(avvik_h, avvik_u, avvik_b)
                    min_a = min(avvik_h, avvik_u, avvik_b)
                    if max_a > 8:
                        avvik_utfall = ["hjemmeseier", "uavgjort", "borteseier"][[avvik_h, avvik_u, avvik_b].index(max_a)]
                        forklaring_deler.append(f"folkerekka undervurderer {avvik_utfall} ifølge modellen")
                    elif min_a < -8:
                        avvik_utfall = ["hjemmeseier", "uavgjort", "borteseier"][[avvik_h, avvik_u, avvik_b].index(min_a)]
                        forklaring_deler.append(f"folkerekka overvurderer {avvik_utfall} ifølge modellen")

                    if forklaring_deler:
                        st.info("💡 **Kort oppsummert:** " + ". ".join(forklaring_deler) + ".")

    st.divider()

    # ─── Bunntall ───
    col1, col2, col3 = st.columns(3)
    col1.metric("Kamper vist", len(df_vis))
    col2.metric("Verdisignaler (>8pp)", verdikamper)
    col3.metric("Ligaer med statistikk", len(liga_data_cache))

    st.caption(f"Data: NT API + FotMob · Sist oppdatert: {datetime.now().strftime('%H:%M:%S')} · Dyp Poisson-modell: styrke + form + xG")

# ═══════════════════════════════════════════════
# SPILLFORSLAG-FANEN
# ═══════════════════════════════════════════════

def _kupong_html(forslag, analyse_resultater, profil_navn, faktisk_rader):
    """Bygger modernisert HTML-kupong med badges og fargede rader."""
    rows_html = ""
    for i, (f, a) in enumerate(zip(forslag, analyse_resultater)):
        if not f:
            continue
        rad = a["rad"]
        tegn = f["tegn"]
        avvik = f.get("avvik", {})
        row_cls = f"kupong-row-{f['type']}"

        # H/U/B celler med badge-stil
        celler = ""
        for utfall in ["H", "U", "B"]:
            if utfall in tegn:
                er_verdi = avvik.get(utfall, 0) > 5
                badge_cls = "aktiv-verdi" if er_verdi else "aktiv-modell"
                celler += (
                    f'<td style="text-align:center">'
                    f'<span class="tegn-badge aktiv {badge_cls}">{utfall}</span></td>'
                )
            else:
                celler += (
                    f'<td style="text-align:center">'
                    f'<span class="tegn-badge inaktiv">·</span></td>'
                )

        # Type chip
        type_chip = f'<span class="type-chip {f["type"]}">{f["type"][0].upper()}</span>'

        # Begrunnelse chip
        begr = f'<span class="begrunnelse-chip" title="{f["begrunnelse"]}">{f["begrunnelse"]}</span>'

        rows_html += (
            f'<tr class="{row_cls}">'
            f'<td style="font-size:13px"><strong>{i+1}.</strong> {rad["Kamp"]}</td>'
            f'{celler}'
            f'<td style="text-align:center">{type_chip}</td>'
            f'<td>{begr}</td>'
            f'</tr>'
        )

    return f"""
    <table class="kupong-table">
    <thead><tr>
        <th style="text-align:left;min-width:200px">Kamp</th>
        <th style="width:45px">H</th>
        <th style="width:45px">U</th>
        <th style="width:45px">B</th>
        <th style="width:60px">Type</th>
        <th style="text-align:left">Begrunnelse</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
    </table>
    """


with tab_spillforslag:
    st.subheader("Spillforslag")

    if not neste_kupong_analyser:
        st.info("Ingen kamper å lage forslag for.")
    else:
        st.markdown(
            f"**{neste_kupong_dag}kupong** — {neste_kupong_dato} — "
            f"{len(neste_kupong_analyser)} kamper"
        )
        st.caption(
            "Systemforslag basert på Poisson-modellen. "
            "Spiller mot folket der modellen ser verdi. "
            "Pris = antall rekker × 1 kr."
        )

        # Forklaring fargekoder
        st.markdown(
            '<span style="display:inline-block;width:14px;height:14px;background:#1a6b3c;'
            'border-radius:2px;vertical-align:middle"></span> Modell-valg &nbsp;&nbsp;'
            '<span style="display:inline-block;width:14px;height:14px;background:#b8860b;'
            'border-radius:2px;vertical-align:middle"></span> Verdi-spill (>5pp vs folk)',
            unsafe_allow_html=True,
        )
        st.markdown("")

        for profil_key, sf_data in spillforslag_alle.items():
            profil = sf_data["profil"]
            forslag = sf_data["forslag"]
            faktisk_rader = sf_data["rader"]
            kupong_analyser = sf_data["analyser"]

            if not forslag:
                continue

            antall_singler = sum(1 for f in forslag if f and f["type"] == "singel")
            antall_dobler = sum(1 for f in forslag if f and f["type"] == "dobbel")
            antall_tripler = sum(1 for f in forslag if f and f["type"] == "trippel")

            st.markdown(f"### {profil['navn']} spill — {faktisk_rader} rekker ({faktisk_rader} kr)")

            # Nøkkeltall som styled HTML-kort
            kpi_html = f"""
            <div class="kpi-row">
                <div class="kpi-card">
                    <div class="kpi-icon">#</div>
                    <div class="kpi-value">{faktisk_rader}</div>
                    <div class="kpi-label">Rekker</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-icon">1</div>
                    <div class="kpi-value">{antall_singler}</div>
                    <div class="kpi-label">Singler</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-icon">2</div>
                    <div class="kpi-value">{antall_dobler}</div>
                    <div class="kpi-label">Dobler</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-icon">3</div>
                    <div class="kpi-value">{antall_tripler}</div>
                    <div class="kpi-label">Tripler</div>
                </div>
            </div>
            """
            st.markdown(kpi_html, unsafe_allow_html=True)

            # Kupong-tabell i HTML
            html = _kupong_html(forslag, kupong_analyser, profil["navn"], faktisk_rader)
            st.markdown(html, unsafe_allow_html=True)

            st.divider()

# ═══════════════════════════════════════════════
# HISTORIKK-FANEN
# ═══════════════════════════════════════════════

if tab_historikk is not None:
    with tab_historikk:
        if not sheets_available():
            st.info("Historikk krever Google Sheets-oppsett. Se dokumentasjonen for instruksjoner.")
        else:
            st.subheader("Historikk")

            # Oppdater resultater automatisk + manuell knapp
            hcol1, hcol2 = st.columns([3, 1])
            with hcol2:
                if st.button("Oppdater resultater"):
                    st.cache_data.clear()
                    with st.spinner("Oppdaterer resultater fra FotMob..."):
                        antall_oppdatert = oppdater_resultater()
                    if antall_oppdatert > 0:
                        st.success(f"Oppdaterte {antall_oppdatert} kamper med resultater")
                        st.cache_data.clear()
                    else:
                        st.info("Ingen nye resultater å oppdatere")

            # Hent historikk
            hist_df = hent_historikk_data()

            if hist_df.empty:
                st.info("Ingen historikk ennå. Kuponger lagres automatisk hver gang du laster analysen.")
            else:
                # Konverter numeriske kolonner
                for col in ["folk_h", "folk_u", "folk_b", "modell_h", "modell_u", "modell_b", "max_avvik"]:
                    if col in hist_df.columns:
                        hist_df[col] = pd.to_numeric(hist_df[col], errors="coerce")

                # Filtrer kamper med og uten resultat
                har_resultat = hist_df[hist_df["resultat"].astype(str).isin(["H", "U", "B"])].copy()
                venter = hist_df[~hist_df["resultat"].astype(str).isin(["H", "U", "B"])].copy()

                # ─── Nøkkeltall ───
                if not har_resultat.empty:
                    totalt = len(har_resultat)
                    modell_treff = (har_resultat["modell_korrekt"].astype(str) == "true").sum()
                    modell_rate = round(modell_treff / totalt * 100, 1) if totalt > 0 else 0

                    verdi_kamper = har_resultat[har_resultat["verdi_tips"].astype(str).isin(["H", "U", "B"])]
                    verdi_totalt = len(verdi_kamper)
                    verdi_treff = (verdi_kamper["verdi_korrekt"].astype(str) == "true").sum() if verdi_totalt > 0 else 0
                    verdi_rate = round(verdi_treff / verdi_totalt * 100, 1) if verdi_totalt > 0 else 0

                    folk_treff = (har_resultat["folk_korrekt"].astype(str) == "true").sum()
                    folk_rate = round(folk_treff / totalt * 100, 1) if totalt > 0 else 0

                    modell_vs_folk = modell_treff - folk_treff

                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Kamper tipset", totalt)
                    m2.metric("Modell-treffrate", f"{modell_rate}%")
                    m3.metric("Verdi-treffrate", f"{verdi_rate}%" if verdi_totalt > 0 else "–",
                              help=f"Basert på {verdi_totalt} kamper med verdisignal")
                    m4.metric("Folk-treffrate", f"{folk_rate}%")
                    m5.metric("Modell vs Folk", f"{'+' if modell_vs_folk > 0 else ''}{modell_vs_folk} kamper",
                              delta=f"{'+' if modell_vs_folk > 0 else ''}{modell_vs_folk}",
                              delta_color="normal")

                    # Spillforslag-treffrate
                    spill_cols = [
                        ("spill_lite_korrekt", "Lite (72 kr)"),
                        ("spill_medium_korrekt", "Medium (256 kr)"),
                        ("spill_stor_korrekt", "Stort (384 kr)"),
                    ]
                    spill_stats = []
                    for col_name, label in spill_cols:
                        if col_name in har_resultat.columns:
                            col_vals = har_resultat[col_name].astype(str)
                            spill_n = col_vals.isin(["true", "false"]).sum()
                            if spill_n > 0:
                                spill_treff = (col_vals == "true").sum()
                                spill_pct = round(spill_treff / spill_n * 100, 1)
                                spill_stats.append((label, spill_treff, spill_n, spill_pct))

                    if spill_stats:
                        st.markdown("**Spillforslag-treffrate (per kamp)**")
                        sp_cols = st.columns(len(spill_stats))
                        for j, (label, treff, n_sp, pct) in enumerate(spill_stats):
                            sp_cols[j].metric(label, f"{pct}% ({treff}/{n_sp})")

                    st.divider()

                # ─── Statistikk-seksjon ───
                if not har_resultat.empty:
                    stat_col1, stat_col2 = st.columns(2)

                    with stat_col1:
                        st.markdown("#### Treffrate per liga")
                        liga_stats = []
                        for liga_navn in sorted(har_resultat["liga"].unique()):
                            liga_df = har_resultat[har_resultat["liga"] == liga_navn]
                            n = len(liga_df)
                            mt = (liga_df["modell_korrekt"].astype(str) == "true").sum()
                            ft = (liga_df["folk_korrekt"].astype(str) == "true").sum()
                            liga_stats.append({
                                "Liga": liga_navn,
                                "n": n,
                                "Modell": f"{round(mt / n * 100, 1)}%",
                                "Folk": f"{round(ft / n * 100, 1)}%",
                            })
                        if liga_stats:
                            st.dataframe(pd.DataFrame(liga_stats), use_container_width=True, hide_index=True)

                    with stat_col2:
                        st.markdown("#### Treffrate per modellnivå")
                        nivaa_stats = []
                        for nivaa in har_resultat["modell_nivaa"].unique():
                            nivaa_df = har_resultat[har_resultat["modell_nivaa"] == nivaa]
                            n = len(nivaa_df)
                            mt = (nivaa_df["modell_korrekt"].astype(str) == "true").sum()
                            nivaa_stats.append({
                                "Modellnivå": nivaa,
                                "n": n,
                                "Treffrate": f"{round(mt / n * 100, 1)}%",
                            })
                        if nivaa_stats:
                            st.dataframe(pd.DataFrame(nivaa_stats), use_container_width=True, hide_index=True)

                    st.divider()

                # ─── Kuponger ───
                st.markdown("#### Tippekuponger")

                # Filtre
                hist_fil1, hist_fil2, hist_fil3 = st.columns(3)
                with hist_fil1:
                    alle_ligaer = sorted(hist_df["liga"].dropna().unique().tolist())
                    valgt_liga = st.multiselect("Liga", options=alle_ligaer, default=alle_ligaer, key="hist_liga")
                with hist_fil2:
                    kun_verdi = st.checkbox("Kun verdikamper", key="hist_verdi")
                with hist_fil3:
                    vis_type = st.radio("Vis", ["Alle", "Med resultat", "Venter"], key="hist_vis", horizontal=True)

                # Appliser filtre
                vis_df = hist_df.copy()
                if valgt_liga:
                    vis_df = vis_df[vis_df["liga"].isin(valgt_liga)]
                if kun_verdi:
                    vis_df = vis_df[vis_df["verdi_tips"].astype(str).isin(["H", "U", "B"])]
                if vis_type == "Med resultat":
                    vis_df = vis_df[vis_df["resultat"].astype(str).isin(["H", "U", "B"])]
                elif vis_type == "Venter":
                    vis_df = vis_df[~vis_df["resultat"].astype(str).isin(["H", "U", "B"])]

                if vis_df.empty:
                    st.info("Ingen kamper matcher filtrene")
                else:
                    # Grupper per kupong, sorter nyeste først
                    kupong_ids = vis_df["kupong_id"].unique().tolist()
                    kupong_ids.reverse()

                    for kid in kupong_ids:
                        k_df = vis_df[vis_df["kupong_id"] == kid]
                        if k_df.empty:
                            continue

                        # Parse kupong-info fra kupong_id (format: "YYYY-MM-DD_Dagtype")
                        kid_parts = str(kid).split("_", 1)
                        kupong_dato = kid_parts[0] if kid_parts else ""
                        kupong_dag = kid_parts[1] if len(kid_parts) > 1 else ""

                        # Beregn kupongstatistikk
                        k_har_res = k_df[k_df["resultat"].astype(str).isin(["H", "U", "B"])]
                        k_n = len(k_df)
                        k_n_res = len(k_har_res)
                        k_modell = (k_har_res["modell_korrekt"].astype(str) == "true").sum() if k_n_res > 0 else 0
                        k_folk = (k_har_res["folk_korrekt"].astype(str) == "true").sum() if k_n_res > 0 else 0

                        # Lag tittel
                        if k_n_res > 0:
                            k_modell_pct = round(k_modell / k_n_res * 100)
                            k_folk_pct = round(k_folk / k_n_res * 100)
                            status_str = f"Modell {k_modell}/{k_n_res} ({k_modell_pct}%)  ·  Folk {k_folk}/{k_n_res} ({k_folk_pct}%)"
                        elif k_n_res == 0 and k_n > 0:
                            status_str = f"⏳ {k_n} kamper venter på resultat"
                        else:
                            status_str = ""

                        kupong_tittel = f"{kupong_dag}kupong {kupong_dato}  —  {k_n} kamper  ·  {status_str}"

                        with st.expander(kupong_tittel, expanded=(kid == kupong_ids[0])):
                            # Nøkkeltall for denne kupongen
                            if k_n_res > 0:
                                kc1, kc2, kc3, kc4 = st.columns(4)
                                kc1.metric("Kamper", k_n)
                                kc2.metric("Modell", f"{k_modell}/{k_n_res}")
                                kc3.metric("Folk", f"{k_folk}/{k_n_res}")
                                k_diff = k_modell - k_folk
                                kc4.metric("Modell vs Folk", f"{'+' if k_diff > 0 else ''}{k_diff}",
                                           delta=f"{'+' if k_diff > 0 else ''}{k_diff}",
                                           delta_color="normal")

                            # Kamptabell
                            display_rows = []
                            for _, row in k_df.iterrows():
                                kamp = f"{row.get('hjemmelag', '')} - {row.get('bortelag', '')}"
                                folk_str = f"{row.get('folk_h', '')}/{row.get('folk_u', '')}/{row.get('folk_b', '')}"
                                modell_str = f"{row.get('modell_h', '')}/{row.get('modell_u', '')}/{row.get('modell_b', '')}"
                                res = str(row.get("resultat", ""))
                                if res in ("H", "U", "B"):
                                    modell_ok = "✅" if str(row.get("modell_korrekt", "")) == "true" else "❌"
                                    folk_ok = "✅" if str(row.get("folk_korrekt", "")) == "true" else "❌"
                                else:
                                    res = "⏳"
                                    modell_ok = "–"
                                    folk_ok = "–"

                                avvik_val = row.get("max_avvik", 0)
                                try:
                                    avvik_float = float(avvik_val)
                                    avvik_str = f"{avvik_float:.1f}pp"
                                except (ValueError, TypeError):
                                    avvik_str = "–"

                                # Spillforslag-kolonner
                                sl = str(row.get("spill_lite", "")) or "–"
                                sm = str(row.get("spill_medium", "")) or "–"
                                ss = str(row.get("spill_stor", "")) or "–"

                                display_rows.append({
                                    "Kamp": kamp,
                                    "Liga": row.get("liga", ""),
                                    "Folk": folk_str,
                                    "Modell": modell_str,
                                    "Tips": row.get("modell_tips", ""),
                                    "Verdi": row.get("verdi_tips", "") or "–",
                                    "Avvik": avvik_str,
                                    "Lite": sl,
                                    "Med": sm,
                                    "Stor": ss,
                                    "Resultat": res,
                                    "M": modell_ok,
                                    "F": folk_ok,
                                })
                            st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

                    # Oppsummering under
                    st.caption(f"Viser {len(kupong_ids)} kuponger med totalt {len(vis_df)} kamper"
                               + (f" · ⏳ {len(venter)} kamper venter på resultater" if not venter.empty else ""))

# ═══════════════════════════════════════════════
# BACKTEST-FANEN
# ═══════════════════════════════════════════════

if tab_backtest is not None:
    with tab_backtest:
        st.subheader("Backtest-resultater")

        try:
            with open(_backtest_results_path, "r", encoding="utf-8") as _f:
                bt = json.load(_f)
        except Exception as _e:
            st.error(f"Kunne ikke lese backtest-resultater: {_e}")
            bt = None

        if bt:
            # Note
            if bt.get("note"):
                st.info(bt["note"])

            # ─── Nøkkeltall øverst ───
            bt_m1, bt_m2, bt_m3, bt_m4 = st.columns(4)
            bt_m1.metric("Kamper evaluert", bt.get("best_train_metrics", {}).get("n", 0) + bt.get("best_test_metrics", {}).get("n", 0))
            bt_m2.metric("Ligaer", len([l for l, m in bt.get("per_liga_best", {}).items() if m.get("n", 0) > 0]))
            bt_m3.metric("Standard accuracy", f"{bt.get('default_train_metrics', {}).get('accuracy', '?')}%")
            bt_m4.metric("Optimal accuracy", f"{bt.get('best_train_metrics', {}).get('accuracy', '?')}%",
                         delta=f"{bt.get('best_train_metrics', {}).get('accuracy', 0) - bt.get('default_train_metrics', {}).get('accuracy', 0):+.1f}pp")

            st.divider()

            # ─── Sammendrag: Standard vs Optimale parametre ───
            st.markdown("#### Parametersammenligning")
            _param_labels = {
                "form_weight": "Form-vekt (vs sesong)",
                "form_window": "Antall kamper i formvindu",
                "xg_weight": "xG-vekt",
                "value_threshold_pp": "Verdi-terskel (pp)",
                "lambda_min": "Min forventet mål",
                "lambda_max": "Maks forventet mål",
            }
            param_rows = []
            for k in bt.get("default_params", {}):
                std_v = bt["default_params"][k]
                opt_v = bt.get("best_params", {}).get(k, std_v)
                param_rows.append({
                    "Parameter": _param_labels.get(k, k),
                    "Standard": std_v,
                    "Optimal (grid search)": opt_v,
                    "Endret": "Ja" if std_v != opt_v else "",
                })
            st.dataframe(pd.DataFrame(param_rows), use_container_width=True, hide_index=True)

            st.divider()

            # ─── Metrics side-by-side ───
            st.markdown("#### Modellytelse (train / test split)")
            st.caption("Train = 70% av kampene (kronologisk), Test = siste 30%. Overfitting = god train, dårlig test.")

            def _fmt_metrics(m):
                return {
                    "Accuracy": f"{m.get('accuracy', '?')}%",
                    "Log-loss": str(m.get('log_loss', '?')),
                    "Brier score": str(m.get('brier', '?')),
                    "Kamper": str(m.get('n', '?')),
                }

            metrics_df = pd.DataFrame({
                "Metrikk": ["Accuracy", "Log-loss", "Brier score", "Kamper"],
                "Standard (train)": list(_fmt_metrics(bt.get("default_train_metrics", {})).values()),
                "Standard (test)": list(_fmt_metrics(bt.get("default_test_metrics", {})).values()),
                "Optimal (train)": list(_fmt_metrics(bt.get("best_train_metrics", {})).values()),
                "Optimal (test)": list(_fmt_metrics(bt.get("best_test_metrics", {})).values()),
            })
            st.dataframe(metrics_df, use_container_width=True, hide_index=True)

            st.divider()

            # ─── Per-liga resultater ───
            st.markdown("#### Per-liga resultater")
            per_liga_best = bt.get("per_liga_best", {})
            per_liga_default = bt.get("per_liga_default", {})

            liga_rows = []
            for liga in sorted(set(list(per_liga_best.keys()) + list(per_liga_default.keys()))):
                best_m = per_liga_best.get(liga, {})
                def_m = per_liga_default.get(liga, {})
                n = best_m.get("n", def_m.get("n", 0))
                if n == 0:
                    continue
                liga_rows.append({
                    "Liga": liga,
                    "Kamper": n,
                    "Standard acc": f"{def_m.get('accuracy', '?')}%",
                    "Optimal acc": f"{best_m.get('accuracy', '?')}%",
                    "Standard log-loss": def_m.get("log_loss", "?"),
                    "Optimal log-loss": best_m.get("log_loss", "?"),
                })
            if liga_rows:
                st.dataframe(pd.DataFrame(liga_rows), use_container_width=True, hide_index=True)

            st.divider()

            # ─── Parametersensitivitet ───
            st.markdown("#### Parametersensitivitet")
            st.caption("Snitt accuracy over alle kombinasjoner der parameteren har gitt verdi. Flat linje = ingen effekt.")
            sensitivity = bt.get("sensitivity", {})
            _sens_labels = {
                "form_weight": "Form-vekt",
                "form_window": "Formvindu (kamper)",
            }
            for param_name, values in sensitivity.items():
                if not values or len(values) < 2:
                    continue
                # Sjekk om det er variasjon
                vals_list = list(values.values())
                if max(vals_list) - min(vals_list) < 0.1:
                    continue
                label = _sens_labels.get(param_name, param_name)
                st.markdown(f"**{label}**")
                sens_df = pd.DataFrame({
                    "Verdi": [float(k) for k in values.keys()],
                    "Accuracy (%)": list(values.values()),
                })
                st.line_chart(sens_df.set_index("Verdi"), height=250)

            st.divider()

            # ─── Kalibrering ───
            st.markdown("#### Kalibrering")
            st.caption("Perfekt modell = predikert og observert er like (langs diagonalen). Over diagonalen = modellen er overmodig.")
            calibration = bt.get("calibration", [])
            if calibration:
                cal_df = pd.DataFrame(calibration)

                # Graf med bin som x-akse
                chart_data = pd.DataFrame({
                    "Predikert %": cal_df["avg_predicted"].values,
                    "Observert %": cal_df["avg_observed"].values,
                    "Perfekt": cal_df["avg_predicted"].values,  # diagonalen
                })
                chart_data.index = cal_df["bin"].values
                st.line_chart(chart_data, height=350)

                # Tabell under
                display_cal = cal_df[["bin", "avg_predicted", "avg_observed", "n"]].rename(columns={
                    "bin": "Sannsynlighetsbin",
                    "avg_predicted": "Predikert %",
                    "avg_observed": "Observert %",
                    "n": "Antall prediksjoner",
                })
                st.dataframe(display_cal, use_container_width=True, hide_index=True)

            st.divider()

            # ─── Kampdetaljer ───
            st.markdown("#### Kampdetaljer")
            if os.path.exists(_backtest_details_path):
                try:
                    details_df = pd.read_csv(_backtest_details_path)

                    # Nøkkeltall
                    dt1, dt2, dt3 = st.columns(3)
                    n_correct = details_df["correct"].sum()
                    n_total = len(details_df)
                    dt1.metric("Totalt", n_total)
                    dt2.metric("Korrekte", f"{n_correct} ({round(n_correct/max(n_total,1)*100, 1)}%)")
                    dt3.metric("Feil", f"{n_total - n_correct} ({round((n_total-n_correct)/max(n_total,1)*100, 1)}%)")

                    # Filtre
                    ft1, ft2 = st.columns(2)
                    with ft1:
                        bt_liga_filter = st.multiselect(
                            "Liga",
                            options=sorted(details_df["liga"].unique()),
                            default=sorted(details_df["liga"].unique()),
                            key="bt_liga",
                        )
                    with ft2:
                        bt_correct_filter = st.radio(
                            "Vis", ["Alle", "Korrekte", "Feil"],
                            horizontal=True, key="bt_correct",
                        )

                    filtered = details_df[details_df["liga"].isin(bt_liga_filter)]
                    if bt_correct_filter == "Korrekte":
                        filtered = filtered[filtered["correct"] == True]
                    elif bt_correct_filter == "Feil":
                        filtered = filtered[filtered["correct"] == False]

                    # Vis med bedre kolonnenavn
                    display_details = filtered.rename(columns={
                        "liga": "Liga",
                        "home_name": "Hjemmelag",
                        "away_name": "Bortelag",
                        "home_goals": "HM",
                        "away_goals": "BM",
                        "actual": "Faktisk",
                        "predicted": "Predikert",
                        "prob_H": "H%",
                        "prob_U": "U%",
                        "prob_B": "B%",
                        "correct": "Korrekt",
                    }).drop(columns=["lambda_h", "lambda_b"], errors="ignore")

                    st.dataframe(display_details, use_container_width=True, hide_index=True)
                    st.caption(f"Viser {len(filtered)} av {len(details_df)} kamper")
                except Exception as _e:
                    st.warning(f"Kunne ikke lese detaljer: {_e}")
            else:
                st.info("Ingen detaljfil funnet. Kjør `python backtest.py` for å generere.")

            st.divider()

            # ─── Bruk optimale parametre ───
            st.markdown("#### Bruk optimale parametre")
            using_optimal = st.session_state.get("model_params") == bt.get("best_params")
            if using_optimal:
                st.success("Optimale parametre er aktive i analysen")
                if st.button("Tilbakestill til standard"):
                    if "model_params" in st.session_state:
                        del st.session_state["model_params"]
                    st.rerun()
            else:
                st.info("Analysen bruker standard parametre")
                if st.button("Bruk optimale parametre"):
                    st.session_state["model_params"] = bt["best_params"]
                    st.rerun()
