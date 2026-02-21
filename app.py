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
# CSS – BLOOMBERG/POLYMARKET DESIGN
# ─────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@700;800&family=DM+Sans:wght@400;500;600&display=swap');

:root {
    --bg: #060d16;
    --s1: #0b1624;
    --s2: #0d1a28;
    --s3: #111f30;
    --border: #192537;
    --border2: #1e2f42;
    --text: #e2e8f0;
    --muted: #4a6080;
    --muted2: #2a3d55;
    --green: #10b981;
    --green-bg: #011a12;
    --green-border: #065f46;
    --red: #f43f5e;
    --red-bg: #1f0610;
    --red-border: #881337;
    --blue: #3b82f6;
    --yellow: #f59e0b;
    --purple: #a855f7;
    --mono: 'DM Mono', monospace;
    --display: 'Syne', sans-serif;
    --body: 'DM Sans', sans-serif;
}

html, body, [class*="css"] { font-family: var(--body) !important; background: var(--bg) !important; color: var(--text) !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1.5rem 2rem !important; max-width: 1300px !important; }

/* ── Topbar ── */
.topbar { display:flex; justify-content:space-between; align-items:center; padding:14px 0 20px; border-bottom:1px solid var(--border); margin-bottom:20px; }
.app-logo { font-family:var(--display); font-size:22px; font-weight:800; color:var(--text); letter-spacing:-0.3px; display:flex; align-items:center; gap:10px; }
.app-time { font-family:var(--mono); font-size:12px; color:var(--muted); }

