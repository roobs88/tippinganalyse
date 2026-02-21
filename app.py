import streamlit as st
import pandas as pd
import requests
from scipy.stats import poisson
from datetime import datetime
import numpy as np

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
    "UEFA Europa League": 73,
    "SPA LaLiga": 87,
    "ITA Serie A": 55,
    "GER Bundesliga": 54,
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
            betradar_id = m.get("gameEngineBetRadarId")

            kamper.append({
                "Dag": dag_navn,
                "Kamp": m.get("name", ""),
                "Hjemmelag": m.get("teams", {}).get("home", {}).get("webName", ""),
                "Bortelag": m.get("teams", {}).get("away", {}).get("webName", ""),
                "Liga": liga,
                "Dato": dato,
                "BetRadarId": betradar_id,
                "Folk H%": folk.get("home", 0),
                "Folk U%": folk.get("draw", 0),
                "Folk B%": folk.get("away", 0),
                "FotmobLigaId": FOTMOB_LIGA_IDS.get(liga),
            })
    return pd.DataFrame(kamper)

# ─────────────────────────────────────────────
# DATAHENTING: NT LANGODDSEN (via Sportradar)
# ─────────────────────────────────────────────

@st.cache_data(ttl=300)
def hent_nt_odds(betradar_id):
    """Prøv å hente Norsk Tipping sine egne odds via Sportradar-event-ID."""
    if not betradar_id:
        return None
    try:
        # NT bruker Sportradar internt – prøv direkte odds-endepunkt
        url = f"https://api.norsk-tipping.no/SportsbookFeed/v1/api/events/{betradar_id}/markets"
        headers = {"Accept": "application/json", "Origin": "https://www.norsk-tipping.no"}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            # Finn 1X2-markedet
            for market in data.get("markets", []):
                if "1X2" in market.get("name", "") or market.get("typeId") in [1, 186]:
                    outcomes = market.get("outcomes", [])
                    odds = {}
                    for o in outcomes:
                        name = o.get("name", "").lower()
                        val = o.get("odds") or o.get("price")
                        if val:
                            if "home" in name or name == "1":
                                odds["H"] = val
                            elif "draw" in name or name == "x":
                                odds["U"] = val
                            elif "away" in name or name == "2":
                                odds["B"] = val
                    if odds:
                        return odds
    except Exception:
        pass
    return None

# ─────────────────────────────────────────────
# DATAHENTING: FOTMOB LIGASTATISTIKK
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def hent_fotmob_tabell(liga_id):
    """Henter hjemme/borte-tabell fra Fotmob."""
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
                        lag_stats[navn]["hjemme_spilt"] = spilt
                        lag_stats[navn]["hjemme_scoret"] = scoret
                        lag_stats[navn]["hjemme_innsluppet"] = innsl
                    elif ttype == "away":
                        lag_stats[navn]["borte_spilt"] = spilt
                        lag_stats[navn]["borte_scoret"] = scoret
                        lag_stats[navn]["borte_innsluppet"] = innsl
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
    # Prøv første ord
    første_ord = l.split()[0] if l.split() else ""
    for k, v in lag_stats.items():
        if første_ord and første_ord in k.lower():
            return v
    return None

# ─────────────────────────────────────────────
# POISSON-MODELL
# ─────────────────────────────────────────────

def beregn_poisson_sannsynlighet(h_scoret_snitt, b_innsluppet_snitt,
                                   b_scoret_snitt, h_innsluppet_snitt,
                                   liga_snitt_hjem=1.5, liga_snitt_borte=1.1):
    """
    Beregner H/U/B-sannsynligheter med Poisson-fordeling.

    Forventet mål hjemme = (hjemmelagets scoresnitt hjemme * bortelagets innsluppet-snitt borte) / ligasnitt
    Forventet mål borte  = (bortelagets scoresnitt borte * hjemmelagets innsluppet-snitt hjemme) / ligasnitt
    """
    try:
        lambda_h = (h_scoret_snitt * b_innsluppet_snitt) / liga_snitt_hjem
        lambda_b = (b_scoret_snitt * h_innsluppet_snitt) / liga_snitt_borte

        lambda_h = max(0.2, min(lambda_h, 6.0))
        lambda_b = max(0.2, min(lambda_b, 6.0))

        max_maal = 8
        prob_h, prob_u, prob_b = 0.0, 0.0, 0.0

        for i in range(max_maal + 1):
            for j in range(max_maal + 1):
                p = poisson.pmf(i, lambda_h) * poisson.pmf(j, lambda_b)
                if i > j:
                    prob_h += p
                elif i == j:
                    prob_u += p
                else:
                    prob_b += p

        total = prob_h + prob_u + prob_b
        return {
            "H": round(prob_h / total * 100, 1),
            "U": round(prob_u / total * 100, 1),
            "B": round(prob_b / total * 100, 1),
            "lambda_h": round(lambda_h, 2),
            "lambda_b": round(lambda_b, 2),
        }
    except Exception:
        return None

