import streamlit as st
import pandas as pd
import requests
from scipy.stats import poisson
from datetime import datetime
import numpy as np
import unicodedata

st.set_page_config(page_title="TippingAnalyse", page_icon="⚽", layout="wide")

# ─────────────────────────────────────────────
# KONSTANTER
# ─────────────────────────────────────────────

NT_API = "https://api.norsk-tipping.no/PoolGamesSportInfo/v1/api/tipping/live-info"

FOTMOB_LIGA_IDS = {
    "ENG Premier League": 47,
    "ENG Championship": 48,
    "ENG League 1": 49,
    "ENG League 2": 50,
    "UEFA Champions League": 42,
    "Champions League": 42,
    "UEFA Europa League": 73,
    "Europa League": 73,
    "SPA LaLiga": 87,
    "ITA Serie A": 55,
    "GER Bundesliga": 54,
    "TYS 1. Bundesliga": 54,
    "FRA Ligue 1": 53,
    "NOR Eliteserien": 59,
    "SKO Premiership": 65,
    "NED Eredivisie": 57,
    "POR Primeira Liga": 61,
    "TUR Süper Lig": 71,
}

FOTMOB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.fotmob.com/",
}

# Manuell override for kjente avvik mellom NT-navn og FotMob-navn
TEAM_NAME_OVERRIDES = {
    "Wolverhampton": "Wolverhampton Wanderers",
    "Wolves": "Wolverhampton Wanderers",
    "Nott'm Forest": "Nottingham Forest",
    "Nottingham": "Nottingham Forest",
    "West Ham United": "West Ham",
    "Tottenham Hotspur": "Tottenham",
    "Spurs": "Tottenham",
    "Man City": "Manchester City",
    "Man Utd": "Manchester United",
    "Man United": "Manchester United",
    "Newcastle Utd": "Newcastle United",
    "Newcastle": "Newcastle United",
    "Brighton": "Brighton and Hove Albion",
    "Sheffield Utd": "Sheffield United",
    "Atlético": "Atletico Madrid",
    "Atletico": "Atletico Madrid",
    "Athletic": "Athletic Club",
    "Real Sociedad": "Real Sociedad",
    "St. Pauli": "FC St. Pauli",
    "PSG": "Paris Saint-Germain",
    "St Mirren": "St. Mirren",
    "Ross Co": "Ross County",
    "Røde Stjerne": "FK Crvena Zvezda",
    "Rode Stjerne": "FK Crvena Zvezda",
    "Crvena Zvezda": "FK Crvena Zvezda",
    "Fenerbahce": "Fenerbahçe",
    "Galatasaray": "Galatasaray",
    "Besiktas": "Beşiktaş",
    "Malmo": "Malmö FF",
    "Malmö": "Malmö FF",
}

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
# DATAHENTING: FOTMOB LIGASTATISTIKK
# ─────────────────────────────────────────────

def _parse_table_row(lag_stats, row, ttype):
    """Parser en tabellrad fra FotMob og oppdaterer lag_stats."""
    navn = row.get("name") or row.get("shortName", "")
    if not navn:
        return
    if navn not in lag_stats:
        lag_stats[navn] = {}

    team_id = row.get("id")
    if team_id:
        lag_stats[navn]["team_id"] = team_id

    spilt = int(row.get("played", 0) or 0)
    scores_str = str(row.get("scoresStr", "0-0"))
    parts = scores_str.split("-")
    scoret = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    innsl = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

    if ttype == "home":
        lag_stats[navn]["hjemme_spilt"] = spilt
        lag_stats[navn]["hjemme_scoret"] = scoret
        lag_stats[navn]["hjemme_innsluppet"] = innsl
    elif ttype == "away":
        lag_stats[navn]["borte_spilt"] = spilt
        lag_stats[navn]["borte_scoret"] = scoret
        lag_stats[navn]["borte_innsluppet"] = innsl
    else:
        lag_stats[navn]["totalt_spilt"] = spilt

