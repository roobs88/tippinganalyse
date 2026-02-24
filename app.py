import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date
import numpy as np
import json
import os

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

st.set_page_config(page_title="TippingAnalyse", page_icon="⚽", layout="wide")

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
    farger = {"W": "#22c55e", "D": "#eab308", "L": "#ef4444"}
    html = ""
    for f in form_liste[:5]:
        r = f.get("result", "?")
        c = farger.get(r, "#9ca3af")
        tooltip = f"{f.get('score', '')} vs {f.get('opponent', '')}"
        venue = "H" if f.get("is_home") else "B"
        html += (
            f'<span title="{tooltip}" style="display:inline-block;width:28px;height:28px;'
            f'line-height:28px;text-align:center;border-radius:4px;margin:1px;'
            f'background:{c};color:white;font-weight:bold;font-size:13px">'
            f'{r}</span>'
        )
    return html

def modell_nivaa_badge(nivaa):
    """Returnerer en farget badge for modellnivå."""
    farger = {
        "Dyp (form+xG)": "#22c55e",
        "Dyp (form)": "#3b82f6",
        "Basis (sesongsnitt)": "#eab308",
        "Ingen modell": "#9ca3af",
    }
    bg = farger.get(nivaa, "#9ca3af")
    return (
        f'<span style="background:{bg};color:white;padding:2px 8px;'
        f'border-radius:10px;font-size:12px;font-weight:bold">{nivaa}</span>'
    )

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
    if not ws.row_values(1):
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
        ]
        ws.append_row(headers)
    return ws

def lagre_kupong_til_sheets(analyse_resultater):
    """Lagrer kupong til Google Sheets. Returnerer (antall_lagret, allerede_lagret)."""
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
        for a in analyse_resultater:
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

st.title("⚽ TippingAnalyse")
st.caption("Folkerekke · Dyp Poisson-analyse · Form · H2H · Verdianalyse · Historikk")

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
        for liga in ligaer:
            lid = FOTMOB_LIGA_IDS.get(liga)
            if lid:
                data = hent_fotmob_tabell(lid)
                if data and data.get("teams"):
                    liga_data_cache[liga] = data
                # Hent xG (valgfritt, feiler stille)
                xg = hent_fotmob_xg(lid)
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
            for tid in needed_teams:
                td = hent_fotmob_team(tid)
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
# LAGRE KUPONG AUTOMATISK
# ─────────────────────────────────────────────

if sheets_available() and analyse_resultater:
    antall, duplikat = lagre_kupong_til_sheets(analyse_resultater)
    if antall > 0:
        st.toast(f"Kupong lagret til historikk ({antall} kamper)")
    elif duplikat:
        pass  # Stille — kupongen er allerede lagret

# ─────────────────────────────────────────────
# TABS: ANALYSE, HISTORIKK OG BACKTEST
# ─────────────────────────────────────────────

# Sjekk om backtest-resultater finnes
_backtest_results_path = os.path.join(os.path.dirname(__file__) or ".", "backtest_results.json")
_backtest_details_path = os.path.join(os.path.dirname(__file__) or ".", "backtest_details.csv")
_has_backtest = os.path.exists(_backtest_results_path)

tab_names = ["Analyse"]
if sheets_available():
    tab_names.append("Historikk")
if _has_backtest:
    tab_names.append("Backtest")

if len(tab_names) > 1:
    tabs = st.tabs(tab_names)
    tab_analyse = tabs[0]
    tab_historikk = tabs[tab_names.index("Historikk")] if "Historikk" in tab_names else None
    tab_backtest = tabs[tab_names.index("Backtest")] if "Backtest" in tab_names else None
else:
    tab_analyse = st.container()
    tab_historikk = None
    tab_backtest = None

# ═══════════════════════════════════════════════
# ANALYSE-FANEN
# ═══════════════════════════════════════════════

