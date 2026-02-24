"""
Backtesting-script for TippingAnalyse Poisson-modell.
Kjøres lokalt: python backtest.py

Henter historiske kamper fra FotMob, kjører walk-forward simulering
med grid search over modellparametre.
"""

import json
import os
import time
import csv
import math
import itertools
from collections import defaultdict

from backtest_config import DEFAULT_PARAMS, PARAM_GRID, MIN_MATCHES_BEFORE_EVAL, TRAIN_RATIO
from fotmob_api import (
    FOTMOB_LIGA_IDS, hent_fotmob_tabell, hent_fotmob_team,
    beregn_styrke, beregn_form_styrke, beregn_dyp_poisson,
)

CACHE_DIR = os.path.join(os.path.dirname(__file__), "backtest_cache")
RESULTS_FILE = os.path.join(os.path.dirname(__file__), "backtest_results.json")
DETAILS_FILE = os.path.join(os.path.dirname(__file__), "backtest_details.csv")

# Ligaer å backteste (kun nasjonale ligaer, ikke cup/europa)
BACKTEST_LEAGUES = {
    "ENG Premier League": 47,
    "ENG Championship": 48,
    "SPA LaLiga": 87,
    "ITA Serie A": 55,
    "GER Bundesliga": 54,
    "FRA Ligue 1": 53,
    "NOR Eliteserien": 59,
    "SKO Premiership": 65,
    "NED Eredivisie": 57,
}


# ─────────────────────────────────────────────
# STEG A: DATAHENTING MED CACHING
# ─────────────────────────────────────────────

def ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def cache_path(kind, entity_id):
    return os.path.join(CACHE_DIR, f"{kind}_{entity_id}.json")


