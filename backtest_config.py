"""
Parameterdefinisjon for backtesting av Poisson-modellen.
"""

# Standardverdier (nåværende hardkodede verdier i app.py)
DEFAULT_PARAMS = {
    "form_weight": 0.5,       # Vekt for form vs sesongsnitt (0.5 = 50% form)
    "form_window": 15,        # Antall siste kamper for formberegning
    "xg_weight": 0.3,         # Vekt for xG-justering (0.3 = 30% xG)
    "value_threshold_pp": 8,  # Prosentpoeng avvik for verdisignal
    "lambda_min": 0.2,        # Minimum forventet mål (clamp)
    "lambda_max": 6.0,        # Maksimum forventet mål (clamp)
}

# Grid for grov søk (fase 1)
PARAM_GRID = {
    "form_weight": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    "form_window": [5, 8, 10, 15],
    "xg_weight": [0.0],  # V1: ingen xG i backtest (kun sesongaggregert, ikke per-kamp)
    "value_threshold_pp": [5, 6, 8, 10, 12],
    "lambda_min": [0.1, 0.2, 0.3],
    "lambda_max": [4.0, 5.0, 6.0],
}

# Minimum kamper per lag før evaluering (oppvarmingsperiode)
MIN_MATCHES_BEFORE_EVAL = 20

# Train/test split
TRAIN_RATIO = 0.7