def maal_snitt(scoret, spilt):
    try:
        s, p = int(scoret), int(spilt)
        return round(s / max(p, 1), 3)
    except:
        return None

# ─────────────────────────────────────────────
# HJELPEFUNKSJONER VISNING
# ─────────────────────────────────────────────

def verdi_visning(folk, modell, odds_impl=None):
    """Returnerer avvik og farger for ett utfall."""
    avvik_modell = round(modell - folk, 1) if modell is not None else None
    avvik_odds   = round(odds_impl - folk, 1) if odds_impl is not None else None
    return avvik_modell, avvik_odds

def farge(avvik):
    if avvik is None: return "gray"
    if avvik > 8: return "green"   # Modell/odds ser MER verdi enn folk
    if avvik < -8: return "red"    # Folk overtipper
    return "gray"

def pil(avvik):
    if avvik is None: return "–"
    if avvik > 8: return "🟢"
    if avvik < -8: return "🔴"
    return "⚪"

# ─────────────────────────────────────────────
# APP START
# ─────────────────────────────────────────────

st.title("⚽ TippingAnalyse")
st.caption("Folkerekke · Markedsodds · Poisson-modell · Verdianalyse")

# Last NT-data
with st.spinner("Henter tippekupong fra Norsk Tipping..."):
    nt_json, nt_feil = hent_nt_data()

if nt_feil or not nt_json:
    st.error(f"Kunne ikke hente Norsk Tipping-data: {nt_feil}")
    st.stop()

df = prosesser_nt(nt_json)
st.success(f"✅ Hentet {len(df)} kamper fra Norsk Tipping")

# Last Fotmob-statistikk
liga_stats_cache = {}
ligaer = df[df["FotmobLigaId"].notna()]["Liga"].unique()
if len(ligaer) > 0:
    with st.spinner("Henter lagstatistikk fra Fotmob..."):
        for liga in ligaer:
            lid = FOTMOB_LIGA_IDS.get(liga)
            if lid:
                stats = hent_fotmob_tabell(lid)
                if stats:
                    liga_stats_cache[liga] = stats
    if liga_stats_cache:
        st.success(f"✅ Hentet statistikk for {len(liga_stats_cache)} ligaer fra Fotmob")

# ─── Forklaring ───
with st.expander("ℹ️ Slik leser du analysen"):
    st.markdown("""
    ### Tre parametere sammenlignes mot **Folkerekka**:

    | Parameter | Kilde | Hva det er |
    |-----------|-------|------------|
    | **Folkerekka** | Norsk Tipping | Hva vanlige tippere tror (%) |
    | **Markedsodds** | NT Langoddsen | Hva bookmaker-oddsen impliserer (%) |
    | **Poisson-modell** | Fotmob-statistikk | Matematisk beregnet sannsynlighet fra mål-statistikk |

    ### Verdisignal:
    - 🟢 **Grønn** = Modellen/oddsen ser **mer** sannsynlighet enn folk → **potensiell verdi**
    - 🔴 **Rød** = Folk overtipper vs. modellen → **unngå**
    - ⚪ **Grå** = Lite avvik

    ### Poisson-modellen:
    Bruker hjemmelagets scorede mål hjemme og bortelagets innslupne mål borte til å beregne
    forventet målscoring, og regner deretter ut sannsynlighet for alle mulige sluttresultater matematisk.
    """)

# ─── Filter ───
st.sidebar.header("🔍 Filter")
dag_valg = st.sidebar.multiselect("Kupong", options=df["Dag"].unique(), default=df["Dag"].unique())
df_vis = df[df["Dag"].isin(dag_valg)].copy()
bare_verdi = st.sidebar.checkbox("Vis bare kamper med potensielt verdispill")
min_avvik = st.sidebar.slider("Minste modell-avvik å vise (pp)", 0, 20, 0)

