"""
Delt FotMob API- og modellkode.
Brukes av app.py (med @st.cache_data) og backtest.py (uten caching).
"""

import requests
import unicodedata
import numpy as np
from scipy.stats import poisson

from backtest_config import DEFAULT_PARAMS

# ─────────────────────────────────────────────
# KONSTANTER
# ─────────────────────────────────────────────

FOTMOB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.fotmob.com/",
}

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
# HJELPEFUNKSJONER
# ─────────────────────────────────────────────

def _normalize(s):
    """Fjerner diakritiske tegn og gjør lowercase for fuzzy matching."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()


def resolve_team(lag_stats, lagnavn):
    """Finner lag i FotMob-tabellen basert på NT-navnet.
    Returnerer (fotmob_navn, stats_dict) eller (None, None)."""
    if not lag_stats:
        return None, None

    override = TEAM_NAME_OVERRIDES.get(lagnavn, lagnavn)

    if override in lag_stats:
        return override, lag_stats[override]

    if lagnavn in lag_stats:
        return lagnavn, lag_stats[lagnavn]

    l = override.lower()
    for k, v in lag_stats.items():
        if l in k.lower() or k.lower() in l:
            return k, v

    l_norm = _normalize(override)
    for k, v in lag_stats.items():
        k_norm = _normalize(k)
        if l_norm in k_norm or k_norm in l_norm:
            return k, v

    første_ord = l_norm.split()[0] if l_norm.split() else ""
    if første_ord and len(første_ord) > 2:
        for k, v in lag_stats.items():
            if første_ord in _normalize(k):
                return k, v

    return None, None


# ─────────────────────────────────────────────
# DATAHENTING: FOTMOB
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
            inner_table = tabell_data.get("table", {})

            table_dicts = []

            if isinstance(inner_table, dict) and "all" in inner_table:
                table_dicts.append(inner_table)
            elif tabell_data.get("tables"):
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
            total_hjemme_scoret += stats.get("hjemme_scoret", 0)
            total_borte_scoret += stats.get("borte_scoret", 0)
            total_hjemme_kamper += stats.get("hjemme_spilt", 0)
            total_borte_kamper += stats.get("borte_spilt", 0)

        league_avg_home = total_hjemme_scoret / max(total_hjemme_kamper, 1)
        league_avg_away = total_borte_scoret / max(total_borte_kamper, 1)

        return {
            "teams": lag_stats,
            "league_avg_home": round(league_avg_home, 3),
            "league_avg_away": round(league_avg_away, 3),
        }
    except Exception:
        return {}


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

        overview = data.get("overview", {})
        team_form = overview.get("teamForm", [])
        for tf in team_form:
            result_str = tf.get("resultString", "")
            score = tf.get("score", "")
            tooltip = tf.get("tooltipText", {})
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
                                        xg_data[team_name] = float(xg_val) / max(int(matches), 1)
                                    except (ValueError, TypeError):
                                        pass
                break

        return xg_data
    except Exception:
        return {}


# ─────────────────────────────────────────────
# MODELL: STYRKE OG FORM
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


def beregn_form_styrke(fixtures, team_id, is_home_team, form_window=None):
    """Beregner styrke basert på siste N relevante kamper (hjemme eller borte).
    form_window: antall kamper å se på (default: DEFAULT_PARAMS['form_window'])."""
    if form_window is None:
        form_window = DEFAULT_PARAMS["form_window"]
    if not fixtures:
        return None

    relevante = []
    for fx in reversed(fixtures):
        if is_home_team and fx["is_home"]:
            relevante.append(fx)
        elif not is_home_team and not fx["is_home"]:
            relevante.append(fx)
        if len(relevante) >= form_window:
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
                        h_form=None, b_form=None, h_xg=None, b_xg=None,
                        params=None):
    """
    Dyp Poisson-modell med styrkeratings, form-vekting og valgfri xG-justering.
    params: dict med modellparametre (bruker DEFAULT_PARAMS hvis None).
    Returnerer dict med sannsynligheter, forventede mål, topp-resultater og modellnivå.
    """
    if params is None:
        params = DEFAULT_PARAMS
    try:
        styrke = beregn_styrke(h_stats, b_stats, league_avg_home, league_avg_away)

        # Sesongbasert lambda
        lambda_h_season = styrke["home_attack"] * styrke["away_defense"] * league_avg_home
        lambda_b_season = styrke["away_attack"] * styrke["home_defense"] * league_avg_away

        modell_nivaa = "Basis (sesongsnitt)"

        form_weight = params.get("form_weight", DEFAULT_PARAMS["form_weight"])
        xg_weight = params.get("xg_weight", DEFAULT_PARAMS["xg_weight"])
        lambda_min = params.get("lambda_min", DEFAULT_PARAMS["lambda_min"])
        lambda_max = params.get("lambda_max", DEFAULT_PARAMS["lambda_max"])

        # Form-blending
        lambda_h = lambda_h_season
        lambda_b = lambda_b_season
        if h_form and b_form:
            lambda_h_form = h_form["scoret_snitt"] * (b_form["innsluppet_snitt"] / max(league_avg_home, 0.5))
            lambda_b_form = b_form["scoret_snitt"] * (h_form["innsluppet_snitt"] / max(league_avg_away, 0.5))
            season_weight = 1.0 - form_weight
            lambda_h = season_weight * lambda_h_season + form_weight * lambda_h_form
            lambda_b = season_weight * lambda_b_season + form_weight * lambda_b_form
            modell_nivaa = "Dyp (form)"

        # xG-justering
        if h_xg is not None and b_xg is not None and xg_weight > 0:
            xg_h_factor = h_xg / max(league_avg_home + league_avg_away, 1) * 2
            xg_b_factor = b_xg / max(league_avg_home + league_avg_away, 1) * 2
            goal_weight = 1.0 - xg_weight
            lambda_h = goal_weight * lambda_h + xg_weight * (xg_h_factor * league_avg_home)
            lambda_b = goal_weight * lambda_b + xg_weight * (xg_b_factor * league_avg_away)
            modell_nivaa = "Dyp (form+xG)"

        # Clamp
        lambda_h = max(lambda_min, min(lambda_h, lambda_max))
        lambda_b = max(lambda_min, min(lambda_b, lambda_max))

        # Poisson-grid
        max_maal = 8
        score_matrise = np.zeros((max_maal + 1, max_maal + 1))
        for i in range(max_maal + 1):
            for j in range(max_maal + 1):
                score_matrise[i][j] = poisson.pmf(i, lambda_h) * poisson.pmf(j, lambda_b)

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
