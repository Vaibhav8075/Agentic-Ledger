"""
Trains the evening-revenue LSTM and writes an honest evaluation report.

Data: datasets/synthetic_sales_data_400k.csv (a synthetic retail sales dataset from Kaggle).
Each Region-and-Sales-Rep pair is treated as one "merchant", giving 20 daily sales series of
730 days. The dataset has no time of day, so the morning (00:00-16:00) / evening split is
SYNTHETIC: each day's morning share is drawn from N(0.40, 0.05). Metrics therefore show that the
pipeline works end to end; they are not evidence of performance on real Paytm merchants.

Split: chronological by target date (70% train / 15% validation / 15% test). The validation set
drives early stopping and calibrates the conservative floor; the test set is used once at the end.

Outputs: models/evening_lstm.pt (weights + metadata) and models/metrics.json.
"""

import json
import os
import sys

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ml.forecaster import (DEFAULT_MODEL_PATH, FEATURE_VERSION, HISTORY_DAYS, EveningRevenueLSTM,
                           Forecaster, to_relative)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "datasets", "synthetic_sales_data_400k.csv")
METRICS_PATH = os.path.join(BASE_DIR, "models", "metrics.json")
SEED = 42
FLOOR_QUANTILE = 0.10  # the floor should be beaten on ~90% of days
HIDDEN_SIZE = 16


def build_samples(df: pd.DataFrame, rng: np.random.Generator):
    daily = (df.groupby(["Region_and_Sales_Rep", "Sale_Date"])["Sales_Amount"].sum()
               .reset_index().sort_values(["Region_and_Sales_Rep", "Sale_Date"]))
    past, morning, target, dates = [], [], [], []
    for _, series in daily.groupby("Region_and_Sales_Rep"):
        totals = series["Sales_Amount"].to_numpy()
        share = np.clip(rng.normal(0.40, 0.05, len(totals)), 0.2, 0.6)  # synthetic morning share
        day = np.stack([totals * share, totals * (1 - share)], axis=1)  # [morning, evening]
        for i in range(HISTORY_DAYS, len(day)):
            past.append(day[i - HISTORY_DAYS:i])
            morning.append(day[i, 0])
            target.append(day[i, 1])
            dates.append(series["Sale_Date"].iloc[i])
    return np.array(past), np.array(morning), np.array(target), np.array(dates)


def scores(actual: np.ndarray, predicted: np.ndarray) -> dict:
    err = actual - predicted
    return {
        "mae_inr": round(float(np.abs(err).mean()), 2),
        "mape_pct": round(float(np.mean(np.abs(err) / actual) * 100), 2),
        "r2": round(float(1 - (err ** 2).sum() / ((actual - actual.mean()) ** 2).sum()), 4),
    }


def main():
    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)

    print("Loading dataset...")
    df = pd.read_csv(DATA_PATH, usecols=["Sale_Date", "Region_and_Sales_Rep", "Sales_Amount"])
    past, morning, target, dates = build_samples(df, rng)

    unique_dates = np.sort(np.unique(dates))
    train_end = unique_dates[int(len(unique_dates) * 0.70)]
    val_end = unique_dates[int(len(unique_dates) * 0.85)]
    split = {"train": dates < train_end, "val": (dates >= train_end) & (dates < val_end), "test": dates >= val_end}
    print({k: int(v.sum()) for k, v in split.items()}, "samples")

    past_rel, morning_rel, scale = to_relative(past, morning)
    target_rel = target / scale

    def tensors(mask):
        return (torch.tensor(past_rel[mask], dtype=torch.float32),
                torch.tensor(morning_rel[mask][:, None], dtype=torch.float32),
                torch.tensor(target_rel[mask][:, None], dtype=torch.float32))

    train_x, train_m, train_y = tensors(split["train"])
    val_x, val_m, val_y = tensors(split["val"])

    model = EveningRevenueLSTM(HIDDEN_SIZE)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()
    best_val, best_state, patience, bad_epochs = float("inf"), None, 20, 0

    print("Training...")
    for epoch in range(300):
        model.train()
        order = torch.randperm(len(train_y))
        for start in range(0, len(order), 256):
            idx = order[start:start + 256]
            optimizer.zero_grad()
            loss = loss_fn(model(train_x[idx], train_m[idx]), train_y[idx])
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            val_loss = loss_fn(model(val_x, val_m), val_y).item()
        if val_loss < best_val - 1e-6:
            best_val, best_state, bad_epochs = val_loss, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            bad_epochs += 1
        if (epoch + 1) % 25 == 0:
            print(f"epoch {epoch + 1}: val MSE (relative) {val_loss:.5f}")
        if bad_epochs >= patience:
            print(f"Early stop at epoch {epoch + 1}")
            break
    model.load_state_dict(best_state)

    # Calibrate the conservative floor on validation data only
    forecaster = Forecaster(model, floor_ratio=1.0)
    val_pred = forecaster.predict_batch(past[split["val"]], morning[split["val"]])
    floor_ratio = float(np.quantile(target[split["val"]] / val_pred, FLOOR_QUANTILE))

    # Final, one-time evaluation on the test period
    test = split["test"]
    pred = forecaster.predict_batch(past[test], morning[test])
    actual = target[test]
    hist_evening = past[test][:, :, 1].mean(axis=1)
    hist_ratio = (past[test][:, :, 1] / past[test][:, :, 0]).mean(axis=1)
    hist_total = past[test].sum(axis=2).mean(axis=1)
    metrics = {
        "dataset": "datasets/synthetic_sales_data_400k.csv (synthetic, Kaggle); 20 Region-and-Sales-Rep series",
        "caveat": "Morning/evening split is synthetic (dataset has no time of day). Not evidence of real-merchant performance.",
        "split": {"train_before": str(train_end), "val_before": str(val_end),
                  "samples": {k: int(v.sum()) for k, v in split.items()}},
        "test": {
            "lstm": scores(actual, pred),
            "baseline_mean_of_last_3_evenings": scores(actual, hist_evening),
            "baseline_morning_times_past_evening_ratio": scores(actual, morning[test] * hist_ratio),
            "baseline_past_mean_total_minus_morning": scores(actual, np.maximum(hist_total - morning[test], 0)),
        },
        "floor": {
            "quantile": FLOOR_QUANTILE,
            "ratio_to_expected": round(floor_ratio, 4),
            "test_coverage_pct": round(float(np.mean(actual >= pred * floor_ratio) * 100), 2),
        },
        "best_val_mse_relative": round(best_val, 6),
        "seed": SEED,
    }

    torch.save({"state_dict": model.state_dict(), "hidden_size": HIDDEN_SIZE, "history_days": HISTORY_DAYS,
                "feature_version": FEATURE_VERSION, "floor_ratio": floor_ratio}, DEFAULT_MODEL_PATH)
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(json.dumps(metrics["test"], indent=2))
    print(json.dumps(metrics["floor"], indent=2))
    print(f"Saved {DEFAULT_MODEL_PATH} and {METRICS_PATH}")


if __name__ == "__main__":
    main()
