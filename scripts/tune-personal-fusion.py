#!/usr/bin/env python3
"""
Personal fusion weight tuner for rime-chth1z (prior-offset + CV L2 ridge regularization).
Reads local privacy-sanitized disambiguation events from `%APPDATA%/Rime/zhiyi/feedback.jsonl`
and fits a gentle personal correction `w = w_prior + delta` (with L2 penalty `lambda * ||delta||^2`
chosen by 5-fold cross-validation) so small personal datasets never overfit.

Usage:
    python scripts/tune-personal-fusion.py
    python scripts/tune-personal-fusion.py --min-samples 50
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
from typing import List, Tuple

import numpy as np

# General dev-calibrated prior weights: [w_logit, w_rank, w_gram, w_char_lp, w_ctx_lp]
W_PRIOR = np.array([0.91, -1.26, 0.05, 0.40, -0.39], dtype=np.float64)


def log_softmax(xs: List[float]) -> np.ndarray:
    arr = np.array(xs, dtype=np.float64)
    m = np.max(arr)
    return arr - (m + np.log(np.sum(np.exp(arr - m))))


def load_samples(path: pathlib.Path) -> List[Tuple[np.ndarray, int]]:
    if not path.is_file():
        return []
    out: List[Tuple[np.ndarray, int]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        cands = rec.get("cands") or []
        logits = rec.get("logits") or []
        grams = rec.get("gram_deltas") or [0.0] * len(cands)
        clps = rec.get("char_lps") or [0.0] * len(cands)
        chosen = rec.get("chosen_text") or ""
        if len(cands) < 2 or len(logits) != len(cands) or chosen not in cands:
            continue
        y = cands.index(chosen)
        lp = log_softmax(logits)
        has_ctx = 1.0 if len((rec.get("context") or "").strip()) >= 2 else 0.0
        X = np.array(
            [
                [lp[i], math.log(i + 1.0), float(grams[i]), float(clps[i]), lp[i] * has_ctx]
                for i in range(len(cands))
            ],
            dtype=np.float64,
        )
        out.append((X, y))
    return out


def fit_offset_ridge(samples: List[Tuple[np.ndarray, int]], lam: float, steps: int = 300) -> np.ndarray:
    """Minimize mean listwise cross-entropy + 0.5 * lam * ||w - W_PRIOR||^2 via stable gradient descent."""
    w = W_PRIOR.copy()
    # Keep step size strictly below 2 / (lam + L_max) so large lambda values never oscillate
    lr = min(0.25, 0.5 / (lam + 4.0))
    n = float(len(samples))
    for _ in range(steps):
        grad = lam * (w - W_PRIOR)
        for X, y in samples:
            s = X @ w
            s -= np.max(s)
            p = np.exp(s)
            p /= np.sum(p)
            p[y] -= 1.0
            grad += (X.T @ p) / n
        if float(np.linalg.norm(grad)) < 1e-6:
            break
        w -= lr * grad
    return w


def eval_acc(samples: List[Tuple[np.ndarray, int]], w: np.ndarray) -> float:
    if not samples:
        return 0.0
    ok = sum(1 for X, y in samples if int(np.argmax(X @ w)) == y)
    return ok / len(samples) * 100.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--log",
        default=os.path.join(os.environ.get("APPDATA", ""), "Rime", "zhiyi", "feedback.jsonl"),
        help="Path to local feedback.jsonl",
    )
    ap.add_argument("--min-samples", type=int, default=30, help="Minimum matched records before fitting")
    args = ap.parse_args()

    log_path = pathlib.Path(args.log)
    samples = load_samples(log_path)
    print(f"Loaded {len(samples)} valid disambiguation records from {log_path}")
    if len(samples) < args.min_samples:
        print(f"Need at least {args.min_samples} records to calibrate safely (keeping prior weights).")
        print("Current prior fusion_weights:", [round(float(x), 3) for x in W_PRIOR])
        return

    prior_acc = eval_acc(samples, W_PRIOR)
    print(f"Prior weights top-1 accuracy on local records: {prior_acc:.2f}%")

    # 5-fold CV over ridge strength lambda (higher lambda = trust general prior more)
    folds = 5
    best_lam = 10.0
    best_cv = prior_acc
    for lam in (0.1, 0.3, 1.0, 3.0, 10.0, 30.0):
        cv_hits = 0
        for f in range(folds):
            val = [s for i, s in enumerate(samples) if i % folds == f]
            trn = [s for i, s in enumerate(samples) if i % folds != f]
            w_f = fit_offset_ridge(trn, lam)
            cv_hits += sum(1 for X, y in val if int(np.argmax(X @ w_f)) == y)
        cv_acc = cv_hits / len(samples) * 100.0
        print(f"  lambda={lam:5.1f} -> 5-fold CV acc = {cv_acc:.2f}%")
        if cv_acc > best_cv + 1e-6:
            best_cv = cv_acc
            best_lam = lam

    if best_cv <= prior_acc:
        print("\nPrior weights already match or beat CV alternatives; no update needed.")
        return

    w_new = fit_offset_ridge(samples, best_lam)
    print(f"\nRecommended personalized weights (lambda={best_lam}, CV {prior_acc:.2f}% -> {best_cv:.2f}%):")
    w_fmt = [round(float(x), 3) for x in w_new]
    print("Paste into zhiyi_rerank/fusion_weights in your schema yaml:")
    print(f"  fusion_weights: {w_fmt}")


if __name__ == "__main__":
    main()
