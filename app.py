import streamlit as st
import pandas as pd
import requests
from scipy.stats import poisson
from datetime import datetime

st.set_page_config(page_title="TippingAnalyse", page_icon="⚽", layout="wide")

# ─────────────────────────────────────────────
# API-NØKKEL (hentes sikkert fra Streamlit Secrets)
# ─────────────────────────────────────────────
try:
    ODDS_API_KEY = st.secrets["ODDS_API_KEY"]
except Exception:
    ODDS_API_KEY = None

# ─────────────────────────────────────────────
# KONSTANTER
# ─────────────────────────────────────────────

NT_API = "https://api.norsk-tipping.no/PoolGamesSportInfo/v1/api/tipping/live-info"

FOTMOB_LIGA_IDS = {
    "ENG Premier League": 47,
    "ENG Championship": 48,
    "ENG League 1": 49,
    "UEFA Champions League": 42,
    "UEFA Europa League": 73,
    "SPA LaLiga": 87,
    "ITA Serie A": 55,
    "GER Bundesliga": 54,
    "FRA Ligue 1": 53,
    "NOR Eliteserien": 59,
    "SKO Premiership": 65,
    "NED Eredivisie": 57,
}

# The Odds API sport-nøkler
ODDS_API_SPORT_KEYS = {
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
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
                "FotmobLigaId": FOTMOB_LIGA_IDS.get(liga),
                "OddsApiSport": ODDS_API_SPORT_KEYS.get(liga),
            })
    return pd.DataFrame(kamper)

# ─────────────────────────────────────────────
# THE ODDS API – MARKEDSODDS
# ─────────────────────────────────────────────

@st.cache_data(ttl=300)
def hent_alle_odds(sport_key):
    if not ODDS_API_KEY or not sport_key:
        return []
    try:
        url = "https://api.the-odds-api.com/v4/sports/{}/odds/".format(sport_key)
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "eu",
            "markets": "h2h",
            "oddsFormat": "decimal",
            "bookmakers": "pinnacle,bet365,unibet_eu",
        }
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []

def match_odds(odds_data, hjemmelag, bortelag):
    """Finn odds for en kamp ved fuzzy-matching av lagnavn."""
    h_lower = hjemmelag.lower()
    b_lower = bortelag.lower()

    for event in odds_data:
        eh = event.get("home_team", "").lower()
        eb = event.get("away_team", "").lower()

        h_match = any(ord in h_lower or h_lower in ord for ord in [eh, eh.split()[0]])
        b_match = any(ord in b_lower or b_lower in ord for ord in [eb, eb.split()[0]])

        if h_match and b_match:
            # Finn beste bookmaker (Pinnacle er mest presis)
            bookmakers = event.get("bookmakers", [])
            for bm_name in ["pinnacle", "bet365", "unibet_eu"]:
                for bm in bookmakers:
                    if bm_name in bm.get("key", ""):
                        for market in bm.get("markets", []):
                            if market.get("key") == "h2h":
                                outcomes = market.get("outcomes", [])
                                odds = {}
                                for o in outcomes:
                                    name = o.get("name", "").lower()
                                    price = o.get("price", 0)
                                    if eh in name or "home" in name:
                                        odds["H"] = price
                                    elif "draw" in name:
                                        odds["U"] = price
                                    elif eb in name or "away" in name:
                                        odds["B"] = price
                                if len(odds) == 3:
                                    return odds
    return None

def odds_til_impl_pct(odds_dict):
    """Konverter odds til implisitt sannsynlighet uten bookmaker-margin."""
    if not odds_dict:
        return None
    try:
        vig = sum(1/v for v in odds_dict.values() if v > 0)
        return {k: round((1/v)/vig*100, 1) for k, v in odds_dict.items() if v > 0}
    except:
        return None

