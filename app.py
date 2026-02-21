import streamlit as st
import pandas as pd
import requests
from scipy.stats import poisson
from datetime import datetime
import numpy as np

st.set_page_config(page_title="TippingAnalyse", page_icon="⚽", layout="wide")

# ─────────────────────────────────────────────
# HEMMELIGHETER
# ─────────────────────────────────────────────
try:
    ODDS_API_KEY = st.secrets["ODDS_API_KEY"]
except:
    ODDS_API_KEY = None

try:
    FOOTBALL_DATA_KEY = st.secrets["FOOTBALL_DATA_KEY"]
except:
    FOOTBALL_DATA_KEY = None

# ─────────────────────────────────────────────
# KONSTANTER
# ─────────────────────────────────────────────

NT_API = "https://api.norsk-tipping.no/PoolGamesSportInfo/v1/api/tipping/live-info"

FD_LIGA_IDS = {
    "ENG Premier League": "PL",
    "ENG Championship": "ELC",
    "ENG League 1": "EL1",
    "UEFA Champions League": "CL",
    "UEFA Europa League": "EL",
    "SPA LaLiga": "PD",
    "ITA Serie A": "SA",
    "GER Bundesliga": "BL1",
    "FRA Ligue 1": "FL1",
    "NOR Eliteserien": "PPL",
    "NED Eredivisie": "DED",
}

# Understat dekker disse ligaene (med xG)
UNDERSTAT_LIGAER = {
    "ENG Premier League": "EPL",
    "ENG Championship": "Championship",
    "SPA LaLiga": "La_liga",
    "ITA Serie A": "Serie_A",
    "GER Bundesliga": "Bundesliga",
    "FRA Ligue 1": "Ligue_1",
    "NED Eredivisie": "Eredivisie",
    "RUS Premier League": "RFPL",
}

ODDS_SPORT_KEYS = {
    "ENG Premier League": "soccer_epl",
    "ENG Championship": "soccer_england_championship",
    "ENG League 1": "soccer_england_league1",
    "UEFA Champions League": "soccer_uefa_champs_league",
    "UEFA Europa League": "soccer_uefa_europa_league",
    "SPA LaLiga": "soccer_spain_la_liga",
    "ITA Serie A": "soccer_italy_serie_a",
    "GER Bundesliga": "soccer_germany_bundesliga",
    "FRA Ligue 1": "soccer_france_ligue_one",
    "NOR Eliteserien": "soccer_norway_eliteserien",
    "SKO Premiership": "soccer_scotland_premiership",
    "NED Eredivisie": "soccer_netherlands_eredivisie",
}

FOTMOB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.fotmob.com/",
}

# ─────────────────────────────────────────────
# NORSK TIPPING
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
            })
    return pd.DataFrame(kamper)

# ─────────────────────────────────────────────
# FOOTBALL-DATA.ORG – Hjemme/borte tabell
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def hent_fd_statistikk(liga_kode):
    if not FOOTBALL_DATA_KEY:
        return {}
    try:
        headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
        url = f"https://api.football-data.org/v4/competitions/{liga_kode}/standings"
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()

        lag_stats = {}
        for tabell in data.get("standings", []):
            ttype = tabell.get("type", "")
            if ttype not in ["HOME", "AWAY", "TOTAL"]:
                continue
            for row in tabell.get("table", []):
                team = row.get("team", {})
                navn = team.get("name", "") or team.get("shortName", "")
                if not navn:
                    continue
                if navn not in lag_stats:
                    lag_stats[navn] = {}

                spilt = row.get("playedGames", 0)
                scoret = row.get("goalsFor", 0)
                innsl = row.get("goalsAgainst", 0)
                seier = row.get("won", 0)
                uav = row.get("draw", 0)
                tap = row.get("lost", 0)

                if ttype == "HOME":
                    lag_stats[navn].update({
                        "hjemme_spilt": spilt, "hjemme_scoret": scoret,
                        "hjemme_innsluppet": innsl, "hjemme_seier": seier,
                        "hjemme_uav": uav, "hjemme_tap": tap,
                    })
                elif ttype == "AWAY":
                    lag_stats[navn].update({
                        "borte_spilt": spilt, "borte_scoret": scoret,
                        "borte_innsluppet": innsl, "borte_seier": seier,
                        "borte_uav": uav, "borte_tap": tap,
                    })
                elif ttype == "TOTAL":
                    lag_stats[navn].update({
                        "totalt_spilt": spilt, "totalt_scoret": scoret,
                        "totalt_innsluppet": innsl,
                    })
        return lag_stats
    except Exception:
        return {}