with tab_analyse:

    # ─────────────────────────────────────────────
    # SAMMENDRAGSTABELL
    # ─────────────────────────────────────────────

    st.subheader("Sammendrag")

    sammendrag_rader = []
    for a in analyse_resultater:
        rad = a["rad"]
        pr = a["poisson_res"]
        avvik = a["avvik_poi"]
        max_av = a["max_poi_avvik"]

        # Finn verdisignal
        verdisignal = "⚪"
        if max_av >= 8:
            beste = max(avvik, key=lambda x: abs(x) if x else 0, default=None)
            verdisignal = pil(beste)

        sammendrag_rader.append({
            "Kamp": rad["Kamp"],
            "Folk H/U/B": f"{a['folk_h']}/{a['folk_u']}/{a['folk_b']}",
            "Modell H/U/B": f"{pr['H']}/{pr['U']}/{pr['B']}" if pr else "–",
            "Forv. mål": f"{pr['lambda_h']}-{pr['lambda_b']}" if pr else "–",
            "Modellnivå": a["modell_nivaa"],
            "Verdisignal": verdisignal,
        })

    if sammendrag_rader:
        st.dataframe(
            pd.DataFrame(sammendrag_rader),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    # ─────────────────────────────────────────────
    # KAMPVISNING
    # ─────────────────────────────────────────────

    verdikamper = 0

    for dag in df_vis["Dag"].unique():
        st.subheader(f"📅 {dag}kupong")
        dag_analyser = [a for a in analyse_resultater if a["rad"]["Dag"] == dag]

        for a in dag_analyser:
            rad = a["rad"]
            hjemmelag = rad["Hjemmelag"]
            bortelag = rad["Bortelag"]
            liga = rad["Liga"]
            folk_h, folk_u, folk_b = a["folk_h"], a["folk_u"], a["folk_b"]
            poisson_res = a["poisson_res"]
            avvik_poi = a["avvik_poi"]
            max_poi_avvik = a["max_poi_avvik"]

            har_verdi = max_poi_avvik >= min_avvik
            if bare_verdi and max_poi_avvik < 8:
                continue
            if max_poi_avvik < min_avvik:
                continue
            if max_poi_avvik >= 8:
                verdikamper += 1

            # Tittel
            beste = max(avvik_poi, key=lambda x: abs(x) if x else 0, default=None)
            tittel_ikon = pil(beste) if beste and abs(beste) > 8 else ""

            with st.expander(f"{tittel_ikon} {rad['Kamp']}  —  {liga}  ({rad['Dato']})"):

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

    st.divider()

    # ─── Bunntall ───
    col1, col2, col3 = st.columns(3)
    col1.metric("Kamper vist", len(df_vis))
    col2.metric("Verdisignaler (>8pp)", verdikamper)
    col3.metric("Ligaer med statistikk", len(liga_data_cache))

    st.caption(f"Data: NT API + FotMob · Sist oppdatert: {datetime.now().strftime('%H:%M:%S')} · Dyp Poisson-modell: styrke + form + xG")

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

                    # Verdi-treff (kun kamper med verdisignal)
                    verdi_kamper = har_resultat[har_resultat["verdi_tips"].astype(str).isin(["H", "U", "B"])]
                    verdi_totalt = len(verdi_kamper)
                    verdi_treff = (verdi_kamper["verdi_korrekt"].astype(str) == "true").sum() if verdi_totalt > 0 else 0
                    verdi_rate = round(verdi_treff / verdi_totalt * 100, 1) if verdi_totalt > 0 else 0

                    folk_treff = (har_resultat["folk_korrekt"].astype(str) == "true").sum()
                    folk_rate = round(folk_treff / totalt * 100, 1) if totalt > 0 else 0

                    modell_vs_folk = modell_treff - folk_treff

                    # Metrics
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Kamper tipset", totalt)
                    m2.metric("Modell-treffrate", f"{modell_rate}%")
                    m3.metric("Verdi-treffrate", f"{verdi_rate}%" if verdi_totalt > 0 else "–",
                              help=f"Basert på {verdi_totalt} kamper med verdisignal")
                    m4.metric("Folk-treffrate", f"{folk_rate}%")
                    m5.metric("Modell vs Folk", f"{'+' if modell_vs_folk > 0 else ''}{modell_vs_folk} kamper",
                              delta=f"{'+' if modell_vs_folk > 0 else ''}{modell_vs_folk}",
                              delta_color="normal")

                    st.divider()

                    # ─── Treffrate per liga ───
                    st.markdown("#### Treffrate per liga")
                    liga_stats = []
                    for liga_navn in har_resultat["liga"].unique():
                        liga_df = har_resultat[har_resultat["liga"] == liga_navn]
                        n = len(liga_df)
                        mt = (liga_df["modell_korrekt"].astype(str) == "true").sum()
                        ft = (liga_df["folk_korrekt"].astype(str) == "true").sum()
                        liga_stats.append({
                            "Liga": liga_navn,
                            "Kamper": n,
                            "Modell": f"{round(mt / n * 100, 1)}%",
                            "Folk": f"{round(ft / n * 100, 1)}%",
                            "Modell bedre": mt - ft,
                        })
                    if liga_stats:
                        st.dataframe(pd.DataFrame(liga_stats), use_container_width=True, hide_index=True)

                    # ─── Treffrate per modellnivå ───
                    st.markdown("#### Treffrate per modellnivå")
                    nivaa_stats = []
                    for nivaa in har_resultat["modell_nivaa"].unique():
                        nivaa_df = har_resultat[har_resultat["modell_nivaa"] == nivaa]
                        n = len(nivaa_df)
                        mt = (nivaa_df["modell_korrekt"].astype(str) == "true").sum()
                        nivaa_stats.append({
                            "Modellnivå": nivaa,
                            "Kamper": n,
                            "Treffrate": f"{round(mt / n * 100, 1)}%",
                        })
                    if nivaa_stats:
                        st.dataframe(pd.DataFrame(nivaa_stats), use_container_width=True, hide_index=True)

                    # ─── Treffrate per kupong (siste 10) ───
                    st.markdown("#### Treffrate per kupong (siste 10)")
                    kupong_stats = []
                    for kid in har_resultat["kupong_id"].unique():
                        k_df = har_resultat[har_resultat["kupong_id"] == kid]
                        n = len(k_df)
                        mt = (k_df["modell_korrekt"].astype(str) == "true").sum()
                        ft = (k_df["folk_korrekt"].astype(str) == "true").sum()
                        kupong_stats.append({
                            "Kupong": kid,
                            "Kamper": n,
                            "Modell": f"{round(mt / n * 100, 1)}%",
                            "Folk": f"{round(ft / n * 100, 1)}%",
                        })
                    # Vis siste 10
                    kupong_df = pd.DataFrame(kupong_stats[-10:])
                    if not kupong_df.empty:
                        st.dataframe(kupong_df, use_container_width=True, hide_index=True)

                    st.divider()

                # ─── Filtre for detaljert visning ───
                st.markdown("#### Detaljert kamphistorikk")
                fil1, fil2, fil3 = st.columns(3)
                with fil1:
                    alle_ligaer = sorted(hist_df["liga"].dropna().unique().tolist())
                    valgt_liga = st.multiselect("Liga", options=alle_ligaer, default=alle_ligaer, key="hist_liga")
                with fil2:
                    kun_verdi = st.checkbox("Kun verdikamper", key="hist_verdi")
                with fil3:
                    vis_type = st.radio("Vis", ["Alle", "Med resultat", "Venter på resultat"], key="hist_vis", horizontal=True)

                # Filtrer
                vis_df = hist_df.copy()
                if valgt_liga:
                    vis_df = vis_df[vis_df["liga"].isin(valgt_liga)]
                if kun_verdi:
                    vis_df = vis_df[vis_df["verdi_tips"].astype(str).isin(["H", "U", "B"])]
                if vis_type == "Med resultat":
                    vis_df = vis_df[vis_df["resultat"].astype(str).isin(["H", "U", "B"])]
                elif vis_type == "Venter på resultat":
                    vis_df = vis_df[~vis_df["resultat"].astype(str).isin(["H", "U", "B"])]

                # Bygg visningstabell
                if not vis_df.empty:
                    display_rows = []
                    for _, row in vis_df.iterrows():
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
                        display_rows.append({
                            "Dato": row.get("dato", ""),
                            "Kamp": kamp,
                            "Liga": row.get("liga", ""),
                            "Folk H/U/B": folk_str,
                            "Modell H/U/B": modell_str,
                            "Tips": row.get("modell_tips", ""),
                            "Verdi": row.get("verdi_tips", ""),
                            "Resultat": res,
                            "Modell": modell_ok,
                            "Folk": folk_ok,
                        })
                    st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
                else:
                    st.info("Ingen kamper matcher filtrene")

                # Ventende kamper
                if not venter.empty:
                    st.caption(f"⏳ {len(venter)} kamper venter på resultater")

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