def load_cached(kind, entity_id):
    path = cache_path(kind, entity_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cached(kind, entity_id, data):
    path = cache_path(kind, entity_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def fetch_league_table(liga_name, liga_id):
    """Henter ligatabell, med caching."""
    cached = load_cached("league", liga_id)
    if cached:
        return cached
    print(f"  Henter tabell for {liga_name} (id={liga_id})...")
    data = hent_fotmob_tabell(liga_id)
    if data:
        save_cached("league", liga_id, data)
        time.sleep(1)
    return data


def fetch_team_data(team_id):
    """Henter lagdata, med caching."""
    cached = load_cached("team", team_id)
    if cached:
        return cached
    print(f"  Henter lag {team_id}...")
    data = hent_fotmob_team(team_id)
    if data:
        save_cached("team", team_id, data)
        time.sleep(1)
    return data


def fetch_all_data():
    """Henter alle liga- og lagdata."""
    ensure_cache_dir()
    league_data = {}
    all_team_data = {}

    for liga_name, liga_id in BACKTEST_LEAGUES.items():
        print(f"\n{'='*50}")
        print(f"Liga: {liga_name}")
        print(f"{'='*50}")

        ld = fetch_league_table(liga_name, liga_id)
        if not ld or not ld.get("teams"):
            print(f"  FEIL: Ingen tabelldata for {liga_name}")
            continue

        league_data[liga_name] = ld
        teams = ld["teams"]

        for team_name, stats in teams.items():
            team_id = stats.get("team_id")
            if not team_id:
                continue
            if team_id in all_team_data:
                continue

            td = fetch_team_data(team_id)
            if td:
                all_team_data[team_id] = td
                n_fixtures = len(td.get("fixtures", []))
                print(f"    {team_name}: {n_fixtures} kamper")
            else:
                print(f"    {team_name}: FEIL ved henting")

    return league_data, all_team_data


# ─────────────────────────────────────────────
# STEG B: BYGG KAMP-KORPUS
# ─────────────────────────────────────────────

def build_match_corpus(league_data, all_team_data):
    """Bygger deduplisert kamp-korpus per liga."""
    corpus = {}  # liga -> list of matches

    for liga_name, ld in league_data.items():
        teams = ld["teams"]
        team_ids_in_league = set()
        for stats in teams.values():
            tid = stats.get("team_id")
            if tid:
                team_ids_in_league.add(tid)

        seen = set()
        matches = []

        for team_id in team_ids_in_league:
            td = all_team_data.get(team_id)
            if not td:
                continue

            for fx in td.get("fixtures", []):
                home_id = fx["home_id"]
                away_id = fx["away_id"]

                # Kun ligakamper: begge lag må tilhøre ligaen
                if home_id not in team_ids_in_league or away_id not in team_ids_in_league:
                    continue

                # Dedupliser
                key = (home_id, away_id, fx["home_goals"], fx["away_goals"])
                if key in seen:
                    continue
                seen.add(key)

                # Bestem faktisk resultat
                if fx["home_goals"] > fx["away_goals"]:
                    result = "H"
                elif fx["home_goals"] == fx["away_goals"]:
                    result = "U"
                else:
                    result = "B"

                matches.append({
                    "home_id": home_id,
                    "away_id": away_id,
                    "home_name": fx["home_name"],
                    "away_name": fx["away_name"],
                    "home_goals": fx["home_goals"],
                    "away_goals": fx["away_goals"],
                    "result": result,
                    "liga": liga_name,
                })

        corpus[liga_name] = matches
        print(f"{liga_name}: {len(matches)} unike ligakamper")

    return corpus


# ─────────────────────────────────────────────
# STEG C: WALK-FORWARD SIMULERING
# ─────────────────────────────────────────────

def compute_league_averages(prior_matches):
    """Beregner ligasnitt fra forutgående kamper."""
    home_goals = sum(m["home_goals"] for m in prior_matches)
    away_goals = sum(m["away_goals"] for m in prior_matches)
    n = len(prior_matches)
    if n == 0:
        return 1.4, 1.1
    return home_goals / n, away_goals / n


def compute_team_stats_from_history(prior_matches, team_id):
    """Beregner hjemme/borte-statistikk for et lag fra historiske kamper."""
    hjemme_spilt = 0
    hjemme_scoret = 0
    hjemme_innsluppet = 0
    borte_spilt = 0
    borte_scoret = 0
    borte_innsluppet = 0

    for m in prior_matches:
        if m["home_id"] == team_id:
            hjemme_spilt += 1
            hjemme_scoret += m["home_goals"]
            hjemme_innsluppet += m["away_goals"]
        elif m["away_id"] == team_id:
            borte_spilt += 1
            borte_scoret += m["away_goals"]
            borte_innsluppet += m["home_goals"]

    return {
        "hjemme_spilt": hjemme_spilt,
        "hjemme_scoret": hjemme_scoret,
        "hjemme_innsluppet": hjemme_innsluppet,
        "borte_spilt": borte_spilt,
        "borte_scoret": borte_scoret,
        "borte_innsluppet": borte_innsluppet,
    }


def compute_form_from_history(prior_matches, team_id, is_home, form_window):
    """Beregner form fra historiske kamper (siste N hjemme/borte-kamper)."""
    relevante = []
    for m in reversed(prior_matches):
        if is_home and m["home_id"] == team_id:
            relevante.append({
                "home_goals": m["home_goals"],
                "away_goals": m["away_goals"],
                "is_home": True,
            })
        elif not is_home and m["away_id"] == team_id:
            relevante.append({
                "home_goals": m["home_goals"],
                "away_goals": m["away_goals"],
                "is_home": False,
            })
        if len(relevante) >= form_window:
            break

    if len(relevante) < 3:
        return None

    scoret = sum(fx["home_goals"] if fx["is_home"] else fx["away_goals"] for fx in relevante)
    innsluppet = sum(fx["away_goals"] if fx["is_home"] else fx["home_goals"] for fx in relevante)

    return {
        "kamper": len(relevante),
        "scoret_snitt": scoret / len(relevante),
        "innsluppet_snitt": innsluppet / len(relevante),
    }


def count_team_matches(prior_matches, team_id):
    """Teller antall kamper et lag har spilt."""
    return sum(1 for m in prior_matches if m["home_id"] == team_id or m["away_id"] == team_id)


def walk_forward_evaluate(matches, params):
    """
    Walk-forward evaluering av en parameterkombinajon.
    Returnerer liste med (prediction, actual_result) per kamp.
    """
    results = []
    form_window = params.get("form_window", DEFAULT_PARAMS["form_window"])

    for i, match in enumerate(matches):
        prior = matches[:i]

        # Krev minimum kamper
        h_count = count_team_matches(prior, match["home_id"])
        a_count = count_team_matches(prior, match["away_id"])
        if h_count < MIN_MATCHES_BEFORE_EVAL or a_count < MIN_MATCHES_BEFORE_EVAL:
            continue

        # Beregn ligasnitt
        league_avg_home, league_avg_away = compute_league_averages(prior)

        # Beregn lagstatistikk
        h_stats = compute_team_stats_from_history(prior, match["home_id"])
        b_stats = compute_team_stats_from_history(prior, match["away_id"])

        # Beregn form
        h_form = compute_form_from_history(prior, match["home_id"], True, form_window)
        b_form = compute_form_from_history(prior, match["away_id"], False, form_window)

        # Kjør modell (uten xG — V1 begrensning)
        pred = beregn_dyp_poisson(
            h_stats, b_stats, league_avg_home, league_avg_away,
            h_form, b_form, None, None,
            params=params,
        )
        if not pred:
            continue

        # Bestem predikert resultat
        probs = {"H": pred["H"], "U": pred["U"], "B": pred["B"]}
        predicted = max(probs, key=probs.get)

        results.append({
            "match": match,
            "predicted": predicted,
            "actual": match["result"],
            "prob_H": pred["H"],
            "prob_U": pred["U"],
            "prob_B": pred["B"],
            "lambda_h": pred["lambda_h"],
            "lambda_b": pred["lambda_b"],
        })

    return results


# ─────────────────────────────────────────────
# STEG D: GRID SEARCH
# ─────────────────────────────────────────────

def compute_metrics(results):
    """Beregner accuracy, log-loss, Brier score og verdi-treffrate."""
    if not results:
        return {"accuracy": 0, "log_loss": 999, "brier": 999, "n": 0}

    correct = 0
    total_log_loss = 0
    total_brier = 0
    n = len(results)

    for r in results:
        actual = r["actual"]
        predicted = r["predicted"]

        if predicted == actual:
            correct += 1

        # Sannsynligheter
        prob_map = {"H": r["prob_H"] / 100, "U": r["prob_U"] / 100, "B": r["prob_B"] / 100}

        # Log loss
        actual_prob = max(prob_map[actual], 1e-10)
        total_log_loss += -math.log(actual_prob)

        # Brier score
        for outcome in ["H", "U", "B"]:
            actual_val = 1.0 if outcome == actual else 0.0
            total_brier += (prob_map[outcome] - actual_val) ** 2

    return {
        "accuracy": round(correct / n * 100, 2),
        "log_loss": round(total_log_loss / n, 4),
        "brier": round(total_brier / n, 4),
        "n": n,
        "correct": correct,
    }


def generate_param_combos(grid):
    """Genererer alle parameterkombinasjoner fra griden."""
    keys = sorted(grid.keys())
    values = [grid[k] for k in keys]
    combos = []
    for combo in itertools.product(*values):
        combos.append(dict(zip(keys, combo)))
    return combos


def run_grid_search(all_matches):
    """Kjører grid search over alle parameterkombinasjoner."""
    combos = generate_param_combos(PARAM_GRID)
    print(f"\nGrid search: {len(combos)} parameterkombinasjoner")
    print(f"Totalt {len(all_matches)} kamper å evaluere\n")

    # Split i train/test
    split_idx = int(len(all_matches) * TRAIN_RATIO)
    train_matches = all_matches[:split_idx]
    test_matches = all_matches[split_idx:]
    print(f"Train: {len(train_matches)} kamper, Test: {len(test_matches)} kamper\n")

    best_train = None
    best_train_metrics = {"log_loss": 999}
    all_results = []

    for idx, params in enumerate(combos):
        # Evaluer på train-set
        train_results = walk_forward_evaluate(train_matches, params)
        train_metrics = compute_metrics(train_results)

        all_results.append({
            "params": params,
            "train_metrics": train_metrics,
        })

        if train_metrics["log_loss"] < best_train_metrics["log_loss"] and train_metrics["n"] > 0:
            best_train_metrics = train_metrics
            best_train = params

        if (idx + 1) % 10 == 0 or idx == 0:
            print(f"  [{idx+1}/{len(combos)}] Acc={train_metrics['accuracy']}% "
                  f"LogLoss={train_metrics['log_loss']} n={train_metrics['n']}")

    # Evaluer beste på test-set
    print(f"\nBeste parametre (train): {best_train}")
    print(f"  Train: {best_train_metrics}")

    test_results = walk_forward_evaluate(test_matches, best_train)
    test_metrics = compute_metrics(test_results)
    print(f"  Test:  {test_metrics}")

    # Evaluer standardparametre for sammenligning
    default_train_results = walk_forward_evaluate(train_matches, DEFAULT_PARAMS)
    default_train_metrics = compute_metrics(default_train_results)
    default_test_results = walk_forward_evaluate(test_matches, DEFAULT_PARAMS)
    default_test_metrics = compute_metrics(default_test_results)

    print(f"\nStandard parametre:")
    print(f"  Train: {default_train_metrics}")
    print(f"  Test:  {default_test_metrics}")

    return {
        "best_params": best_train,
        "best_train_metrics": best_train_metrics,
        "best_test_metrics": test_metrics,
        "default_train_metrics": default_train_metrics,
        "default_test_metrics": default_test_metrics,
        "all_results": all_results,
        "test_details": test_results,
    }


# ─────────────────────────────────────────────
# STEG E: LAGRE RESULTATER
# ─────────────────────────────────────────────

def compute_per_league_metrics(all_matches, params):
    """Beregner metrics per liga."""
    liga_matches = defaultdict(list)
    for m in all_matches:
        liga_matches[m["liga"]].append(m)

    per_liga = {}
    for liga, matches in liga_matches.items():
        results = walk_forward_evaluate(matches, params)
        metrics = compute_metrics(results)
        per_liga[liga] = metrics
    return per_liga


def compute_calibration(results, n_bins=10):
    """Beregner kalibrering: predikert vs observert frekvens."""
    bins = [[] for _ in range(n_bins)]

    for r in results:
        for outcome in ["H", "U", "B"]:
            prob = r[f"prob_{outcome}"] / 100
            actual = 1.0 if r["actual"] == outcome else 0.0
            bin_idx = min(int(prob * n_bins), n_bins - 1)
            bins[bin_idx].append((prob, actual))

    calibration = []
    for i, bin_data in enumerate(bins):
        if not bin_data:
            continue
        avg_pred = sum(p for p, _ in bin_data) / len(bin_data)
        avg_actual = sum(a for _, a in bin_data) / len(bin_data)
        calibration.append({
            "bin": f"{i*10}-{(i+1)*10}%",
            "avg_predicted": round(avg_pred * 100, 1),
            "avg_observed": round(avg_actual * 100, 1),
            "n": len(bin_data),
        })
    return calibration


def compute_sensitivity(all_results):
    """Beregner parametersensitivitet: accuracy per parameterverdi."""
    sensitivity = {}
    for param_name in PARAM_GRID:
        param_values = {}
        for r in all_results:
            val = r["params"][param_name]
            if val not in param_values:
                param_values[val] = []
            param_values[val].append(r["train_metrics"]["accuracy"])

        sensitivity[param_name] = {
            str(k): round(sum(v) / len(v), 2) for k, v in sorted(param_values.items())
        }
    return sensitivity


def save_results(grid_results, all_matches):
    """Lagrer resultater til JSON og CSV."""
    best_params = grid_results["best_params"]

    # Per-liga metrics med beste parametre
    per_liga_best = compute_per_league_metrics(all_matches, best_params)
    per_liga_default = compute_per_league_metrics(all_matches, DEFAULT_PARAMS)

    # Kalibrering
    all_results_best = walk_forward_evaluate(all_matches, best_params)
    calibration = compute_calibration(all_results_best)

    # Sensitivitet
    sensitivity = compute_sensitivity(grid_results["all_results"])

    # JSON-resultat
    output = {
        "best_params": best_params,
        "default_params": DEFAULT_PARAMS,
        "best_train_metrics": grid_results["best_train_metrics"],
        "best_test_metrics": grid_results["best_test_metrics"],
        "default_train_metrics": grid_results["default_train_metrics"],
        "default_test_metrics": grid_results["default_test_metrics"],
        "per_liga_best": per_liga_best,
        "per_liga_default": per_liga_default,
        "calibration": calibration,
        "sensitivity": sensitivity,
        "total_matches": len(all_matches),
        "note": "V1: Backtest uten xG (kun sesongaggregert, ikke per-kamp historisk)",
    }

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nResultater lagret til {RESULTS_FILE}")

    # CSV med per-kamp prediksjoner
    if all_results_best:
        with open(DETAILS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "liga", "home_name", "away_name", "home_goals", "away_goals",
                "actual", "predicted", "prob_H", "prob_U", "prob_B",
                "lambda_h", "lambda_b", "correct",
            ])
            writer.writeheader()
            for r in all_results_best:
                m = r["match"]
                writer.writerow({
                    "liga": m["liga"],
                    "home_name": m["home_name"],
                    "away_name": m["away_name"],
                    "home_goals": m["home_goals"],
                    "away_goals": m["away_goals"],
                    "actual": r["actual"],
                    "predicted": r["predicted"],
                    "prob_H": r["prob_H"],
                    "prob_U": r["prob_U"],
                    "prob_B": r["prob_B"],
                    "lambda_h": r["lambda_h"],
                    "lambda_b": r["lambda_b"],
                    "correct": r["predicted"] == r["actual"],
                })
        print(f"Detaljer lagret til {DETAILS_FILE}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("TippingAnalyse Backtest")
    print("=" * 60)

    # Steg A: Hent data
    print("\n--- Steg A: Henter data fra FotMob ---")
    league_data, all_team_data = fetch_all_data()

    if not league_data:
        print("FEIL: Ingen ligadata hentet. Avslutter.")
        return

    # Steg B: Bygg kamp-korpus
    print("\n--- Steg B: Bygger kamp-korpus ---")
    corpus = build_match_corpus(league_data, all_team_data)

    # Kombiner alle kamper i kronologisk rekkefølge (vi bruker fixture-rekkefølgen)
    all_matches = []
    for liga_name, matches in corpus.items():
        all_matches.extend(matches)

    if not all_matches:
        print("FEIL: Ingen kamper funnet. Avslutter.")
        return

    print(f"\nTotalt: {len(all_matches)} kamper")

    # Steg D: Grid search
    print("\n--- Steg D: Grid search ---")
    grid_results = run_grid_search(all_matches)

    # Steg E: Lagre resultater
    print("\n--- Steg E: Lagrer resultater ---")
    save_results(grid_results, all_matches)

    print("\n" + "=" * 60)
    print("Backtest fullført!")
    print("=" * 60)


if __name__ == "__main__":
    main()