# ─────────────────────────────────────────────
# UNDERSTAT – xG per lag
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def hent_understat_xg(liga_navn):
    """Henter xG-statistikk fra Understat for en hel liga."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://understat.com/",
        }
        url = f"https://understat.com/league/{liga_navn}"
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()

        import re, json
        # Understat embedder data i script-tagger som JSON
        pattern = r"teamsData\s*=\s*JSON\.parse\('(.+?)'\)"
        match = re.search(pattern, r.text)
        if not match:
            return {}

        raw = match.group(1)
        # Unscape unicode
        raw = raw.encode('utf-8').decode('unicode_escape')
        teams_data = json.loads(raw)

        xg_stats = {}
        for team_id, team in teams_data.items():
            navn = team.get("title", "")
            if not navn:
                continue

            # Hent xG og xGA fra kamphistorikk
            history = team.get("history", [])
            hjem_xg, hjem_xga, hjem_n = 0, 0, 0
            borte_xg, borte_xga, borte_n = 0, 0, 0

            for kamp in history:
                h = kamp.get("h_a", "")
                xg  = float(kamp.get("xG", 0) or 0)
                xga = float(kamp.get("xGA", 0) or 0)
                if h == "h":
                    hjem_xg += xg; hjem_xga += xga; hjem_n += 1
                elif h == "a":
                    borte_xg += xg; borte_xga += xga; borte_n += 1

            xg_stats[navn] = {
                "hjem_xg":  round(hjem_xg / max(hjem_n, 1), 3),
                "hjem_xga": round(hjem_xga / max(hjem_n, 1), 3),
                "hjem_n":   hjem_n,
                "borte_xg":  round(borte_xg / max(borte_n, 1), 3),
                "borte_xga": round(borte_xga / max(borte_n, 1), 3),
                "borte_n":   borte_n,
            }
        return xg_stats
    except Exception:
        return {}

# ─────────────────────────────────────────────
# DIXON-COLES STYRKEINDEKSER
# ─────────────────────────────────────────────

def beregn_styrkeindekser(lag_stats):
    """
    Beregner angrepsstyrke og forsvarsstyrke for hvert lag
    relativt til ligagjennomsnittet (Dixon-Coles-metoden).
    
    Angrepsstyrke > 1.0 = scorer mer enn ligasnittet
    Forsvarsstyrke < 1.0 = slipper inn færre enn ligasnittet (BEDRE forsvar)
    """
    if not lag_stats:
        return {}

    # Beregn ligasnitt
    hjem_scoret_snitt = np.mean([
        s["hjemme_scoret"] / max(s["hjemme_spilt"], 1)
        for s in lag_stats.values()
        if s.get("hjemme_spilt", 0) > 0
    ]) if lag_stats else 1.5

    borte_scoret_snitt = np.mean([
        s["borte_scoret"] / max(s["borte_spilt"], 1)
        for s in lag_stats.values()
        if s.get("borte_spilt", 0) > 0
    ]) if lag_stats else 1.1

    styrke = {}
    for navn, s in lag_stats.items():
        hsp = max(s.get("hjemme_spilt", 0), 1)
        bsp = max(s.get("borte_spilt", 0), 1)

        hjem_score_snitt = s.get("hjemme_scoret", 0) / hsp
        hjem_innsl_snitt = s.get("hjemme_innsluppet", 0) / hsp
        borte_score_snitt = s.get("borte_scoret", 0) / bsp
        borte_innsl_snitt = s.get("borte_innsluppet", 0) / bsp

        styrke[navn] = {
            # Angrepsstyrke: lagets snitt / ligasnitt
            "angrep_hjem":  round(hjem_score_snitt / max(hjem_scoret_snitt, 0.1), 3),
            "angrep_borte": round(borte_score_snitt / max(borte_scoret_snitt, 0.1), 3),
            # Forsvarsstyrke: ligasnitt / lagets innslupne (høyere = bedre forsvar)
            "forsvar_hjem":  round(hjem_scoret_snitt / max(hjem_innsl_snitt, 0.1), 3),
            "forsvar_borte": round(borte_scoret_snitt / max(borte_innsl_snitt, 0.1), 3),
            # Snitt
            "hjem_sc_snitt":  round(hjem_score_snitt, 3),
            "hjem_in_snitt":  round(hjem_innsl_snitt, 3),
            "borte_sc_snitt": round(borte_score_snitt, 3),
            "borte_in_snitt": round(borte_innsl_snitt, 3),
            "liga_hjem_snitt":  round(hjem_scoret_snitt, 3),
            "liga_borte_snitt": round(borte_scoret_snitt, 3),
        }
    return styrke

# ─────────────────────────────────────────────
# POISSON-MODELL (Dixon-Coles forbedret)
# ─────────────────────────────────────────────

def poisson_modell(h_styrke, b_styrke, xg_data_h=None, xg_data_b=None):
    """
    Beregner H/U/B med Poisson-fordeling basert på Dixon-Coles styrkeindekser.
    Vekter inn xG der det er tilgjengelig.
    """
    try:
        liga_hjem  = h_styrke.get("liga_hjem_snitt", 1.5)
        liga_borte = h_styrke.get("liga_borte_snitt", 1.1)

        # Forventet mål basert på styrkeindekser (Dixon-Coles)
        lambda_h_dc = (h_styrke["angrep_hjem"] * b_styrke["forsvar_borte"] * liga_hjem)
        lambda_b_dc = (b_styrke["angrep_borte"] * h_styrke["forsvar_hjem"] * liga_borte)

        # Hvis xG er tilgjengelig, vekt 50/50 mellom modell og xG
        if xg_data_h and xg_data_b:
            xg_h = xg_data_h.get("hjem_xg", lambda_h_dc)
            xg_b = xg_data_b.get("borte_xg", lambda_b_dc)
            lambda_h = 0.5 * lambda_h_dc + 0.5 * xg_h
            lambda_b = 0.5 * lambda_b_dc + 0.5 * xg_b
        else:
            lambda_h = lambda_h_dc
            lambda_b = lambda_b_dc

        # Begrens til realistiske verdier
        lambda_h = max(0.3, min(lambda_h, 6.0))
        lambda_b = max(0.3, min(lambda_b, 6.0))

        ph = pu = pb = 0.0
        for i in range(9):
            for j in range(9):
                p = poisson.pmf(i, lambda_h) * poisson.pmf(j, lambda_b)
                if i > j:    ph += p
                elif i == j: pu += p
                else:        pb += p

        tot = ph + pu + pb
        return {
            "H": round(ph/tot*100, 1),
            "U": round(pu/tot*100, 1),
            "B": round(pb/tot*100, 1),
            "xH": round(lambda_h, 2),
            "xB": round(lambda_b, 2),
            "brukte_xg": xg_data_h is not None and xg_data_b is not None,
        }
    except:
        return None

# ─────────────────────────────────────────────
# THE ODDS API
# ─────────────────────────────────────────────

@st.cache_data(ttl=300)
def hent_odds(sport_key):
    if not ODDS_API_KEY or not sport_key:
        return []
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "eu",
            "markets": "h2h",
            "oddsFormat": "decimal",
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return []

def match_odds(odds_liste, hjemme, borte):
    hl, bl = hjemme.lower(), borte.lower()
    for event in odds_liste:
        eh = event.get("home_team", "").lower()
        eb = event.get("away_team", "").lower()
        if (hl in eh or eh in hl or hl.split()[0] in eh) and \
           (bl in eb or eb in bl or bl.split()[0] in eb):
            for bm in event.get("bookmakers", []):
                for market in bm.get("markets", []):
                    if market.get("key") == "h2h":
                        outcomes = market.get("outcomes", [])
                        odds = {}
                        for o in outcomes:
                            n = o.get("name", "").lower()
                            p = o.get("price", 0)
                            if eh in n or "home" in n: odds["H"] = p
                            elif "draw" in n: odds["U"] = p
                            elif eb in n or "away" in n: odds["B"] = p
                        if len(odds) == 3:
                            return odds
    return None

def impl_pct(odds_dict):
    if not odds_dict: return None
    try:
        vig = sum(1/v for v in odds_dict.values() if v > 0)
        return {k: round((1/v)/vig*100, 1) for k, v in odds_dict.items() if v > 0}
    except:
        return None

# ─────────────────────────────────────────────
# FUZZY NAVNEMATCHING
# ─────────────────────────────────────────────

def fuzzy_match(stats_dict, lagnavn):
    if not stats_dict or not lagnavn:
        return None
    if lagnavn in stats_dict:
        return stats_dict[lagnavn]
    l = lagnavn.lower()
    for k, v in stats_dict.items():
        if l in k.lower() or k.lower() in l:
            return v
    første = l.split()[0] if l.split() else ""
    for k, v in stats_dict.items():
        if første and len(første) > 3 and første in k.lower():
            return v
    return None

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.kamp-kort {
    background: #0f172a;
    border: 1px solid #1e293b;
    border-left: 3px solid #1e293b;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 14px;
}
.kamp-kort.verdi {
    border-color: #22c55e44;
    border-left: 3px solid #22c55e;
}
.kamp-tittel {
    font-size: 16px; font-weight: 800;
    color: #f1f5f9; margin-bottom: 2px;
}
.kamp-meta { font-size: 12px; color: #475569; }
.verdi-badge {
    display: inline-block;
    background: #14532d; color: #4ade80;
    font-size: 10px; font-weight: 700;
    padding: 2px 9px; border-radius: 20px;
    margin-left: 8px; letter-spacing: 0.5px;
}
.seksjon {
    background: #131e2e;
    border-radius: 8px;
    padding: 14px;
    height: 100%;
}
.sek-tittel {
    font-size: 11px; font-weight: 700;
    color: #475569; letter-spacing: 0.08em;
    text-transform: uppercase; margin-bottom: 12px;
}
.folk-rad { margin-bottom: 8px; }
.folk-topp {
    display: flex; justify-content: space-between;
    font-size: 12px; color: #94a3b8; margin-bottom: 4px;
}
.folk-bar { height: 5px; background: #1e293b; border-radius: 3px; }
.folk-fill-H { background: #3b82f6; border-radius: 3px; height: 5px; }
.folk-fill-U { background: #eab308; border-radius: 3px; height: 5px; }
.folk-fill-B { background: #a855f7; border-radius: 3px; height: 5px; }
.utfall-rad {
    display: flex; align-items: center;
    gap: 6px; margin-bottom: 8px; font-size: 13px;
}
.u-label { color: #64748b; min-width: 80px; font-size: 12px; }
.u-pct { color: #e2e8f0; font-weight: 700; font-family: monospace; min-width: 42px; }
.u-odds { color: #475569; font-size: 11px; min-width: 55px; }
.u-avvik { font-weight: 700; font-family: monospace; font-size: 12px; }
.stat-grid {
    display: grid; grid-template-columns: 1fr 1fr 1fr;
    gap: 8px; margin-top: 4px;
}
.stat-boks {
    background: #1e293b; border-radius: 6px;
    padding: 8px 10px; text-align: center;
}
.stat-label { font-size: 10px; color: #475569; margin-bottom: 3px; }
.stat-val { font-size: 16px; font-weight: 800; color: #e2e8f0; font-family: monospace; }
.stat-sub { font-size: 10px; color: #64748b; }
.styrke-rad {
    display: flex; justify-content: space-between;
    font-size: 12px; padding: 4px 0;
    border-bottom: 1px solid #1e293b;
}
.xg-badge {
    display: inline-block;
    background: #1e3a5f; color: #60a5fa;
    font-size: 10px; font-weight: 700;
    padding: 1px 6px; border-radius: 4px; margin-left: 4px;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# APP START
# ─────────────────────────────────────────────

st.title("⚽ TippingAnalyse")
st.caption("Folkerekke · Markedsodds · Dixon-Coles Poisson-modell med xG")

# ─── Last NT ───
with st.spinner("Henter tippekupong fra Norsk Tipping..."):
    nt_json, nt_feil = hent_nt_data()
if nt_feil or not nt_json:
    st.error(f"Kunne ikke hente NT-data: {nt_feil}")
    st.stop()

df = prosesser_nt(nt_json)
ligaer_i_kupong = df["Liga"].unique().tolist()

# ─── Last football-data.org ───
fd_cache = {}
styrke_cache = {}
with st.spinner("Henter statistikk og beregner styrkeindekser..."):
    for liga, kode in FD_LIGA_IDS.items():
        if liga in ligaer_i_kupong:
            stats = hent_fd_statistikk(kode)
            if stats:
                fd_cache[liga] = stats
                styrke_cache[liga] = beregn_styrkeindekser(stats)

# ─── Last Understat xG ───
xg_cache = {}
with st.spinner("Henter xG-data fra Understat..."):
    for liga, understat_navn in UNDERSTAT_LIGAER.items():
        if liga in ligaer_i_kupong:
            xg = hent_understat_xg(understat_navn)
            if xg:
                xg_cache[liga] = xg

# ─── Last odds ───
odds_cache = {}
with st.spinner("Henter markedsodds..."):
    for liga, sport_key in ODDS_SPORT_KEYS.items():
        if liga in ligaer_i_kupong:
            data = hent_odds(sport_key)
            if data:
                odds_cache[liga] = data

# ─── Status ───
col1, col2, col3, col4 = st.columns(4)
col1.metric("Kamper", len(df))
col2.metric("Ligaer m/ statistikk", len(fd_cache))
col3.metric("Ligaer m/ xG", len(xg_cache))
col4.metric("Ligaer m/ odds", len(odds_cache))

# ─── Forklaring ───
with st.expander("ℹ️ Slik leser du analysen"):
    st.markdown("""
    ### Tre sannsynlighetsestimater sammenlignes mot Folkerekka:

    | | Kilde | Metode |
    |-|-------|--------|
    | 👥 **Folkerekka** | Norsk Tipping | Hva vanlige tippere tror (%) |
    | 📈 **Markedsodds** | The Odds API | Implisitt % fra bookmaker-odds (margin fjernet) |
    | 🔢 **Poisson-modell** | football-data.org + Understat | Dixon-Coles med xG der tilgjengelig |

    ### Poisson-modellen (Dixon-Coles):
    - **Angrepsstyrke** = lagets scoresnitt / ligasnitt (>1.0 = bedre enn snitt)
    - **Forsvarsstyrke** = ligasnitt / lagets innslupne (>1.0 = bedre enn snitt)
    - **Forventet mål (λ)** = hjemmeangrep × borteforsvar × ligasnitt
    - **xG vektes 50/50** der Understat-data er tilgjengelig

    ### Verdisignaler:
    - 🟢 **Grønn +pp** = Modell/odds ser MER enn folk → **underspilt → verdi**
    - 🔴 **Rød -pp** = Folk overtipper → **overspilt → vær forsiktig**
    """)

# ─── Filter ───
st.sidebar.header("🔍 Filter")
dag_valg = st.sidebar.multiselect("Kupong", options=df["Dag"].unique(), default=df["Dag"].unique())
bare_verdi = st.sidebar.checkbox("Vis bare verdisignaler (>8pp)")
min_avvik = st.sidebar.slider("Minste avvik å vise (pp)", 0, 20, 0)
if st.sidebar.button("🔄 Oppdater alle data"):
    st.cache_data.clear()
    st.rerun()

df_vis = df[df["Dag"].isin(dag_valg)].copy()
st.divider()

# ─────────────────────────────────────────────
# KAMPVISNING
# ─────────────────────────────────────────────

verdikamper = 0

for dag in df_vis["Dag"].unique():
    st.subheader(f"📅 {dag}kupong")

    for _, rad in df_vis[df_vis["Dag"] == dag].iterrows():
        hjemmelag = rad["Hjemmelag"]
        bortelag  = rad["Bortelag"]
        liga      = rad["Liga"]
        folk_h    = rad["Folk H%"]
        folk_u    = rad["Folk U%"]
        folk_b    = rad["Folk B%"]

        # ── Styrkeindekser ──
        styrke = styrke_cache.get(liga, {})
        h_styrke = fuzzy_match(styrke, hjemmelag)
        b_styrke = fuzzy_match(styrke, bortelag)

        # ── xG ──
        xg_liga = xg_cache.get(liga, {})
        h_xg = fuzzy_match(xg_liga, hjemmelag)
        b_xg = fuzzy_match(xg_liga, bortelag)

        # ── Poisson-modell ──
        poi = None
        if h_styrke and b_styrke:
            poi = poisson_modell(h_styrke, b_styrke, h_xg, b_xg)

        # ── Markedsodds ──
        odds_liste = odds_cache.get(liga, [])
        rå_odds = match_odds(odds_liste, hjemmelag, bortelag) if odds_liste else None
        impl = impl_pct(rå_odds)

        # ── Avvik ──
        poi_avvik = [
            (poi["H"] - folk_h) if poi else None,
            (poi["U"] - folk_u) if poi else None,
            (poi["B"] - folk_b) if poi else None,
        ]
        odds_avvik = [
            (impl["H"] - folk_h) if impl else None,
            (impl["U"] - folk_u) if impl else None,
            (impl["B"] - folk_b) if impl else None,
        ]
        alle_avvik = [abs(a) for a in poi_avvik + odds_avvik if a is not None]
        max_avvik  = max(alle_avvik, default=0)

        if bare_verdi and max_avvik < 8: continue
        if max_avvik < min_avvik: continue
        if max_avvik >= 8: verdikamper += 1

        har_verdi = max_avvik >= 8
        verdi_klasse = "kamp-kort verdi" if har_verdi else "kamp-kort"
        badge = "<span class='verdi-badge'>✦ VERDI</span>" if har_verdi else ""
        xg_badge = "<span class='xg-badge'>xG</span>" if (h_xg and b_xg) else ""

        # ── Render kort ──
        st.markdown(f"<div class='{verdi_klasse}'>", unsafe_allow_html=True)

        # Header
        st.markdown(f"""
        <div style='display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px'>
            <div>
                <div class='kamp-tittel'>{rad['Kamp']}{badge}</div>
                <div class='kamp-meta'>{liga} · {rad['Dato']} {xg_badge}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        k1, k2, k3 = st.columns(3)

        # ── Folkerekka ──
        with k1:
            farger = {"H": "folk-fill-H", "U": "folk-fill-U", "B": "folk-fill-B"}
            st.markdown("<div class='seksjon'>", unsafe_allow_html=True)
            st.markdown("<div class='sek-tittel'>👥 Folkerekka</div>", unsafe_allow_html=True)
            for label, utfall, val in [("Hjemme", "H", folk_h), ("Uavgjort", "U", folk_u), ("Borte", "B", folk_b)]:
                st.markdown(f"""
                <div class='folk-rad'>
                    <div class='folk-topp'><span>{label}</span><span><b>{val}%</b></span></div>
                    <div class='folk-bar'><div class='{farger[utfall]}' style='width:{val}%'></div></div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # ── Markedsodds ──
        with k2:
            st.markdown("<div class='seksjon'>", unsafe_allow_html=True)
            st.markdown("<div class='sek-tittel'>📈 Markedsodds</div>", unsafe_allow_html=True)
            if impl and rå_odds:
                for label, key, fv in [("Hjemme", "H", folk_h), ("Uavgjort", "U", folk_u), ("Borte", "B", folk_b)]:
                    avvik = round(impl.get(key, 0) - fv, 1)
                    prefix = "+" if avvik > 0 else ""
                    if avvik > 8: farge = "#22c55e"; ikon = "🟢"
                    elif avvik < -8: farge = "#ef4444"; ikon = "🔴"
                    else: farge = "#64748b"; ikon = "⚪"
                    st.markdown(f"""
                    <div class='utfall-rad'>
                        <span class='u-label'>{label}</span>
                        <span class='u-pct'>{impl.get(key,'–')}%</span>
                        <span class='u-odds'>odds {rå_odds.get(key,'–')}</span>
                        <span class='u-avvik' style='color:{farge}'>{ikon} {prefix}{avvik}pp</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("<div style='font-size:12px;color:#475569;font-style:italic'>Odds ikke tilgjengelig</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # ── Poisson-modell ──
        with k3:
            st.markdown("<div class='seksjon'>", unsafe_allow_html=True)
            xg_info = " (inkl. xG)" if poi and poi.get("brukte_xg") else ""
            st.markdown(f"<div class='sek-tittel'>🔢 Poisson-modell{xg_info}</div>", unsafe_allow_html=True)
            if poi:
                for label, key, pv, fv in [
                    ("Hjemme", "H", poi["H"], folk_h),
                    ("Uavgjort", "U", poi["U"], folk_u),
                    ("Borte", "B", poi["B"], folk_b),
                ]:
                    avvik = round(pv - fv, 1)
                    prefix = "+" if avvik > 0 else ""
                    if avvik > 8: farge = "#22c55e"; ikon = "🟢"
                    elif avvik < -8: farge = "#ef4444"; ikon = "🔴"
                    else: farge = "#64748b"; ikon = "⚪"
                    st.markdown(f"""
                    <div class='utfall-rad'>
                        <span class='u-label'>{label}</span>
                        <span class='u-pct'>{pv}%</span>
                        <span class='u-odds'></span>
                        <span class='u-avvik' style='color:{farge}'>{ikon} {prefix}{avvik}pp</span>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown(f"<div style='font-size:11px;color:#475569;margin-top:6px'>λ hjemme: {poi['xH']} · λ borte: {poi['xB']}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='font-size:12px;color:#475569;font-style:italic'>Ikke nok data for modellen</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # ── Lagstatistikk og styrkeindekser ──
        if h_styrke or b_styrke:
            st.markdown("<div style='border-top:1px solid #1e293b;margin:16px 0 12px'></div>", unsafe_allow_html=True)
            s1, s2 = st.columns(2)

            with s1:
                if h_styrke:
                    hj_xg_str = f" · xG: {h_xg.get('hjem_xg','–')}" if h_xg else ""
                    st.markdown(f"<div style='font-size:12px;font-weight:700;color:#94a3b8;margin-bottom:8px'>🏠 {hjemmelag} — hjemme{hj_xg_str}</div>", unsafe_allow_html=True)
                    st.markdown(f"""
                    <div class='stat-grid'>
                        <div class='stat-boks'>
                            <div class='stat-label'>Kamper</div>
                            <div class='stat-val'>{fd_cache.get(liga,{}).get(list(styrke.keys())[0] if styrke else '',{}).get('hjemme_spilt','–') if False else h_styrke.get('hjem_sc_snitt','–')}</div>
                        </div>
                        <div class='stat-boks'>
                            <div class='stat-label'>⚽ Scoret/kamp</div>
                            <div class='stat-val'>{h_styrke.get('hjem_sc_snitt','–')}</div>
                            <div class='stat-sub'>Angrepsstyrke: {h_styrke.get('angrep_hjem','–')}</div>
                        </div>
                        <div class='stat-boks'>
                            <div class='stat-label'>🥅 Innsluppet/kamp</div>
                            <div class='stat-val'>{h_styrke.get('hjem_in_snitt','–')}</div>
                            <div class='stat-sub'>Forsvarsstyrke: {h_styrke.get('forsvar_hjem','–')}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            with s2:
                if b_styrke:
                    bo_xg_str = f" · xG: {b_xg.get('borte_xg','–')}" if b_xg else ""
                    st.markdown(f"<div style='font-size:12px;font-weight:700;color:#94a3b8;margin-bottom:8px'>✈️ {bortelag} — borte{bo_xg_str}</div>", unsafe_allow_html=True)
                    st.markdown(f"""
                    <div class='stat-grid'>
                        <div class='stat-boks'>
                            <div class='stat-label'>⚽ Scoret/kamp</div>
                            <div class='stat-val'>{b_styrke.get('borte_sc_snitt','–')}</div>
                            <div class='stat-sub'>Angrepsstyrke: {b_styrke.get('angrep_borte','–')}</div>
                        </div>
                        <div class='stat-boks'>
                            <div class='stat-label'>🥅 Innsluppet/kamp</div>
                            <div class='stat-val'>{b_styrke.get('borte_in_snitt','–')}</div>
                            <div class='stat-sub'>Forsvarsstyrke: {b_styrke.get('forsvar_borte','–')}</div>
                        </div>
                        <div class='stat-boks'>
                            <div class='stat-label'>Ligasnitt hjem</div>
                            <div class='stat-val'>{b_styrke.get('liga_hjem_snitt','–')}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        # ── Verdioppsummering ──
        alle_poi = [("Hjemme", poi_avvik[0]), ("Uavgjort", poi_avvik[1]), ("Borte", poi_avvik[2])]
        beste = max(alle_poi, key=lambda x: abs(x[1]) if x[1] is not None else 0)
        if beste[1] is not None and beste[1] > 8:
            st.markdown(f"<div style='margin-top:12px;padding:10px 14px;background:#14532d;border-radius:8px;color:#4ade80;font-weight:700;font-size:13px'>🟢 Verdisignal: Poisson ser {beste[1]}pp mer sannsynlighet for <b>{beste[0]}</b> enn folkerekka</div>", unsafe_allow_html=True)
        elif beste[1] is not None and beste[1] < -8:
            st.markdown(f"<div style='margin-top:12px;padding:10px 14px;background:#7f1d1d;border-radius:8px;color:#fca5a5;font-weight:700;font-size:13px'>🔴 Obs: Folk overtipper <b>{beste[0]}</b> med {abs(beste[1])}pp vs modellen</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

# ─── Bunntall ───
st.divider()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Kamper vist", len(df_vis))
c2.metric("✦ Verdisignaler", verdikamper)
c3.metric("Ligaer m/ statistikk", len(fd_cache))
c4.metric("Ligaer m/ xG", len(xg_cache))
st.caption(f"Norsk Tipping · football-data.org · Understat (xG) · The Odds API · {datetime.now().strftime('%H:%M:%S')}")
