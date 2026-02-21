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

UNDERSTAT_LIGAER = {
    "ENG Premier League": "EPL",
    "ENG Championship": "Championship",
    "SPA LaLiga": "La_liga",
    "ITA Serie A": "Serie_A",
    "GER Bundesliga": "Bundesliga",
    "FRA Ligue 1": "Ligue_1",
    "NED Eredivisie": "Eredivisie",
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

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@700;800&family=DM+Sans:wght@400;500;600&display=swap');

:root {
    --bg: #070c12;
    --surface: #0d1520;
    --surface2: #111c2a;
    --border: #192537;
    --border2: #243045;
    --text: #dde6f0;
    --muted: #4a6080;
    --green: #10b981;
    --green-bg: #011a12;
    --red: #f43f5e;
    --red-bg: #1f0610;
    --blue: #3b82f6;
    --yellow: #f59e0b;
    --purple: #a78bfa;
    --mono: 'DM Mono', monospace;
    --display: 'Syne', sans-serif;
    --body: 'DM Sans', sans-serif;
}

html, body, [class*="css"] { font-family: var(--body) !important; background: var(--bg) !important; color: var(--text) !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 2rem 2.5rem !important; max-width: 1400px !important; }

.app-title { font-family: var(--display); font-size: 30px; font-weight: 800; color: var(--text); letter-spacing: -0.5px; }
.app-sub { font-size: 11px; color: var(--muted); letter-spacing: 0.1em; text-transform: uppercase; margin: 4px 0 20px; }

.status-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px; }
.pill { display:inline-flex; align-items:center; gap:5px; padding:4px 11px; border-radius:20px; font-size:11px; font-weight:600; letter-spacing:0.03em; }
.pill-ok  { background:#011a12; color:#10b981; border:1px solid #065f46; }
.pill-warn{ background:#1c1200; color:#f59e0b; border:1px solid #78350f; }
.pill-err { background:#1f0610; color:#f43f5e; border:1px solid #881337; }
.pill-dot { width:5px; height:5px; border-radius:50%; background:currentColor; }

.dag-hdr { font-family:var(--display); font-size:12px; font-weight:800; color:var(--muted); letter-spacing:0.14em; text-transform:uppercase; margin:32px 0 10px; padding-bottom:10px; border-bottom:1px solid var(--border); }

.kamp { background:var(--surface); border:1px solid var(--border); border-left:3px solid var(--border); border-radius:10px; margin-bottom:10px; }
.kamp.verdi { border-color:#065f46; border-left-color:var(--green); background:linear-gradient(135deg,#011a1210,var(--surface)); }

.kamp-top { display:flex; justify-content:space-between; align-items:center; padding:13px 18px; border-bottom:1px solid var(--border); }
.k-navn { font-family:var(--display); font-size:15px; font-weight:800; color:var(--text); letter-spacing:-0.1px; }
.k-meta { font-size:11px; color:var(--muted); margin-top:2px; }
.badges { display:flex; gap:5px; }
.bdg { font-size:10px; font-weight:700; padding:2px 8px; border-radius:4px; letter-spacing:0.06em; text-transform:uppercase; }
.bdg-v { background:#011a12; color:var(--green); border:1px solid #065f46; }
.bdg-x { background:#1e1b4b; color:#a78bfa; border:1px solid #3730a3; }
.bdg-o { background:#1c1917; color:#a8a29e; border:1px solid #44403c; }

.sek-lbl { font-size:10px; font-weight:700; color:var(--muted); letter-spacing:0.1em; text-transform:uppercase; margin-bottom:10px; }

.folk-item { margin-bottom:8px; }
.folk-row { display:flex; justify-content:space-between; font-size:12px; margin-bottom:3px; }
.folk-lbl { color:var(--muted); }
.folk-pct { font-family:var(--mono); font-size:13px; font-weight:500; color:var(--text); }
.bar { height:4px; background:var(--border2); border-radius:2px; }
.bar-h { height:4px; border-radius:2px; background:var(--blue); }
.bar-u { height:4px; border-radius:2px; background:var(--yellow); }
.bar-b { height:4px; border-radius:2px; background:var(--purple); }

.utfall { display:grid; grid-template-columns:72px 46px 1fr auto; align-items:center; gap:8px; padding:7px 0; border-bottom:1px solid var(--border); }
.utfall:last-child { border-bottom:none; }
.u-n { font-size:12px; color:var(--muted); }
.u-p { font-family:var(--mono); font-size:14px; font-weight:500; color:var(--text); }
.u-t { font-family:var(--mono); font-size:11px; color:var(--muted); background:var(--border); padding:2px 6px; border-radius:3px; justify-self:start; }
.u-a { font-family:var(--mono); font-size:13px; font-weight:500; text-align:right; }
.pos { color:var(--green); } .neg { color:var(--red); } .nøy { color:var(--muted); }

.stat-sek { padding:14px 18px; background:var(--bg); border-top:1px solid var(--border); }
.lag-lbl { font-size:11px; font-weight:700; color:var(--muted); letter-spacing:0.05em; text-transform:uppercase; margin-bottom:8px; }
.chips { display:flex; gap:7px; flex-wrap:wrap; }
.chip { background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:7px 12px; text-align:center; min-width:88px; }
.c-lbl { font-size:10px; color:var(--muted); margin-bottom:3px; }
.c-val { font-family:var(--mono); font-size:15px; font-weight:500; color:var(--text); }
.c-sub { font-size:10px; color:var(--muted); margin-top:2px; }
.c-grønn { color:var(--green) !important; }
.c-rød   { color:var(--red)   !important; }

.banner { margin:10px 18px 14px; padding:10px 14px; border-radius:6px; font-size:13px; font-weight:600; }
.ban-v { background:var(--green-bg); border:1px solid #065f46; color:var(--green); }
.ban-r { background:var(--red-bg); border:1px solid #881337; color:var(--red); }

.ingen { font-size:12px; color:var(--muted); font-style:italic; padding:10px 0; }

.footer { display:flex; gap:32px; padding:20px 0; border-top:1px solid var(--border); margin-top:24px; }
.f-stat { text-align:center; }
.f-val { font-family:var(--mono); font-size:22px; font-weight:500; color:var(--text); }
.f-lbl { font-size:11px; color:var(--muted); margin-top:3px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# DATAHENTING
# ─────────────────────────────────────────────

@st.cache_data(ttl=180)
def hent_nt():
    try:
        r = requests.get(NT_API, timeout=10)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)

def prosesser_nt(data):
    kamper = []
    for dag in data.get("gameDays", []):
        dag_navn = {"MIDWEEK": "Midtuke", "SATURDAY": "Lørdag", "SUNDAY": "Søndag"}.get(dag.get("dayType", ""), dag.get("dayType", ""))
        game = dag.get("game", {})
        matches = game.get("matches", [])
        folk_ft = game.get("tips", {}).get("fullTime", {}).get("peoples", [])
        for i, m in enumerate(matches):
            folk = folk_ft[i] if i < len(folk_ft) else {}
            liga = m.get("arrangement", {}).get("name", "")
            dato = m.get("date", "")[:10]
            kamper.append({
                "Dag": dag_navn, "Kamp": m.get("name", ""),
                "Hjemmelag": m.get("teams", {}).get("home", {}).get("webName", ""),
                "Bortelag": m.get("teams", {}).get("away", {}).get("webName", ""),
                "Liga": liga, "Dato": dato,
                "Folk H%": folk.get("home", 0),
                "Folk U%": folk.get("draw", 0),
                "Folk B%": folk.get("away", 0),
            })
    return pd.DataFrame(kamper)

@st.cache_data(ttl=3600)
def hent_fd(kode):
    if not FOOTBALL_DATA_KEY:
        return {}, "Ingen FOOTBALL_DATA_KEY i Secrets"
    try:
        r = requests.get(
            f"https://api.football-data.org/v4/competitions/{kode}/standings",
            headers={"X-Auth-Token": FOOTBALL_DATA_KEY}, timeout=15
        )
        if r.status_code == 403: return {}, "403 – Sjekk at FOOTBALL_DATA_KEY er korrekt i Secrets"
        if r.status_code == 404: return {}, f"404 – Liga '{kode}' ikke funnet"
        r.raise_for_status()
        data = r.json()
        lag = {}
        for tabell in data.get("standings", []):
            ttype = tabell.get("type", "")
            if ttype not in ["HOME", "AWAY", "TOTAL"]: continue
            for row in tabell.get("table", []):
                navn = row.get("team", {}).get("name", "")
                if not navn: continue
                if navn not in lag: lag[navn] = {}
                sp = row.get("playedGames", 0)
                gf = row.get("goalsFor", 0)
                ga = row.get("goalsAgainst", 0)
                if ttype == "HOME":
                    lag[navn].update({"hs": sp, "hgf": gf, "hga": ga})
                elif ttype == "AWAY":
                    lag[navn].update({"as": sp, "agf": gf, "aga": ga})
        return lag, None
    except Exception as e:
        return {}, str(e)

def beregn_styrke(lag):
    if not lag: return {}
    vals = list(lag.values())
    hsnitt = np.mean([v["hgf"]/max(v["hs"],1) for v in vals if v.get("hs",0)>0]) or 1.5
    bsnitt = np.mean([v["agf"]/max(v["as"],1) for v in vals if v.get("as",0)>0]) or 1.1
    res = {}
    for n, v in lag.items():
        hs = max(v.get("hs",0),1); as_ = max(v.get("as",0),1)
        hsc = v.get("hgf",0)/hs; hin = v.get("hga",0)/hs
        bsc = v.get("agf",0)/as_; bin_ = v.get("aga",0)/as_
        res[n] = {
            "ah": round(hsc/max(hsnitt,.1),3), "fh": round(hsnitt/max(hin,.1),3),
            "ab": round(bsc/max(bsnitt,.1),3), "fb": round(bsnitt/max(bin_,.1),3),
            "hsc":round(hsc,2), "hin":round(hin,2), "bsc":round(bsc,2), "bin":round(bin_,2),
            "hs":int(hs), "bs":int(as_), "lh":round(hsnitt,2), "lb":round(bsnitt,2),
        }
    return res

@st.cache_data(ttl=3600)
def hent_xg(liga_navn):
    try:
        import re, json
        r = requests.get(f"https://understat.com/league/{liga_navn}",
            headers={"User-Agent":"Mozilla/5.0","Referer":"https://understat.com/"}, timeout=15)
        r.raise_for_status()
        m = re.search(r"teamsData\s*=\s*JSON\.parse\('(.+?)'\)", r.text)
        if not m: return {}
        teams = json.loads(m.group(1).encode('utf-8').decode('unicode_escape'))
        xg = {}
        for _, t in teams.items():
            navn = t.get("title","")
            if not navn: continue
            hxg=hxga=hn=bxg=bxga=bn=0
            for k in t.get("history",[]):
                ha=k.get("h_a",""); g=float(k.get("xG",0) or 0); ga=float(k.get("xGA",0) or 0)
                if ha=="h": hxg+=g; hxga+=ga; hn+=1
                elif ha=="a": bxg+=g; bxga+=ga; bn+=1
            xg[navn] = {"hxg":round(hxg/max(hn,1),3),"bxg":round(bxg/max(bn,1),3)}
        return xg
    except: return {}

@st.cache_data(ttl=300)
def hent_odds_liga(sport_key):
    if not ODDS_API_KEY: return []
    try:
        r = requests.get(f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/",
            params={"apiKey":ODDS_API_KEY,"regions":"eu","markets":"h2h","oddsFormat":"decimal"}, timeout=10)
        r.raise_for_status(); return r.json()
    except: return []

def match_odds(liste, h, b):
    hl,bl = h.lower(),b.lower()
    for e in liste:
        eh=e.get("home_team","").lower(); eb=e.get("away_team","").lower()
        if (hl in eh or eh in hl or hl.split()[0] in eh) and (bl in eb or eb in bl or bl.split()[0] in eb):
            for bm in e.get("bookmakers",[]):
                for mkt in bm.get("markets",[]):
                    if mkt.get("key")=="h2h":
                        odds={}
                        for o in mkt.get("outcomes",[]):
                            n=o.get("name","").lower(); p=o.get("price",0)
                            if eh in n or "home" in n: odds["H"]=p
                            elif "draw" in n: odds["U"]=p
                            elif eb in n or "away" in n: odds["B"]=p
                        if len(odds)==3: return odds
    return None

def impl(d):
    if not d: return None
    try:
        vig=sum(1/v for v in d.values() if v>0)
        return {k:round((1/v)/vig*100,1) for k,v in d.items() if v>0}
    except: return None

def fuzzy(d, navn):
    if not d or not navn: return None
    if navn in d: return d[navn]
    l=navn.lower()
    for k,v in d.items():
        if l in k.lower() or k.lower() in l: return v
    f=l.split()[0] if l.split() else ""
    for k,v in d.items():
        if f and len(f)>3 and f in k.lower(): return v
    return None

def poisson_calc(hs, bs, hxg=None, bxg=None):
    try:
        lh_dc = hs["ah"] * bs["fb"] * hs["lh"]
        lb_dc = bs["ab"] * hs["fh"] * hs["lb"]
        brukte_xg = False
        if hxg and bxg and hxg.get("hxg",0)>0 and bxg.get("bxg",0)>0:
            lh = 0.5*lh_dc + 0.5*hxg["hxg"]
            lb = 0.5*lb_dc + 0.5*bxg["bxg"]
            brukte_xg = True
        else:
            lh,lb = lh_dc,lb_dc
        lh=max(.3,min(lh,6.)); lb=max(.3,min(lb,6.))
        ph=pu=pb=0.
        for i in range(9):
            for j in range(9):
                p=poisson.pmf(i,lh)*poisson.pmf(j,lb)
                if i>j: ph+=p
                elif i==j: pu+=p
                else: pb+=p
        tot=ph+pu+pb
        return {"H":round(ph/tot*100,1),"U":round(pu/tot*100,1),"B":round(pb/tot*100,1),
                "lh":round(lh,2),"lb":round(lb,2),"xg":brukte_xg}
    except: return None

def avvik_html(val, folk, tag=""):
    if val is None: return f"<span class='u-t'>{tag}</span><span class='u-a nøy'>—</span>"
    av = round(val-folk,1); p="+" if av>0 else ""
    cls = "pos" if av>8 else ("neg" if av<-8 else "nøy")
    tag_html = f"<span class='u-t'>{tag}</span>" if tag else "<span></span>"
    return f"{tag_html}<span class='u-a {cls}'>{p}{av}pp</span>"

def styrke_cls(v, høy_er_bra=True):
    if v is None: return ""
    if høy_er_bra: return "c-grønn" if v>1.1 else ("c-rød" if v<0.9 else "")
    return "c-rød" if v>1.1 else ("c-grønn" if v<0.9 else "")

# ─────────────────────────────────────────────
# HENT DATA
# ─────────────────────────────────────────────

with st.spinner(""):
    nt_json, nt_feil = hent_nt()
if nt_feil or not nt_json:
    st.error(f"Norsk Tipping feil: {nt_feil}"); st.stop()

df = prosesser_nt(nt_json)
ligaer = df["Liga"].unique().tolist()

fd_cache, styrke_cache, fd_feil = {}, {}, {}
for liga, kode in FD_LIGA_IDS.items():
    if liga in ligaer:
        stats, feil = hent_fd(kode)
        if stats:
            fd_cache[liga] = stats
            styrke_cache[liga] = beregn_styrke(stats)
        if feil:
            fd_feil[liga] = feil

xg_cache = {}
for liga, u_navn in UNDERSTAT_LIGAER.items():
    if liga in ligaer:
        xg = hent_xg(u_navn)
        if xg: xg_cache[liga] = xg

odds_cache = {}
for liga, sport_key in ODDS_SPORT_KEYS.items():
    if liga in ligaer:
        data = hent_odds_liga(sport_key)
        if data: odds_cache[liga] = data

# ─────────────────────────────────────────────
# APP HEADER
# ─────────────────────────────────────────────

st.markdown("<div class='app-title'>⚽ TippingAnalyse</div>", unsafe_allow_html=True)
st.markdown("<div class='app-sub'>Folkerekke · Markedsodds · Dixon-Coles Poisson-modell med xG</div>", unsafe_allow_html=True)

# Status-piller
def pill(ok, tekst):
    cls = "pill-ok" if ok else "pill-err"
    return f"<span class='pill {cls}'><span class='pill-dot'></span>{tekst}</span>"

def pill_warn(ok, tekst):
    cls = "pill-ok" if ok else "pill-warn"
    return f"<span class='pill {cls}'><span class='pill-dot'></span>{tekst}</span>"

pills = "".join([
    pill(True, f"NT — {len(df)} kamper"),
    pill(bool(fd_cache), f"football-data.org — {len(fd_cache)} ligaer"),
    pill_warn(bool(xg_cache), f"Understat xG — {len(xg_cache)} ligaer"),
    pill_warn(bool(odds_cache), f"The Odds API — {len(odds_cache)} ligaer"),
])
st.markdown(f"<div class='status-bar'>{pills}</div>", unsafe_allow_html=True)

# Vis eventuelle feil fra football-data.org
if fd_feil and not fd_cache:
    feil_tekst = list(fd_feil.values())[0]
    st.error(f"⚠️ football-data.org: {feil_tekst}")

# ─── Sidebar ───
st.sidebar.markdown("### 🔍 Filter")
dag_valg = st.sidebar.multiselect("Kupong", options=df["Dag"].unique(), default=df["Dag"].unique())
bare_verdi = st.sidebar.checkbox("Kun verdisignaler (>8pp)")
min_avvik = st.sidebar.slider("Minste avvik å vise (pp)", 0, 20, 0)
st.sidebar.markdown("---")
show_debug = st.sidebar.checkbox("🛠 Vis debug-info")
if show_debug:
    st.sidebar.markdown("**football-data.org:**")
    for liga, stats in fd_cache.items():
        lag_eks = list(stats.keys())[:2]
        st.sidebar.success(f"✅ {liga}: {len(stats)} lag\n_{', '.join(lag_eks)}_")
    for liga, feil in fd_feil.items():
        st.sidebar.error(f"❌ {liga}: {feil}")
if st.sidebar.button("🔄 Oppdater data"):
    st.cache_data.clear(); st.rerun()

df_vis = df[df["Dag"].isin(dag_valg)].copy()

# ─────────────────────────────────────────────
# KAMPVISNING
# ─────────────────────────────────────────────

verdikamper = 0

for dag in df_vis["Dag"].unique():
    st.markdown(f"<div class='dag-hdr'>{dag}kupong</div>", unsafe_allow_html=True)

    for _, rad in df_vis[df_vis["Dag"] == dag].iterrows():
        hjem = rad["Hjemmelag"]; borte = rad["Bortelag"]
        liga = rad["Liga"]; fh = rad["Folk H%"]; fu = rad["Folk U%"]; fb = rad["Folk B%"]

        hs = fuzzy(styrke_cache.get(liga,{}), hjem)
        bs = fuzzy(styrke_cache.get(liga,{}), borte)
        hxg = fuzzy(xg_cache.get(liga,{}), hjem)
        bxg = fuzzy(xg_cache.get(liga,{}), borte)
        poi = poisson_calc(hs, bs, hxg, bxg) if hs and bs else None
        rå  = match_odds(odds_cache.get(liga,[]), hjem, borte)
        im  = impl(rå)

        alle_avvik = []
        for (pv,fv) in ([(poi["H"],fh),(poi["U"],fu),(poi["B"],fb)] if poi else []):
            alle_avvik.append(abs(pv-fv))
        for (iv,fv) in ([(im["H"],fh),(im["U"],fu),(im["B"],fb)] if im else []):
            alle_avvik.append(abs(iv-fv))
        max_av = max(alle_avvik, default=0)

        if bare_verdi and max_av < 8: continue
        if max_av < min_avvik: continue
        if max_av >= 8: verdikamper += 1

        verdi = max_av >= 8
        badges = ""
        if verdi: badges += "<span class='bdg bdg-v'>✦ Verdi</span>"
        if poi and poi.get("xg"): badges += "<span class='bdg bdg-x'>xG</span>"
        if im: badges += "<span class='bdg bdg-o'>Odds</span>"

        st.markdown(f"<div class='kamp {'verdi' if verdi else ''}'>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class='kamp-top'>
            <div><div class='k-navn'>{rad['Kamp']}</div><div class='k-meta'>{liga} · {rad['Dato']}</div></div>
            <div class='badges'>{badges}</div>
        </div>""", unsafe_allow_html=True)

        k1, k2, k3 = st.columns(3)

        with k1:
            st.markdown(f"""
            <div style='padding:15px 4px'>
            <div class='sek-lbl'>👥 Folkerekka</div>
            <div class='folk-item'>
                <div class='folk-row'><span class='folk-lbl'>Hjemme</span><span class='folk-pct'>{fh}%</span></div>
                <div class='bar'><div class='bar-h' style='width:{fh}%'></div></div>
            </div>
            <div class='folk-item'>
                <div class='folk-row'><span class='folk-lbl'>Uavgjort</span><span class='folk-pct'>{fu}%</span></div>
                <div class='bar'><div class='bar-u' style='width:{fu}%'></div></div>
            </div>
            <div class='folk-item'>
                <div class='folk-row'><span class='folk-lbl'>Borte</span><span class='folk-pct'>{fb}%</span></div>
                <div class='bar'><div class='bar-b' style='width:{fb}%'></div></div>
            </div>
            </div>""", unsafe_allow_html=True)

        with k2:
            st.markdown("<div style='padding:15px 4px'>", unsafe_allow_html=True)
            st.markdown("<div class='sek-lbl'>📈 Markedsodds</div>", unsafe_allow_html=True)
            if im and rå:
                for lbl,key,fv in [("Hjemme","H",fh),("Uavgjort","U",fu),("Borte","B",fb)]:
                    av=round(im[key]-fv,1); p="+" if av>0 else ""
                    cls="pos" if av>8 else ("neg" if av<-8 else "nøy")
                    st.markdown(f"""<div class='utfall'>
                        <span class='u-n'>{lbl}</span>
                        <span class='u-p'>{im[key]}%</span>
                        <span class='u-t'>{rå[key]}</span>
                        <span class='u-a {cls}'>{p}{av}pp</span>
                    </div>""", unsafe_allow_html=True)
            else:
                st.markdown("<div class='ingen'>Odds ikke tilgjengelig</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with k3:
            xg_suf = " (inkl. xG)" if poi and poi.get("xg") else ""
            st.markdown("<div style='padding:15px 4px'>", unsafe_allow_html=True)
            st.markdown(f"<div class='sek-lbl'>🔢 Poisson-modell{xg_suf}</div>", unsafe_allow_html=True)
            if poi:
                for lbl,key,fv in [("Hjemme","H",fh),("Uavgjort","U",fu),("Borte","B",fb)]:
                    av=round(poi[key]-fv,1); p="+" if av>0 else ""
                    cls="pos" if av>8 else ("neg" if av<-8 else "nøy")
                    lambda_vis = poi['lh'] if key=='H' else (poi['lb'] if key=='B' else "")
                    tag = f"λ={lambda_vis}" if key!='U' else ""
                    st.markdown(f"""<div class='utfall'>
                        <span class='u-n'>{lbl}</span>
                        <span class='u-p'>{poi[key]}%</span>
                        <span class='u-t'>{tag}</span>
                        <span class='u-a {cls}'>{p}{av}pp</span>
                    </div>""", unsafe_allow_html=True)
            else:
                if not FOOTBALL_DATA_KEY:
                    msg = "FOOTBALL_DATA_KEY mangler i Secrets"
                elif not hs and not bs:
                    msg = f"Ingen data for {hjem} eller {borte}"
                elif not hs:
                    msg = f"Ingen data for {hjem}"
                elif not bs:
                    msg = f"Ingen data for {borte}"
                else:
                    msg = "Beregning feilet"
                st.markdown(f"<div class='ingen'>{msg}</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # Lagstatistikk
        if hs or bs:
            st.markdown("<div class='stat-sek'>", unsafe_allow_html=True)
            ss1, ss2 = st.columns(2)
            with ss1:
                if hs:
                    xg_str = f" · xG {hxg.get('hxg','–')}" if hxg else ""
                    st.markdown(f"<div class='lag-lbl'>🏠 {hjem} hjemme ({hs.get('hs','–')} kamper{xg_str})</div>", unsafe_allow_html=True)
                    sc_cls=styrke_cls(hs.get("ah")); fc_cls=styrke_cls(hs.get("fh"))
                    st.markdown(f"""<div class='chips'>
                        <div class='chip'><div class='c-lbl'>Scoret/kamp</div><div class='c-val {sc_cls}'>{hs.get('hsc','–')}</div></div>
                        <div class='chip'><div class='c-lbl'>Innsluppet/kamp</div><div class='c-val'>{hs.get('hin','–')}</div></div>
                        <div class='chip'><div class='c-lbl'>Angrepsstyrke</div><div class='c-val {sc_cls}'>{hs.get('ah','–')}</div><div class='c-sub'>1.0 = ligasnitt</div></div>
                        <div class='chip'><div class='c-lbl'>Forsvarsstyrke</div><div class='c-val {fc_cls}'>{hs.get('fh','–')}</div><div class='c-sub'>1.0 = ligasnitt</div></div>
                    </div>""", unsafe_allow_html=True)
            with ss2:
                if bs:
                    xg_str2 = f" · xG {bxg.get('bxg','–')}" if bxg else ""
                    st.markdown(f"<div class='lag-lbl'>✈️ {borte} borte ({bs.get('bs','–')} kamper{xg_str2})</div>", unsafe_allow_html=True)
                    sc_cls2=styrke_cls(bs.get("ab")); fc_cls2=styrke_cls(bs.get("fb"))
                    st.markdown(f"""<div class='chips'>
                        <div class='chip'><div class='c-lbl'>Scoret/kamp</div><div class='c-val {sc_cls2}'>{bs.get('bsc','–')}</div></div>
                        <div class='chip'><div class='c-lbl'>Innsluppet/kamp</div><div class='c-val'>{bs.get('bin','–')}</div></div>
                        <div class='chip'><div class='c-lbl'>Angrepsstyrke</div><div class='c-val {sc_cls2}'>{bs.get('ab','–')}</div><div class='c-sub'>1.0 = ligasnitt</div></div>
                        <div class='chip'><div class='c-lbl'>Forsvarsstyrke</div><div class='c-val {fc_cls2}'>{bs.get('fb','–')}</div><div class='c-sub'>1.0 = ligasnitt</div></div>
                    </div>""", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # Verdibanner
        if poi:
            poi_av = [("Hjemme",poi["H"]-fh),("Uavgjort",poi["U"]-fu),("Borte",poi["B"]-fb)]
            beste = max(poi_av, key=lambda x: abs(x[1]))
            if beste[1] > 8:
                st.markdown(f"<div class='banner ban-v'>🟢 Verdisignal: Poisson ser +{round(beste[1],1)}pp for <b>{beste[0]}</b> vs. folkerekka</div>", unsafe_allow_html=True)
            elif beste[1] < -8:
                st.markdown(f"<div class='banner ban-r'>🔴 Folk overtipper <b>{beste[0]}</b> med {round(abs(beste[1]),1)}pp vs. modellen</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

# Bunntall
st.markdown(f"""
<div class='footer'>
    <div class='f-stat'><div class='f-val'>{len(df_vis)}</div><div class='f-lbl'>Kamper</div></div>
    <div class='f-stat'><div class='f-val'>{verdikamper}</div><div class='f-lbl'>Verdisignaler</div></div>
    <div class='f-stat'><div class='f-val'>{len(fd_cache)}</div><div class='f-lbl'>Ligaer m/ statistikk</div></div>
    <div class='f-stat'><div class='f-val'>{len(xg_cache)}</div><div class='f-lbl'>Ligaer m/ xG</div></div>
    <div class='f-stat'><div class='f-val' style='font-size:16px'>{datetime.now().strftime('%H:%M')}</div><div class='f-lbl'>Oppdatert</div></div>
</div>
""", unsafe_allow_html=True)