/* ── Status piller ── */
.pills { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:20px; }
.pill { display:inline-flex; align-items:center; gap:5px; padding:4px 12px; border-radius:20px; font-size:11px; font-weight:600; letter-spacing:0.03em; }
.p-ok   { background:var(--green-bg); color:var(--green); border:1px solid var(--green-border); }
.p-warn { background:#1c1200; color:var(--yellow); border:1px solid #78350f; }
.p-err  { background:var(--red-bg); color:var(--red); border:1px solid var(--red-border); }
.pill-dot { width:5px; height:5px; border-radius:50%; background:currentColor; flex-shrink:0; }

/* ── Metrikk-rad ── */
.mrad { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:24px; }
.mbox { background:var(--s2); border:1px solid var(--border); border-radius:8px; padding:14px 16px; }
.mval { font-family:var(--mono); font-size:28px; font-weight:500; color:var(--text); line-height:1; }
.mval.green { color:var(--green); }
.mlbl { font-size:11px; color:var(--muted); margin-top:5px; }

/* ── Dag-header ── */
.dag { font-family:var(--display); font-size:11px; font-weight:800; color:var(--muted); letter-spacing:0.14em; text-transform:uppercase; margin:28px 0 10px; padding-bottom:8px; border-bottom:1px solid var(--border); }

/* ── Kamp-kort ── */
.kort { background:var(--s1); border:1px solid var(--border); border-left:3px solid var(--border); border-radius:10px; margin-bottom:10px; overflow:hidden; }
.kort.verdi { border-color:var(--green-border); border-left-color:var(--green); }

/* ── Kamp-topp ── */
.ktop { display:flex; justify-content:space-between; align-items:center; padding:12px 18px; background:var(--s2); border-bottom:1px solid var(--border); }
.knavn { font-family:var(--display); font-size:15px; font-weight:800; color:var(--text); letter-spacing:-0.1px; }
.kmeta { font-size:11px; color:var(--muted); margin-top:2px; }
.badges { display:flex; gap:6px; align-items:center; }
.bdg { font-size:10px; font-weight:700; padding:2px 8px; border-radius:4px; letter-spacing:0.06em; text-transform:uppercase; }
.bdg-v { background:var(--green-bg); color:var(--green); border:1px solid var(--green-border); }
.bdg-x { background:#1e1b4b; color:#a78bfa; border:1px solid #3730a3; }
.bdg-o { background:#1c1917; color:#a8a29e; border:1px solid #44403c; }

/* ── Verdibanner ── */
.vbanner { padding:8px 18px; font-size:12px; font-weight:600; border-bottom:1px solid var(--border); }
.vbanner.pos { background:var(--green-bg); color:var(--green); }
.vbanner.neg { background:var(--red-bg); color:var(--red); }

/* ── Dataseksjon ── */
.dsek { padding:14px 18px 16px; }
.sek-lbl { font-size:10px; font-weight:700; color:var(--muted); letter-spacing:0.1em; text-transform:uppercase; margin-bottom:11px; }

/* ── Folkestolper ── */
.folkrad { margin-bottom:9px; }
.folktop { display:flex; justify-content:space-between; font-size:12px; margin-bottom:3px; }
.folk-n { color:var(--muted); }
.folk-p { font-family:var(--mono); font-weight:500; color:var(--text); }
.bar { height:4px; background:var(--border2); border-radius:2px; }
.bar-h { height:4px; border-radius:2px; background:var(--blue); }
.bar-u { height:4px; border-radius:2px; background:var(--yellow); }
.bar-b { height:4px; border-radius:2px; background:var(--purple); }

/* ── Utfall-rader ── */
.urad { display:grid; grid-template-columns:70px 48px 60px 1fr; align-items:center; gap:8px; padding:7px 0; border-bottom:1px solid #0f1e30; }
.urad:last-child { border-bottom:none; }
.u-n { font-size:12px; color:var(--muted); }
.u-p { font-family:var(--mono); font-size:14px; font-weight:500; color:var(--text); }
.u-tag { font-family:var(--mono); font-size:11px; color:var(--muted); background:var(--border); padding:2px 6px; border-radius:3px; }
.u-av { font-family:var(--mono); font-size:13px; font-weight:600; text-align:right; }
.av-pos { color:var(--green); }
.av-neg { color:var(--red); }
.av-nøy { color:var(--muted); }
.ingen { font-size:12px; color:var(--muted); font-style:italic; padding:8px 0; }

/* ── Separator ── */
.sep { height:1px; background:var(--border); margin:0; }

/* ── Lagstatistikk ── */
.stagsek { padding:14px 18px 16px; background:var(--bg); border-top:1px solid var(--border); }
.lag-lbl { font-size:11px; font-weight:700; color:var(--muted); letter-spacing:0.05em; text-transform:uppercase; margin-bottom:8px; }
.chips { display:flex; gap:8px; flex-wrap:wrap; }
.chip { background:var(--s1); border:1px solid var(--border); border-radius:6px; padding:7px 12px; text-align:center; min-width:90px; }
.c-lbl { font-size:10px; color:var(--muted); margin-bottom:3px; }
.c-val { font-family:var(--mono); font-size:16px; font-weight:500; color:var(--text); }
.c-sub { font-size:9px; color:var(--muted2); margin-top:2px; }
.c-g { color:var(--green) !important; }
.c-r { color:var(--red) !important; }

/* ── Poisson-forklaring ── */
.poi-sek { padding:14px 18px 16px; background:#060f1a; border-top:1px solid var(--border); }
.poi-steg { display:flex; gap:12px; padding:9px 0; border-bottom:1px solid #0d1e30; }
.poi-steg:last-child { border-bottom:none; }
.steg-num { width:22px; height:22px; border-radius:50%; background:#1e3a5f; color:#60a5fa; font-size:11px; font-weight:700; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.steg-innhold { flex:1; }
.steg-top { display:flex; justify-content:space-between; align-items:center; margin-bottom:2px; }
.steg-lbl { font-size:12px; color:#94a3b8; }
.steg-val { font-family:var(--mono); font-size:13px; font-weight:700; color:var(--text); }
.steg-bsk { font-size:11px; color:var(--muted); line-height:1.4; }
.poi-konklusjon { margin-top:12px; padding:12px 14px; background:#0d1f3a; border:1px solid #1e3a5f; border-radius:6px; }
.poi-k-tittel { font-size:11px; font-weight:700; color:#60a5fa; margin-bottom:5px; }
.poi-k-tekst { font-size:12px; color:#94a3b8; line-height:1.6; }
.poi-resultat { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; }
.poi-res-boks { background:#0f1e35; border-radius:6px; padding:8px 14px; text-align:center; flex:1; min-width:80px; }
.pr-lbl { font-size:10px; color:var(--muted); margin-bottom:3px; }
.pr-val { font-family:var(--mono); font-size:18px; font-weight:700; color:var(--text); }
.pr-av  { font-family:var(--mono); font-size:12px; font-weight:600; margin-top:2px; }

/* ── Footer ── */
.footer { display:flex; gap:28px; padding:18px 0; border-top:1px solid var(--border); margin-top:24px; }
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
            kl = m.get("date", "")[11:16] if len(m.get("date","")) > 10 else ""
            kamper.append({
                "Dag": dag_navn, "Kamp": m.get("name", ""),
                "Hjemmelag": m.get("teams", {}).get("home", {}).get("webName", ""),
                "Bortelag": m.get("teams", {}).get("away", {}).get("webName", ""),
                "Liga": liga, "Dato": dato, "Kl": kl,
                "Folk H%": folk.get("home", 0),
                "Folk U%": folk.get("draw", 0),
                "Folk B%": folk.get("away", 0),
            })
    return pd.DataFrame(kamper)

@st.cache_data(ttl=3600)
def hent_fd(kode):
    if not FOOTBALL_DATA_KEY:
        return {}, "Ingen FOOTBALL_DATA_KEY"
    try:
        r = requests.get(
            f"https://api.football-data.org/v4/competitions/{kode}/standings",
            headers={"X-Auth-Token": FOOTBALL_DATA_KEY}, timeout=15
        )
        if r.status_code == 403: return {}, "403 – Sjekk FOOTBALL_DATA_KEY"
        if r.status_code == 404: return {}, f"404 – Liga '{kode}' ikke funnet"
        r.raise_for_status()
        lag = {}
        for tabell in r.json().get("standings", []):
            ttype = tabell.get("type", "")
            if ttype not in ["HOME", "AWAY"]: continue
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
            "hsc":round(hsc,2), "hin":round(hin,2),
            "bsc":round(bsc,2), "bin":round(bin_,2),
            "hs":int(hs), "bs":int(as_),
            "lh":round(hsnitt,2), "lb":round(bsnitt,2),
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
            hxg=hn=bxg=bn=0
            for k in t.get("history",[]):
                ha=k.get("h_a",""); g=float(k.get("xG",0) or 0)
                if ha=="h": hxg+=g; hn+=1
                elif ha=="a": bxg+=g; bn+=1
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

def lag_forklaring(hjem, borte, hs, bs, poi, hxg, bxg):
    """Lag en norsk forklaring på Poisson-modellen for denne kampen."""
    if not hs or not bs or not poi:
        return [], ""

    steg = []

    # Angrepsstyrke hjem
    ah = hs.get("ah", 1.0)
    ah_tekst = f"{'Scorer' if ah > 1.05 else 'Scorer'} {abs(round((ah-1)*100))}% {'over' if ah>1.05 else 'under'} ligasnittet hjemme"
    steg.append({"label": f"{hjem} angrepsstyrke hjemme", "verdi": f"{ah}×", "bsk": ah_tekst})

    # Forsvarsstyrke borte
    fb = bs.get("fb", 1.0)
    fb_tekst = f"{'Holder igjen' if fb > 1.05 else 'Slipper inn'} {abs(round((fb-1)*100))}% {'under' if fb>1.05 else 'over'} ligasnittet borte"
    steg.append({"label": f"{borte} forsvarsstyrke borte", "verdi": f"{fb}×", "bsk": fb_tekst})

    # Angrepsstyrke borte
    ab = bs.get("ab", 1.0)
    ab_tekst = f"{'Scorer' if ab > 1.05 else 'Scorer'} {abs(round((ab-1)*100))}% {'over' if ab>1.05 else 'under'} ligasnittet borte"
    steg.append({"label": f"{borte} angrepsstyrke borte", "verdi": f"{ab}×", "bsk": ab_tekst})

    # Forsvarsstyrke hjem
    fh = hs.get("fh", 1.0)
    fh_tekst = f"{'Holder igjen' if fh > 1.05 else 'Slipper inn'} {abs(round((fh-1)*100))}% {'under' if fh>1.05 else 'over'} ligasnittet hjemme"
    steg.append({"label": f"{hjem} forsvarsstyrke hjemme", "verdi": f"{fh}×", "bsk": fh_tekst})

    # xG
    if poi.get("xg") and hxg and bxg:
        steg.append({"label": "xG-justering (Understat)", "verdi": f"{hxg.get('hxg','–')} / {bxg.get('bxg','–')}", "bsk": f"xG vektes 50/50 med statistikkmodellen. {hjem}: {hxg.get('hxg','–')} xG/kamp hjemme, {borte}: {bxg.get('bxg','–')} xG/kamp borte"})

    # Lambda
    steg.append({"label": "Forventet mål (λ)", "verdi": f"{poi['lh']} – {poi['lb']}", "bsk": f"λ hjemme={poi['lh']}: angrep × motstanders forsvar × ligasnitt{' + xG-vekting' if poi.get('xg') else ''}. λ borte={poi['lb']} beregnet tilsvarende"})

    # Konklusjon
    h_av = round(poi["H"] - 0, 1)  # placeholder
    beste_utfall = max([("Hjemme", poi["H"]), ("Uavgjort", poi["U"]), ("Borte", poi["B"])], key=lambda x: x[1])
    if poi["lh"] > poi["lb"] + 0.3:
        favoritt = f"{hjem} er klar favoritt"
    elif poi["lb"] > poi["lh"] + 0.3:
        favoritt = f"{borte} er favoritt på bortebane"
    else:
        favoritt = "Jevn kamp ifølge modellen"

    konklusjon = f"{favoritt} med λ={poi['lh']} mot λ={poi['lb']}. Poisson-fordelingen beregner sannsynlighet for alle mulige sluttresultater (0-0, 1-0, 0-1 osv.) og summer disse til H/U/B-prosenter."
    if poi.get("xg"):
        konklusjon += " xG-data fra Understat er inkludert og vektet 50/50 med den statistiske modellen."

    return steg, konklusjon

def avvik_css(av):
    if av > 8: return "av-pos", f"+{av}pp"
    if av < -8: return "av-neg", f"{av}pp"
    p = "+" if av > 0 else ""
    return "av-nøy", f"{p}{av}pp"

def styrke_cls(v):
    if v is None: return ""
    return "c-g" if v > 1.1 else ("c-r" if v < 0.9 else "")

# ─────────────────────────────────────────────
# HENT DATA
# ─────────────────────────────────────────────

with st.spinner(""):
    nt_json, nt_feil = hent_nt()
if nt_feil or not nt_json:
    st.error(f"Norsk Tipping feil: {nt_feil}"); st.stop()

df = prosesser_nt(nt_json)
ligaer = df["Liga"].unique().tolist()

fd_cache, styrke_cache, fd_feil_cache = {}, {}, {}
for liga, kode in FD_LIGA_IDS.items():
    if liga in ligaer:
        stats, feil = hent_fd(kode)
        if stats:
            fd_cache[liga] = stats
            styrke_cache[liga] = beregn_styrke(stats)
        if feil:
            fd_feil_cache[liga] = feil

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

st.markdown(f"""
<div class='topbar'>
    <div class='app-logo'>⚽ TippingAnalyse</div>
    <div class='app-time'>{datetime.now().strftime('%d.%m.%Y %H:%M')}</div>
</div>
""", unsafe_allow_html=True)

# Status-piller
def pill(ok, tekst, warn=False):
    cls = "p-ok" if ok else ("p-warn" if warn else "p-err")
    return f"<span class='pill {cls}'><span class='pill-dot'></span>{tekst}</span>"

pills_html = "".join([
    pill(True, f"NT API — {len(df)} kamper"),
    pill(bool(fd_cache), f"football-data.org — {len(fd_cache)} ligaer", warn=False),
    pill(bool(xg_cache), f"Understat xG — {len(xg_cache)} ligaer", warn=not xg_cache),
    pill(bool(odds_cache), f"The Odds API — {len(odds_cache)} ligaer", warn=not odds_cache),
])
st.markdown(f"<div class='pills'>{pills_html}</div>", unsafe_allow_html=True)

if fd_feil_cache and not fd_cache:
    st.error(f"⚠️ football-data.org: {list(fd_feil_cache.values())[0]}")

# Metrikk-rad
verdikamper_total = 0
for _, rad in df.iterrows():
    hs = fuzzy(styrke_cache.get(rad["Liga"],{}), rad["Hjemmelag"])
    bs = fuzzy(styrke_cache.get(rad["Liga"],{}), rad["Bortelag"])
    if hs and bs:
        poi = poisson_calc(hs, bs)
        if poi:
            avvik = [abs(poi["H"]-rad["Folk H%"]), abs(poi["U"]-rad["Folk U%"]), abs(poi["B"]-rad["Folk B%"])]
            if max(avvik) >= 8: verdikamper_total += 1

st.markdown(f"""
<div class='mrad'>
    <div class='mbox'><div class='mval'>{len(df)}</div><div class='mlbl'>Kamper totalt</div></div>
    <div class='mbox'><div class='mval green'>{verdikamper_total}</div><div class='mlbl'>✦ Verdisignaler</div></div>
    <div class='mbox'><div class='mval'>{len(fd_cache)}</div><div class='mlbl'>Ligaer m/ statistikk</div></div>
    <div class='mbox'><div class='mval'>{len(xg_cache)}</div><div class='mlbl'>Ligaer m/ xG</div></div>
</div>
""", unsafe_allow_html=True)

# ─── Sidebar ───
st.sidebar.markdown("### 🔍 Filter")
dag_valg = st.sidebar.multiselect("Kupong", options=df["Dag"].unique(), default=df["Dag"].unique())
bare_verdi = st.sidebar.checkbox("Kun verdisignaler (>8pp)")
min_avvik = st.sidebar.slider("Minste avvik (pp)", 0, 20, 0)
st.sidebar.markdown("---")
show_debug = st.sidebar.checkbox("🛠 Debug-info")
if show_debug:
    st.sidebar.markdown("**football-data.org:**")
    for liga, stats in fd_cache.items():
        eks = list(stats.keys())[:2]
        st.sidebar.success(f"✅ {liga}: {len(stats)} lag\n_{', '.join(eks)}_")
    for liga, feil in fd_feil_cache.items():
        st.sidebar.error(f"❌ {liga}: {feil}")
if st.sidebar.button("🔄 Oppdater data"):
    st.cache_data.clear(); st.rerun()

with st.sidebar.expander("ℹ️ Slik leser du analysen"):
    st.markdown("""
**Folkerekka** – hva tippere tror (%)  
**Markedsodds** – bookmakers implisitt % (margin fjernet)  
**Poisson-modell** – Dixon-Coles + xG  

🟢 **+pp** = modell ser MER enn folk → verdi  
🔴 **-pp** = folk overtipper → unngå  
**λ** = forventet antall mål  
**Angrepsstyrke** = lagets snitt / ligasnitt  
**Forsvarsstyrke** = ligasnitt / lagets innslupne  
""")

df_vis = df[df["Dag"].isin(dag_valg)].copy()

# ─────────────────────────────────────────────
# KAMPVISNING
# ─────────────────────────────────────────────

for dag in df_vis["Dag"].unique():
    st.markdown(f"<div class='dag'>{dag}kupong</div>", unsafe_allow_html=True)

    for _, rad in df_vis[df_vis["Dag"] == dag].iterrows():
        hjem = rad["Hjemmelag"]; borte = rad["Bortelag"]
        liga = rad["Liga"]
        fh = rad["Folk H%"]; fu = rad["Folk U%"]; fb = rad["Folk B%"]

        hs = fuzzy(styrke_cache.get(liga,{}), hjem)
        bs = fuzzy(styrke_cache.get(liga,{}), borte)
        hxg = fuzzy(xg_cache.get(liga,{}), hjem)
        bxg = fuzzy(xg_cache.get(liga,{}), borte)
        poi = poisson_calc(hs, bs, hxg, bxg) if hs and bs else None
        rå  = match_odds(odds_cache.get(liga,[]), hjem, borte)
        im  = impl(rå)

        alle_avvik = []
        if poi:
            alle_avvik += [abs(poi["H"]-fh), abs(poi["U"]-fu), abs(poi["B"]-fb)]
        if im:
            alle_avvik += [abs(im["H"]-fh), abs(im["U"]-fu), abs(im["B"]-fb)]
        max_av = max(alle_avvik, default=0)

        if bare_verdi and max_av < 8: continue
        if max_av < min_avvik: continue

        verdi = max_av >= 8

        # Beste verdisignal fra Poisson
        beste = None
        if poi:
            poi_avvik = [("Hjemme", poi["H"]-fh), ("Uavgjort", poi["U"]-fu), ("Borte", poi["B"]-fb)]
            beste = max(poi_avvik, key=lambda x: abs(x[1]))

        badges = ""
        if verdi: badges += "<span class='bdg bdg-v'>✦ Verdi</span>"
        if poi and poi.get("xg"): badges += "<span class='bdg bdg-x'>xG</span>"
        if im: badges += "<span class='bdg bdg-o'>Odds</span>"

        kl_str = f" · {rad['Kl']}" if rad.get("Kl") else ""

        st.markdown(f"<div class='kort {'verdi' if verdi else ''}'>", unsafe_allow_html=True)

        # Topp
        st.markdown(f"""
        <div class='ktop'>
            <div>
                <div class='knavn'>{rad['Kamp']}</div>
                <div class='kmeta'>{liga} · {rad['Dato']}{kl_str}</div>
            </div>
            <div class='badges'>{badges}</div>
        </div>""", unsafe_allow_html=True)

        # Verdibanner
        if beste and abs(beste[1]) > 8:
            av_r = round(beste[1], 1)
            if av_r > 0:
                st.markdown(f"<div class='vbanner pos'>🟢 Modellen ser +{av_r}pp mer sannsynlighet for <b>{beste[0]}</b> enn folkerekka</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='vbanner neg'>🔴 Folk overtipper <b>{beste[0]}</b> med {abs(av_r)}pp vs. modellen</div>", unsafe_allow_html=True)

        # Tre kolonner
        k1, k2, k3 = st.columns(3)

        with k1:
            st.markdown(f"""
            <div class='dsek'>
            <div class='sek-lbl'>👥 Folkerekka</div>
            <div class='folkrad'>
                <div class='folktop'><span class='folk-n'>Hjemme</span><span class='folk-p'>{fh}%</span></div>
                <div class='bar'><div class='bar-h' style='width:{fh}%'></div></div>
            </div>
            <div class='folkrad'>
                <div class='folktop'><span class='folk-n'>Uavgjort</span><span class='folk-p'>{fu}%</span></div>
                <div class='bar'><div class='bar-u' style='width:{fu}%'></div></div>
            </div>
            <div class='folkrad'>
                <div class='folktop'><span class='folk-n'>Borte</span><span class='folk-p'>{fb}%</span></div>
                <div class='bar'><div class='bar-b' style='width:{fb}%'></div></div>
            </div>
            </div>""", unsafe_allow_html=True)

        with k2:
            st.markdown("<div class='dsek'>", unsafe_allow_html=True)
            st.markdown("<div class='sek-lbl'>📈 Markedsodds</div>", unsafe_allow_html=True)
            if im and rå:
                for lbl, key, fv in [("Hjemme","H",fh),("Uavgjort","U",fu),("Borte","B",fb)]:
                    av = round(im[key]-fv, 1)
                    cls, tekst = avvik_css(av)
                    st.markdown(f"""<div class='urad'>
                        <span class='u-n'>{lbl}</span>
                        <span class='u-p'>{im[key]}%</span>
                        <span class='u-tag'>{rå[key]}</span>
                        <span class='u-av {cls}'>{tekst}</span>
                    </div>""", unsafe_allow_html=True)
            else:
                st.markdown("<div class='ingen'>Odds ikke tilgjengelig</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with k3:
            xg_suf = " (inkl. xG)" if poi and poi.get("xg") else ""
            st.markdown("<div class='dsek'>", unsafe_allow_html=True)
            st.markdown(f"<div class='sek-lbl'>🔢 Poisson-modell{xg_suf}</div>", unsafe_allow_html=True)
            if poi:
                for lbl, key, fv in [("Hjemme","H",fh),("Uavgjort","U",fu),("Borte","B",fb)]:
                    av = round(poi[key]-fv, 1)
                    cls, tekst = avvik_css(av)
                    lam = poi['lh'] if key=='H' else (poi['lb'] if key=='B' else "–")
                    tag = f"λ={lam}" if key != 'U' else "–"
                    st.markdown(f"""<div class='urad'>
                        <span class='u-n'>{lbl}</span>
                        <span class='u-p'>{poi[key]}%</span>
                        <span class='u-tag'>{tag}</span>
                        <span class='u-av {cls}'>{tekst}</span>
                    </div>""", unsafe_allow_html=True)
            else:
                if not FOOTBALL_DATA_KEY:
                    msg = "FOOTBALL_DATA_KEY mangler i Secrets"
                elif not hs: msg = f"Ingen data for {hjem}"
                elif not bs: msg = f"Ingen data for {borte}"
                else: msg = "Beregning feilet"
                st.markdown(f"<div class='ingen'>{msg}</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # Lagstatistikk
        if hs or bs:
            st.markdown("<div class='stagsek'>", unsafe_allow_html=True)
            ss1, ss2 = st.columns(2)
            with ss1:
                if hs:
                    xg_str = f" · xG {hxg.get('hxg','–')}" if hxg else ""
                    st.markdown(f"<div class='lag-lbl'>🏠 {hjem} hjemme ({hs.get('hs','–')} kamper{xg_str})</div>", unsafe_allow_html=True)
                    sc=styrke_cls(hs.get("ah")); fc=styrke_cls(hs.get("fh"))
                    st.markdown(f"""<div class='chips'>
                        <div class='chip'><div class='c-lbl'>Scoret/kamp</div><div class='c-val {sc}'>{hs.get('hsc','–')}</div></div>
                        <div class='chip'><div class='c-lbl'>Innsluppet/kamp</div><div class='c-val'>{hs.get('hin','–')}</div></div>
                        <div class='chip'><div class='c-lbl'>Angrepsstyrke</div><div class='c-val {sc}'>{hs.get('ah','–')}</div><div class='c-sub'>1.0 = ligasnitt</div></div>
                        <div class='chip'><div class='c-lbl'>Forsvarsstyrke</div><div class='c-val {fc}'>{hs.get('fh','–')}</div><div class='c-sub'>1.0 = ligasnitt</div></div>
                    </div>""", unsafe_allow_html=True)
            with ss2:
                if bs:
                    xg_str2 = f" · xG {bxg.get('bxg','–')}" if bxg else ""
                    st.markdown(f"<div class='lag-lbl'>✈️ {borte} borte ({bs.get('bs','–')} kamper{xg_str2})</div>", unsafe_allow_html=True)
                    sc2=styrke_cls(bs.get("ab")); fc2=styrke_cls(bs.get("fb"))
                    st.markdown(f"""<div class='chips'>
                        <div class='chip'><div class='c-lbl'>Scoret/kamp</div><div class='c-val {sc2}'>{bs.get('bsc','–')}</div></div>
                        <div class='chip'><div class='c-lbl'>Innsluppet/kamp</div><div class='c-val'>{bs.get('bin','–')}</div></div>
                        <div class='chip'><div class='c-lbl'>Angrepsstyrke</div><div class='c-val {sc2}'>{bs.get('ab','–')}</div><div class='c-sub'>1.0 = ligasnitt</div></div>
                        <div class='chip'><div class='c-lbl'>Forsvarsstyrke</div><div class='c-val {fc2}'>{bs.get('fb','–')}</div><div class='c-sub'>1.0 = ligasnitt</div></div>
                    </div>""", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # Poisson-forklaring
        if poi and hs and bs:
            steg, konklusjon = lag_forklaring(hjem, borte, hs, bs, poi, hxg, bxg)
            with st.expander("🔍 Hvorfor gir modellen disse resultatene?"):
                st.markdown("<div class='poi-sek'>", unsafe_allow_html=True)
                st.markdown("<div style='font-size:11px;font-weight:700;color:#3b82f6;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:12px'>🔢 Poisson-modellen steg for steg (Dixon-Coles)</div>", unsafe_allow_html=True)
                for i, s in enumerate(steg):
                    st.markdown(f"""
                    <div class='poi-steg'>
                        <div class='steg-num'>{i+1}</div>
                        <div class='steg-innhold'>
                            <div class='steg-top'>
                                <span class='steg-lbl'>{s['label']}</span>
                                <span class='steg-val'>{s['verdi']}</span>
                            </div>
                            <div class='steg-bsk'>{s['bsk']}</div>
                        </div>
                    </div>""", unsafe_allow_html=True)

                st.markdown(f"""
                <div class='poi-konklusjon'>
                    <div class='poi-k-tittel'>📊 Konklusjon</div>
                    <div class='poi-k-tekst'>{konklusjon}</div>
                </div>""", unsafe_allow_html=True)

                # Resultat-bokser
                res_html = "<div class='poi-resultat'>"
                for lbl, key, fv in [("Hjemme","H",fh),("Uavgjort","U",fu),("Borte","B",fb)]:
                    av = round(poi[key]-fv, 1)
                    farge = "#10b981" if av > 8 else ("#f43f5e" if av < -8 else "#64748b")
                    p = "+" if av > 0 else ""
                    res_html += f"""<div class='poi-res-boks' style='border:1px solid {farge}30'>
                        <div class='pr-lbl'>{lbl}</div>
                        <div class='pr-val'>{poi[key]}%</div>
                        <div class='pr-av' style='color:{farge}'>{p}{av}pp vs folk</div>
                    </div>"""
                res_html += "</div>"
                st.markdown(res_html, unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

# Footer
st.markdown(f"""
<div class='footer'>
    <div class='f-stat'><div class='f-val'>{len(df_vis)}</div><div class='f-lbl'>Kamper vist</div></div>
    <div class='f-stat'><div class='f-val'>{verdikamper_total}</div><div class='f-lbl'>Verdisignaler</div></div>
    <div class='f-stat'><div class='f-val'>{len(fd_cache)}</div><div class='f-lbl'>Ligaer m/ stat</div></div>
    <div class='f-stat'><div class='f-val'>{len(xg_cache)}</div><div class='f-lbl'>Ligaer m/ xG</div></div>
    <div class='f-stat'><div class='f-val' style='font-size:16px'>{datetime.now().strftime('%H:%M')}</div><div class='f-lbl'>Oppdatert</div></div>
</div>
""", unsafe_allow_html=True)