# ─────────────────────────────────────────────
# FOTMOB STATISTIKK
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def hent_fotmob_tabell(liga_id):
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
            alle_tabeller = tabell_data.get("tables", [tabell_data])

            for t in alle_tabeller:
                ttype = t.get("type", "all")
                rows = []
                if isinstance(t.get("table"), dict):
                    rows = t["table"].get("rows", [])
                elif isinstance(t.get("table"), list):
                    rows = t["table"]
                if not rows:
                    rows = t.get("rows", [])

                for row in rows:
                    navn = row.get("name") or row.get("shortName", "")
                    if not navn:
                        continue
                    if navn not in lag_stats:
                        lag_stats[navn] = {}

                    spilt = int(row.get("played", 0) or 0)
                    scores_str = str(row.get("scoresStr", "0-0"))
                    parts = scores_str.split("-")
                    scoret = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
                    innsl = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

                    if ttype == "home":
                        lag_stats[navn].update({"hjemme_spilt": spilt, "hjemme_scoret": scoret, "hjemme_innsluppet": innsl})
                    elif ttype == "away":
                        lag_stats[navn].update({"borte_spilt": spilt, "borte_scoret": scoret, "borte_innsluppet": innsl})
                    else:
                        lag_stats[navn]["totalt_spilt"] = spilt

        return lag_stats
    except Exception:
        return {}

def fuzzy_match(lag_stats, lagnavn):
    if lagnavn in lag_stats:
        return lag_stats[lagnavn]
    l = lagnavn.lower()
    for k, v in lag_stats.items():
        if l in k.lower() or k.lower() in l:
            return v
    første = l.split()[0] if l.split() else ""
    for k, v in lag_stats.items():
        if første and første in k.lower():
            return v
    return None

def snitt(scoret, spilt):
    try:
        return round(int(scoret) / max(int(spilt), 1), 3)
    except:
        return None

# ─────────────────────────────────────────────
# POISSON-MODELL
# ─────────────────────────────────────────────

def poisson_modell(h_sc, b_in, b_sc, h_in, liga_hjem=1.5, liga_borte=1.1):
    try:
        lh = max(0.2, min((h_sc * b_in) / liga_hjem, 6.0))
        lb = max(0.2, min((b_sc * h_in) / liga_borte, 6.0))
        ph = pu = pb = 0.0
        for i in range(9):
            for j in range(9):
                p = poisson.pmf(i, lh) * poisson.pmf(j, lb)
                if i > j: ph += p
                elif i == j: pu += p
                else: pb += p
        tot = ph + pu + pb
        return {
            "H": round(ph/tot*100, 1),
            "U": round(pu/tot*100, 1),
            "B": round(pb/tot*100, 1),
            "xH": round(lh, 2),
            "xB": round(lb, 2),
        }
    except:
        return None

# ─────────────────────────────────────────────
# VISNINGSHJELPERE
# ─────────────────────────────────────────────

def signal(avvik):
    if avvik is None: return "⚪", "gray"
    if avvik > 8: return "🟢", "green"
    if avvik < -8: return "🔴", "red"
    return "⚪", "gray"

def vis_avvik(label, modell_pct, folk_pct):
    if modell_pct is None:
        return
    avvik = round(modell_pct - folk_pct, 1)
    ikon, farge = signal(avvik)
    prefix = "+" if avvik > 0 else ""
    st.markdown(
        f"**{label}:** {modell_pct}% &nbsp; "
        f"<span style='color:{farge};font-weight:bold'>{ikon} {prefix}{avvik}pp vs folk</span>",
        unsafe_allow_html=True
    )

# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

st.title("⚽ TippingAnalyse")
st.caption("Folkerekke · Markedsodds · Poisson-modell · Verdianalyse")

if not ODDS_API_KEY:
    st.warning("⚠️ Odds API-nøkkel ikke funnet. Legg den inn under App Settings → Secrets.")

# Last NT
with st.spinner("Henter tippekupong fra Norsk Tipping..."):
    nt_json, nt_feil = hent_nt_data()
if nt_feil or not nt_json:
    st.error(f"Kunne ikke hente NT-data: {nt_feil}")
    st.stop()

df = prosesser_nt(nt_json)
st.success(f"✅ Hentet {len(df)} kamper fra Norsk Tipping")

