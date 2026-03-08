"""
Examiner and art-unit scoring logic.

Produces a composite 0–100 score and Green / Yellow / Red difficulty band,
analogous to PatentAdvisor ETA™ but computed from open USPTO data.

Weights (tunable in config.py):
  40 % – allowance rate  (higher = easier)
  30 % – avg office actions per disposed app  (lower = easier)
  20 % – avg pendency months  (lower = easier)
  10 % – RCE rate  (lower = easier)
"""

from __future__ import annotations

import statistics
from config import SCORE_GREEN, SCORE_YELLOW
from services.uspto_api import get_outcome, count_office_actions, count_rces, pendency_months

# USPTO-wide rough averages used for normalisation
_AVG_OA       = 2.5    # average OAs before disposal
_AVG_PENDENCY = 26.0   # months
_AVG_RCE_RATE = 0.20   # 20 % of apps have an RCE


def _normalise(value: float, worst: float, best: float) -> float:
    """Map value onto [0,100] where best → 100 and worst → 0."""
    if best == worst:
        return 50.0
    clamped = max(min(value, worst), best) if worst > best else max(min(value, best), worst)
    return 100 * (clamped - worst) / (best - worst)


def compute_examiner_score(apps: list[dict]) -> dict:
    """
    Given a list of application dicts (from PEDS), compute examiner stats.

    Returns a dict with keys:
        score, band, color_hex,
        total, patented, abandoned, pending,
        allowance_rate, avg_oa, avg_pendency, rce_rate,
        sample_size
    """
    if not apps:
        return _empty_score()

    patented  = [a for a in apps if get_outcome(a) == "patented"]
    abandoned = [a for a in apps if get_outcome(a) == "abandoned"]
    pending   = [a for a in apps if get_outcome(a) == "pending"]
    disposed  = patented + abandoned

    total = len(apps)
    n_pat = len(patented)
    n_abn = len(abandoned)
    n_dis = len(disposed)

    allowance_rate = n_pat / n_dis if n_dis > 0 else 0.0

    # Office-action and RCE counts come from embedded transactions when available
    oa_counts:  list[float] = []
    rce_counts: list[float] = []
    pendencies: list[float] = []

    for a in disposed:
        # New ODP schema: events are in eventDataBag on the app itself
        oa = count_office_actions(a)
        rc = count_rces(a)
        if oa > 0 or rc > 0:
            oa_counts.append(oa)
            rce_counts.append(rc)
        p = pendency_months(a)
        if p is not None:
            pendencies.append(p)

    avg_oa      = statistics.mean(oa_counts)   if oa_counts   else _AVG_OA
    avg_pend    = statistics.mean(pendencies)  if pendencies  else _AVG_PENDENCY
    rce_rate    = statistics.mean(rce_counts)  if rce_counts  else _AVG_RCE_RATE

    # Component scores (each 0–100, higher = easier for the applicant)
    s_allow   = allowance_rate * 100
    s_oa      = _normalise(avg_oa,      worst=6.0,  best=1.0)
    s_pend    = _normalise(avg_pend,    worst=60.0, best=12.0)
    s_rce     = _normalise(rce_rate,    worst=0.8,  best=0.0)

    composite = 0.40 * s_allow + 0.30 * s_oa + 0.20 * s_pend + 0.10 * s_rce

    band, color_hex = _band(composite)

    return {
        "score":          round(composite, 1),
        "band":           band,
        "color_hex":      color_hex,
        "total":          total,
        "patented":       n_pat,
        "abandoned":      n_abn,
        "pending":        len(pending),
        "allowance_rate": round(allowance_rate * 100, 1),
        "avg_oa":         round(avg_oa, 2),
        "avg_pendency":   round(avg_pend, 1),
        "rce_rate":       round(rce_rate * 100, 1) if rce_counts else None,
        "sample_size":    total,
    }


def compute_art_unit_score(apps: list[dict]) -> dict:
    """Same as examiner score but for a whole art unit's applications."""
    return compute_examiner_score(apps)


def _band(score: float) -> tuple[str, str]:
    if score >= SCORE_GREEN:
        return "Easy (Green)", "#2ecc71"
    if score >= SCORE_YELLOW:
        return "Moderate (Yellow)", "#f39c12"
    return "Difficult (Red)", "#e74c3c"


def _empty_score() -> dict:
    return {
        "score": None, "band": "No data", "color_hex": "#95a5a6",
        "total": 0, "patented": 0, "abandoned": 0, "pending": 0,
        "allowance_rate": None, "avg_oa": None,
        "avg_pendency": None, "rce_rate": None, "sample_size": 0,
    }