# ─── Oppdater ───
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
    dag_df = df_vis[df_vis["Dag"] == dag]

    for _, rad in dag_df.iterrows():
        hjemmelag = rad["Hjemmelag"]
        bortelag  = rad["Bortelag"]
        liga      = rad["Liga"]

        # ── Hent lagstatistikk ──
        lag_stats = liga_stats_cache.get(liga, {})
        h_stats   = fuzzy_match(lag_stats, hjemmelag) if lag_stats else None
        b_stats   = fuzzy_match(lag_stats, bortelag)  if lag_stats else None

        # ── Beregn snitt ──
        h_sc_snitt = maal_snitt(h_stats.get("hjemme_scoret", 0), h_stats.get("hjemme_spilt", 1)) if h_stats else None
        h_in_snitt = maal_snitt(h_stats.get("hjemme_innsluppet", 0), h_stats.get("hjemme_spilt", 1)) if h_stats else None
        b_sc_snitt = maal_snitt(b_stats.get("borte_scoret", 0), b_stats.get("borte_spilt", 1)) if b_stats else None
        b_in_snitt = maal_snitt(b_stats.get("borte_innsluppet", 0), b_stats.get("borte_spilt", 1)) if b_stats else None

        # ── Poisson-modell ──
        poisson_res = None
        if all(x is not None for x in [h_sc_snitt, b_in_snitt, b_sc_snitt, h_in_snitt]):
            poisson_res = beregn_poisson_sannsynlighet(
                h_sc_snitt, b_in_snitt, b_sc_snitt, h_in_snitt
            )

        # ── NT Langoddsen ──
        nt_odds = hent_nt_odds(rad.get("BetRadarId"))
        odds_impl = None
        if nt_odds:
            vig_sum = sum(1/v for v in nt_odds.values() if v and v > 0)
            odds_impl = {
                k: round((1/v)/vig_sum*100, 1)
                for k, v in nt_odds.items() if v and v > 0
            }

        # ── Avvik beregning ──
        folk_h, folk_u, folk_b = rad["Folk H%"], rad["Folk U%"], rad["Folk B%"]
        poi_h = poisson_res["H"] if poisson_res else None
        poi_u = poisson_res["U"] if poisson_res else None
        poi_b = poisson_res["B"] if poisson_res else None
        oi_h = odds_impl.get("H") if odds_impl else None
        oi_u = odds_impl.get("U") if odds_impl else None
        oi_b = odds_impl.get("B") if odds_impl else None

        # Avvik: positivt = modell ser mer enn folk (verdi), negativt = folk overtipper
        avvik_poi = [
            (poi_h - folk_h) if poi_h else None,
            (poi_u - folk_u) if poi_u else None,
            (poi_b - folk_b) if poi_b else None,
        ]
        max_poi_avvik = max((abs(a) for a in avvik_poi if a is not None), default=0)

        har_verdi = max_poi_avvik >= min_avvik
        if bare_verdi and max_poi_avvik < 8:
            continue
        if max_poi_avvik < min_avvik:
            continue
        if max_poi_avvik >= 8:
            verdikamper += 1

        # ── Tittel ──
        beste = max(avvik_poi, key=lambda x: abs(x) if x else 0, default=None)
        tittel_ikon = pil(beste) if beste and abs(beste) > 8 else ""

        with st.expander(f"{tittel_ikon} {rad['Kamp']}  —  {liga}  ({rad['Dato']})"):

            # ════ HOVEDDEL: tre kolonner ════
            k1, k2, k3 = st.columns(3)

            # ── Kolonne 1: Folkerekke ──
            with k1:
                st.markdown("#### 👥 Folkerekka")
                for label, val in [("Hjemme (H)", folk_h), ("Uavgjort (U)", folk_u), ("Borte (B)", folk_b)]:
                    st.markdown(f"**{label}:** {val}%")
                    st.progress(int(val))

            # ── Kolonne 2: Markedsodds (NT Langoddsen) ──
            with k2:
                st.markdown("#### 📈 Markedsodds (NT Langoddsen)")
                if nt_odds and odds_impl:
                    for label, key, folk_val in [("Hjemme (H)", "H", folk_h), ("Uavgjort (U)", "U", folk_u), ("Borte (B)", "B", folk_b)]:
                        raw_odds = nt_odds.get(key, "–")
                        impl_pct = odds_impl.get(key)
                        avvik = round(impl_pct - folk_val, 1) if impl_pct else None
                        av_pil = pil(avvik)
                        av_farge = farge(avvik)
                        prefix = "+" if (avvik or 0) > 0 else ""
                        st.markdown(
                            f"**{label}:** odds **{raw_odds}** → {impl_pct}% "
                            f"<span style='color:{av_farge}'>{av_pil} {prefix}{avvik}pp</span>",
                            unsafe_allow_html=True
                        )
                else:
                    st.info("NT Langoddsen-odds ikke tilgjengelig for denne kampen")
                    st.markdown("_Odds hentes fra NT sitt interne API. Ikke alle kamper er tilgjengelige._")

            # ── Kolonne 3: Poisson-modell ──
            with k3:
                st.markdown("#### 🔢 Poisson-modell")
                if poisson_res:
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
                            unsafe_allow_html=True
                        )
                    st.caption(f"Forventet mål: {poisson_res['lambda_h']} – {poisson_res['lambda_b']}")
                else:
                    st.info("Ikke nok statistikk for Poisson-beregning")
                    if not h_stats:
                        st.caption(f"Fant ikke {hjemmelag} i Fotmob-tabellen")
                    if not b_stats:
                        st.caption(f"Fant ikke {bortelag} i Fotmob-tabellen")

            # ════ LAGSTATISTIKK ════
            if h_stats or b_stats:
                st.divider()
                st.markdown("#### 📊 Lagstatistikk fra Fotmob (sesongen)")
                s1, s2 = st.columns(2)

                with s1:
                    st.markdown(f"**🏠 {hjemmelag} — hjemmekamper**")
                    if h_stats and h_sc_snitt is not None:
                        hj_sp = h_stats.get("hjemme_spilt", "–")
                        hj_sc = h_stats.get("hjemme_scoret", "–")
                        hj_in = h_stats.get("hjemme_innsluppet", "–")
                        c1a, c1b, c1c = st.columns(3)
                        c1a.metric("Kamper", hj_sp)
                        c1b.metric("⚽ Scoret", f"{hj_sc} ({h_sc_snitt}/k)")
                        c1c.metric("🥅 Innsluppet", f"{hj_in} ({h_in_snitt}/k)")
                    else:
                        st.caption("Statistikk ikke tilgjengelig")

                with s2:
                    st.markdown(f"**✈️ {bortelag} — bortekamper**")
                    if b_stats and b_sc_snitt is not None:
                        bo_sp = b_stats.get("borte_spilt", "–")
                        bo_sc = b_stats.get("borte_scoret", "–")
                        bo_in = b_stats.get("borte_innsluppet", "–")
                        c2a, c2b, c2c = st.columns(3)
                        c2a.metric("Kamper", bo_sp)
                        c2b.metric("⚽ Scoret", f"{bo_sc} ({b_sc_snitt}/k)")
                        c2c.metric("🥅 Innsluppet", f"{bo_in} ({b_in_snitt}/k)")
                    else:
                        st.caption("Statistikk ikke tilgjengelig")

            # ════ VERDIOPPSUMMERING ════
            beste_poi = max(
                [("Hjemme", avvik_poi[0]), ("Uavgjort", avvik_poi[1]), ("Borte", avvik_poi[2])],
                key=lambda x: abs(x[1]) if x[1] is not None else 0
            )
            if beste_poi[1] is not None and beste_poi[1] > 8:
                st.success(f"🟢 **Mulig verdi:** Poisson-modellen ser {beste_poi[1]}pp MER sannsynlighet for **{beste_poi[0]}** enn folkerekka")
            elif beste_poi[1] is not None and beste_poi[1] < -8:
                st.warning(f"🔴 **Obs:** Folk overtipper **{beste_poi[0]}** med {abs(beste_poi[1])}pp vs. modellen")

st.divider()

# ─── Bunntall ───
col1, col2, col3 = st.columns(3)
col1.metric("Kamper vist", len(df_vis))
col2.metric("🟢 Verdisignaler (>8pp)", verdikamper)
col3.metric("Ligaer med statistikk", len(liga_stats_cache))

st.caption(f"Data: NT API + Fotmob · Sist oppdatert: {datetime.now().strftime('%H:%M:%S')} · Poisson-modell basert på sesongens hjemme/borte-statistikk")