# Last Fotmob
liga_stats_cache = {}
with st.spinner("Henter statistikk fra Fotmob..."):
    for liga, lid in FOTMOB_LIGA_IDS.items():
        if liga in df["Liga"].values:
            stats = hent_fotmob_tabell(lid)
            if stats:
                liga_stats_cache[liga] = stats
if liga_stats_cache:
    st.success(f"✅ Fotmob-statistikk lastet for {len(liga_stats_cache)} ligaer")

# Last odds fra The Odds API
odds_cache = {}
if ODDS_API_KEY:
    with st.spinner("Henter markedsodds fra The Odds API..."):
        for liga, sport_key in ODDS_API_SPORT_KEYS.items():
            if liga in df["Liga"].values:
                odds_data = hent_alle_odds(sport_key)
                if odds_data:
                    odds_cache[liga] = odds_data
    if odds_cache:
        st.success(f"✅ Markedsodds hentet for {len(odds_cache)} ligaer")

# ─── Forklaring ───
with st.expander("ℹ️ Slik leser du analysen"):
    st.markdown("""
    | Parameter | Kilde | Beskrivelse |
    |-----------|-------|-------------|
    | 👥 **Folkerekka** | Norsk Tipping | Hva vanlige tippere tror (%) |
    | 📈 **Markedsodds** | The Odds API (Pinnacle/Bet365) | Hva de skarpeste bookmakers mener (%) |
    | 🔢 **Poisson-modell** | Fotmob-statistikk | Matematisk beregnet fra mål-statistikk |

    - 🟢 **Grønn (+pp)** = Modellen/oddsen ser MER verdi enn folk → **potensielt underspilt**
    - 🔴 **Rød (-pp)** = Folk overtipper dette utfallet → **potensielt overspilt**
    - **xH – xB** = Forventet målscoring ifølge Poisson-modellen
    """)

# ─── Filter ───
st.sidebar.header("🔍 Filter")
dag_valg = st.sidebar.multiselect("Kupong", options=df["Dag"].unique(), default=df["Dag"].unique())
df_vis = df[df["Dag"].isin(dag_valg)].copy()
bare_verdi = st.sidebar.checkbox("Vis bare kamper med verdisignal (>8pp)")
min_avvik = st.sidebar.slider("Minste avvik å vise (pp)", 0, 20, 0)