@st.cache_data(ttl=3600)
def hent_fotmob_tabell(liga_id):
    """Henter hjemme/borte-tabell fra FotMob, inkl. lag-ID-er og ligasnitt."""
    try:
        url = f"https://www.fotmob.com/api/leagues?id={liga_id}&tab=table&type=league&timeZone=Europe/Oslo"
        r = requests.get(url, headers=FOTMOB_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()

        lag_stats = {}
        tabell_liste = data.get("table", [])
        if not isinstance(tabell_liste, list):
            tabell_liste = [tabell_liste]

        for tabell in tabell_liste:
            tabell_data = tabell.get("data", {})
            # FotMob structure: data.table is a dict with keys "all", "home", "away"
            inner_table = tabell_data.get("table", {})

            # Samle alle tabell-dicts som inneholder {all, home, away}
            table_dicts = []

            if isinstance(inner_table, dict) and "all" in inner_table:
                # Standard liga: data.table.{all, home, away}
                table_dicts.append(inner_table)
            elif tabell_data.get("tables"):
                # Turneringer (CL/EL): data.tables[].table.{all, home, away}
                for sub in tabell_data["tables"]:
                    sub_tbl = sub.get("table", {})
                    if isinstance(sub_tbl, dict) and "all" in sub_tbl:
                        table_dicts.append(sub_tbl)

            for tbl in table_dicts:
                for ttype in ("all", "home", "away"):
                    rows = tbl.get(ttype, [])
                    if not isinstance(rows, list):
                        continue
                    for row in rows:
                        _parse_table_row(lag_stats, row, ttype)

        # Beregn ligasnitt
        total_hjemme_scoret = 0
        total_borte_scoret = 0
        total_hjemme_kamper = 0
        total_borte_kamper = 0
        for stats in lag_stats.values():
            hs = stats.get("hjemme_spilt", 0)
            bs = stats.get("borte_spilt", 0)
            total_hjemme_scoret += stats.get("hjemme_scoret", 0)
            total_borte_scoret += stats.get("borte_scoret", 0)
            total_hjemme_kamper += hs
            total_borte_kamper += bs

        league_avg_home = total_hjemme_scoret / max(total_hjemme_kamper, 1)
        league_avg_away = total_borte_scoret / max(total_borte_kamper, 1)

        return {
            "teams": lag_stats,
            "league_avg_home": round(league_avg_home, 3),
            "league_avg_away": round(league_avg_away, 3),
        }
    except Exception:
        return {}

# ─────────────────────────────────────────────
# DATAHENTING: FOTMOB LAGDATA (kamper + form)
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def hent_fotmob_team(team_id):
    """Henter lagets kamper og form fra FotMob."""
    if not team_id:
        return None
    try:
        url = f"https://www.fotmob.com/api/teams?id={team_id}"
        r = requests.get(url, headers=FOTMOB_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()

        result = {"team_id": team_id, "fixtures": [], "form": []}

        # Hent alle kamper
        fixtures_data = data.get("fixtures", {})
        all_fixtures = fixtures_data.get("allFixtures", {}).get("fixtures", [])
        for fx in all_fixtures:
            status = fx.get("status", {})
            if not status.get("finished", False):
                continue
            home = fx.get("home", {})
            away = fx.get("away", {})
            home_score = home.get("score")
            away_score = away.get("score")
            if home_score is None or away_score is None:
                continue
            try:
                home_goals = int(home_score)
                away_goals = int(away_score)
            except (ValueError, TypeError):
                continue

            result["fixtures"].append({
                "home_id": home.get("id"),
                "home_name": home.get("name", ""),
                "away_id": away.get("id"),
                "away_name": away.get("name", ""),
                "home_goals": home_goals,
                "away_goals": away_goals,
                "is_home": home.get("id") == team_id,
            })

        # Hent form (siste 5)
        overview = data.get("overview", {})
        team_form = overview.get("teamForm", [])
        for tf in team_form:
            result_str = tf.get("resultString", "")  # W/D/L
            score = tf.get("score", "")
            tooltip = tf.get("tooltipText", {})
            # Bestem opponent og hjemme/borte fra tooltip
            if tooltip.get("homeTeamId") == team_id:
                opponent = tooltip.get("awayTeam", "")
                is_home = True
            else:
                opponent = tooltip.get("homeTeam", "")
                is_home = False
            result["form"].append({
                "result": result_str,
                "score": score,
                "opponent": opponent,
                "is_home": is_home,
            })

        return result
    except Exception:
        return None

# ─────────────────────────────────────────────
# DATAHENTING: FOTMOB xG-DATA
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def hent_fotmob_xg(liga_id):
    """Henter xG-data fra FotMob stats-endepunkt. Returnerer dict: lagnavn → xG per kamp."""
    try:
        url = f"https://www.fotmob.com/api/leagues?id={liga_id}&tab=stats&type=league&timeZone=Europe/Oslo"
        r = requests.get(url, headers=FOTMOB_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()

        team_stats = data.get("stats", {}).get("teams", [])
        xg_data = {}

        for category in team_stats:
            header = category.get("header", "").lower()
            if "expected goals" in header and "conceded" not in header and "difference" not in header:
                # fetchAllUrl er på category-nivå
                fetch_url = category.get("fetchAllUrl", "")
                if fetch_url:
                    xg_r = requests.get(fetch_url, headers=FOTMOB_HEADERS, timeout=10)
                    if xg_r.status_code == 200:
                        xg_json = xg_r.json()
                        top_lists = xg_json.get("TopLists", [])
                        if top_lists:
                            for entry in top_lists[0].get("StatList", []):
                                team_name = entry.get("ParticipantName", "")
                                xg_val = entry.get("StatValue")
                                matches = entry.get("MatchesPlayed", 1)
                                if xg_val is not None and team_name:
                                    try:
                                        # Konverter til xG per kamp
                                        xg_data[team_name] = float(xg_val) / max(int(matches), 1)
                                    except (ValueError, TypeError):
                                        pass
                break

        return xg_data
    except Exception:
        return {}

# ─────────────────────────────────────────────
# LAG-ID-MAPPING (NT-NAVN → FOTMOB)
# ─────────────────────────────────────────────

def _normalize(s):
    """Fjerner diakritiske tegn og gjør lowercase for fuzzy matching."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()

def resolve_team(lag_stats, lagnavn):
    """Finner lag i FotMob-tabellen basert på NT-navnet.
    Returnerer (fotmob_navn, stats_dict) eller (None, None)."""
    if not lag_stats:
        return None, None

    # Sjekk override først
    override = TEAM_NAME_OVERRIDES.get(lagnavn, lagnavn)

    # Eksakt match
    if override in lag_stats:
        return override, lag_stats[override]

    # Eksakt match med original
    if lagnavn in lag_stats:
        return lagnavn, lag_stats[lagnavn]

    # Substring-match (case-insensitive)
    l = override.lower()
    for k, v in lag_stats.items():
        if l in k.lower() or k.lower() in l:
            return k, v

    # Unicode-normalisert match (fjerner ç→c, ö→o, etc.)
    l_norm = _normalize(override)
    for k, v in lag_stats.items():
        k_norm = _normalize(k)
        if l_norm in k_norm or k_norm in l_norm:
            return k, v

    # Første ord
    første_ord = l_norm.split()[0] if l_norm.split() else ""
    if første_ord and len(første_ord) > 2:
        for k, v in lag_stats.items():
            if første_ord in _normalize(k):
                return k, v

    return None, None

# ─────────────────────────────────────────────
# DYP POISSON-MODELL
# ─────────────────────────────────────────────

def beregn_styrke(h_stats, b_stats, league_avg_home, league_avg_away):
    """Beregner attack/defense strength ratios for hjemme- og bortelag."""
    h_spilt = max(h_stats.get("hjemme_spilt", 0), 1)
    b_spilt = max(b_stats.get("borte_spilt", 0), 1)

    home_attack = (h_stats.get("hjemme_scoret", 0) / h_spilt) / max(league_avg_home, 0.5)
    home_defense = (h_stats.get("hjemme_innsluppet", 0) / h_spilt) / max(league_avg_away, 0.5)
    away_attack = (b_stats.get("borte_scoret", 0) / b_spilt) / max(league_avg_away, 0.5)
    away_defense = (b_stats.get("borte_innsluppet", 0) / b_spilt) / max(league_avg_home, 0.5)

    return {
        "home_attack": round(home_attack, 3),
        "home_defense": round(home_defense, 3),
        "away_attack": round(away_attack, 3),
        "away_defense": round(away_defense, 3),
    }

def beregn_form_styrke(fixtures, team_id, is_home_team):
    """Beregner styrke basert på siste 10 relevante kamper (hjemme eller borte)."""
    if not fixtures:
        return None

    relevante = []
    for fx in reversed(fixtures):  # nyeste først
        if is_home_team and fx["is_home"]:
            relevante.append(fx)
        elif not is_home_team and not fx["is_home"]:
            relevante.append(fx)
        if len(relevante) >= 10:
            break

    if len(relevante) < 3:
        return None

    scoret = sum(fx["home_goals"] if fx["is_home"] else fx["away_goals"] for fx in relevante)
    innsluppet = sum(fx["away_goals"] if fx["is_home"] else fx["home_goals"] for fx in relevante)

    return {
        "kamper": len(relevante),
        "scoret_snitt": round(scoret / len(relevante), 3),
        "innsluppet_snitt": round(innsluppet / len(relevante), 3),
    }

def beregn_dyp_poisson(h_stats, b_stats, league_avg_home, league_avg_away,
                        h_form=None, b_form=None, h_xg=None, b_xg=None):
    """
    Dyp Poisson-modell med styrkeratings, form-vekting og valgfri xG-justering.
    Returnerer dict med sannsynligheter, forventede mål, topp-resultater og modellnivå.
    """
    try:
        styrke = beregn_styrke(h_stats, b_stats, league_avg_home, league_avg_away)

        # Sesongbasert lambda
        lambda_h_season = styrke["home_attack"] * styrke["away_defense"] * league_avg_home
        lambda_b_season = styrke["away_attack"] * styrke["home_defense"] * league_avg_away

        modell_nivaa = "Basis (sesongsnitt)"

        # Form-blending: 60% siste kamper, 40% sesongsnitt
        lambda_h = lambda_h_season
        lambda_b = lambda_b_season
        if h_form and b_form:
            lambda_h_form = h_form["scoret_snitt"] * (b_form["innsluppet_snitt"] / max(league_avg_home, 0.5))
            lambda_b_form = b_form["scoret_snitt"] * (h_form["innsluppet_snitt"] / max(league_avg_away, 0.5))
            lambda_h = 0.4 * lambda_h_season + 0.6 * lambda_h_form
            lambda_b = 0.4 * lambda_b_season + 0.6 * lambda_b_form
            modell_nivaa = "Dyp (form)"

        # xG-justering: 30% xG, 70% mål-basert
        if h_xg is not None and b_xg is not None:
            h_spilt = max(h_stats.get("hjemme_spilt", 0) + h_stats.get("borte_spilt", 0), 1)
            b_spilt = max(b_stats.get("hjemme_spilt", 0) + b_stats.get("borte_spilt", 0), 1)
            # xG er typisk totalt per kamp, bruk som justering
            xg_h_factor = h_xg / max(league_avg_home + league_avg_away, 1) * 2
            xg_b_factor = b_xg / max(league_avg_home + league_avg_away, 1) * 2
            lambda_h = 0.7 * lambda_h + 0.3 * (xg_h_factor * league_avg_home)
            lambda_b = 0.7 * lambda_b + 0.3 * (xg_b_factor * league_avg_away)
            modell_nivaa = "Dyp (form+xG)"

        # Clamp
        lambda_h = max(0.2, min(lambda_h, 6.0))
        lambda_b = max(0.2, min(lambda_b, 6.0))

        # Poisson-grid
        max_maal = 8
        score_matrise = np.zeros((max_maal + 1, max_maal + 1))
        for i in range(max_maal + 1):
            for j in range(max_maal + 1):
                score_matrise[i][j] = poisson.pmf(i, lambda_h) * poisson.pmf(j, lambda_b)

        prob_h = np.sum(np.tril(score_matrise, -1))  # hjemmelag vinner: i > j
        prob_u = np.sum(np.diag(score_matrise))
        prob_b = np.sum(np.triu(score_matrise, 1))    # bortelag vinner: j > i

        # Korreksjon: tril gir nedre trekant (i > j for rad > kol), men vi har [home][away]
        # score_matrise[i][j] = P(home=i, away=j), så home wins when i > j
        prob_h = 0.0
        prob_u = 0.0
        prob_b = 0.0
        for i in range(max_maal + 1):
            for j in range(max_maal + 1):
                p = score_matrise[i][j]
                if i > j:
                    prob_h += p
                elif i == j:
                    prob_u += p
                else:
                    prob_b += p

        total = prob_h + prob_u + prob_b

        # Topp 3 mest sannsynlige resultater
        flat = []
        for i in range(max_maal + 1):
            for j in range(max_maal + 1):
                flat.append((i, j, score_matrise[i][j]))
        flat.sort(key=lambda x: x[2], reverse=True)
        topp_resultater = [(f"{r[0]}-{r[1]}", round(r[2] / total * 100, 1)) for r in flat[:3]]

        return {
            "H": round(prob_h / total * 100, 1),
            "U": round(prob_u / total * 100, 1),
            "B": round(prob_b / total * 100, 1),
            "lambda_h": round(lambda_h, 2),
            "lambda_b": round(lambda_b, 2),
            "styrke": styrke,
            "topp_resultater": topp_resultater,
            "modell_nivaa": modell_nivaa,
        }
    except Exception:
        return None

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
# APP START
# ─────────────────────────────────────────────

st.title("⚽ TippingAnalyse")
st.caption("Folkerekke · Dyp Poisson-analyse · Form · H2H · Verdianalyse")

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
        h_team_data["fixtures"] if h_team_data else None, h_team_id, True
    ) if h_team_data else None
    b_form = beregn_form_styrke(
        b_team_data["fixtures"] if b_team_data else None, b_team_id, False
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
        width="stretch",
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