if st.button("🔄 Oppdater alle data"):
    st.cache_data.clear()
    st.rerun()

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
        folk_h, folk_u, folk_b = rad["Folk H%"], rad["Folk U%"], rad["Folk B%"]

        # ── Fotmob statistikk ──
        lag_stats = liga_stats_cache.get(liga, {})
        h_stats = fuzzy_match(lag_stats, hjemmelag) if lag_stats else None
        b_stats = fuzzy_match(lag_stats, bortelag)  if lag_stats else None

        h_sc = snitt(h_stats.get("hjemme_scoret", 0), h_stats.get("hjemme_spilt", 1)) if h_stats else None
        h_in = snitt(h_stats.get("hjemme_innsluppet", 0), h_stats.get("hjemme_spilt", 1)) if h_stats else None
        b_sc = snitt(b_stats.get("borte_scoret", 0), b_stats.get("borte_spilt", 1)) if b_stats else None
        b_in = snitt(b_stats.get("borte_innsluppet", 0), b_stats.get("borte_spilt", 1)) if b_stats else None

        # ── Poisson ──
        poi = poisson_modell(h_sc, b_in, b_sc, h_in) if all(x is not None for x in [h_sc, h_in, b_sc, b_in]) else None

        # ── Markedsodds ──
        odds_data = odds_cache.get(liga, [])
        rå_odds = match_odds(odds_data, hjemmelag, bortelag) if odds_data else None
        impl = odds_til_impl_pct(rå_odds)

        # ── Avvik beregning ──
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

        max_avvik = max(
            [abs(a) for a in poi_avvik + odds_avvik if a is not None],
            default=0
        )

        if bare_verdi and max_avvik < 8:
            continue
        if max_avvik < min_avvik:
            continue
        if max_avvik >= 8:
            verdikamper += 1

        # ── Tittel-ikon ──
        alle_avvik = [a for a in poi_avvik + odds_avvik if a is not None]
        beste = max(alle_avvik, key=abs, default=0)
        tittel_ikon, _ = signal(beste)
        tittel_ikon = tittel_ikon if abs(beste) > 8 else ""

        with st.expander(f"{tittel_ikon} {rad['Kamp']}  —  {liga}  ({rad['Dato']})"):

            k1, k2, k3 = st.columns(3)

            # ── Folkerekka ──
            with k1:
                st.markdown("#### 👥 Folkerekka")
                for label, val in [("Hjemme (H)", folk_h), ("Uavgjort (U)", folk_u), ("Borte (B)", folk_b)]:
                    st.markdown(f"**{label}:** {val}%")
                    st.progress(int(val))

            # ── Markedsodds ──
            with k2:
                st.markdown("#### 📈 Markedsodds")
                if rå_odds and impl:
                    for label, key, folk_val in [
                        ("Hjemme (H)", "H", folk_h),
                        ("Uavgjort (U)", "U", folk_u),
                        ("Borte (B)", "B", folk_b)
                    ]:
                        odds_val = rå_odds.get(key, "–")
                        impl_val = impl.get(key)
                        vis_avvik(f"{label} (odds {odds_val})", impl_val, folk_val)
                else:
                    st.info("Markedsodds ikke tilgjengelig for denne kampen")

            # ── Poisson-modell ──
            with k3:
                st.markdown("#### 🔢 Poisson-modell")
                if poi:
                    vis_avvik("Hjemme (H)", poi["H"], folk_h)
                    vis_avvik("Uavgjort (U)", poi["U"], folk_u)
                    vis_avvik("Borte (B)", poi["B"], folk_b)
                    st.caption(f"Forventet mål: {poi['xH']} – {poi['xB']}")
                else:
                    st.info("Ikke nok statistikk for Poisson-beregning")
                    if not h_stats: st.caption(f"Fant ikke {hjemmelag} i Fotmob")
                    if not b_stats: st.caption(f"Fant ikke {bortelag} i Fotmob")

            # ── Lagstatistikk ──
            if h_stats or b_stats:
                st.divider()
                st.markdown("#### 📊 Lagstatistikk (Fotmob)")
                s1, s2 = st.columns(2)
                with s1:
                    st.markdown(f"**🏠 {hjemmelag} hjemme**")
                    if h_stats and h_sc is not None:
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Kamper", h_stats.get("hjemme_spilt", "–"))
                        c2.metric("⚽ Scoret/k", h_sc)
                        c3.metric("🥅 Innsl./k", h_in)
                with s2:
                    st.markdown(f"**✈️ {bortelag} borte**")
                    if b_stats and b_sc is not None:
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Kamper", b_stats.get("borte_spilt", "–"))
                        c2.metric("⚽ Scoret/k", b_sc)
                        c3.metric("🥅 Innsl./k", b_in)

            # ── Verdioppsummering ──
            alle_med_label = [
                ("Hjemme", poi_avvik[0]), ("Uavgjort", poi_avvik[1]), ("Borte", poi_avvik[2]),
            ]
            beste_poi = max(alle_med_label, key=lambda x: abs(x[1]) if x[1] is not None else 0)
            if beste_poi[1] is not None and beste_poi[1] > 8:
                st.success(f"🟢 **Verdisignal:** Poisson ser {beste_poi[1]}pp mer sannsynlighet for **{beste_poi[0]}** enn folkerekka")
            elif beste_poi[1] is not None and beste_poi[1] < -8:
                st.warning(f"🔴 **Obs:** Folk overtipper **{beste_poi[0]}** med {abs(beste_poi[1])}pp vs. modellen")

st.divider()
c1, c2, c3 = st.columns(3)
c1.metric("Kamper vist", len(df_vis))
c2.metric("🟢 Verdisignaler", verdikamper)
c3.metric("Ligaer m/ statistikk", len(liga_stats_cache))
st.caption(f"NT API + Fotmob + The Odds API · {datetime.now().strftime('%H:%M:%S')}")
