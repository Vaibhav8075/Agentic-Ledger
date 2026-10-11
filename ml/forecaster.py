"""
Evening-revenue forecaster used by the Liquidity Engine.

The model predicts a merchant's sales between 16:00 and midnight from the previous days'
[morning, evening] sales and today's morning sales. All inputs are divided by the merchant's
mean daily sales over the history window, so the same model works for a Rs 10k/day kirana and
a Rs 20 lakh/day distributor. (The first version used absolute rupee values with a scaler fitted
on dataset-wide totals of ~Rs 2 crore/day, so its output never changed for real merchants.)

The forecast is advisory. Decisions use `floor`, a conservative lower bound calibrated on held-out
data, and the deterministic guardrail always has the final say.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn

HISTORY_DAYS = 3
FEATURE_VERSION = 2
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "evening_lstm.pt"


class EveningRevenueLSTM(nn.Module):
    """LSTM over past days' [morning, evening] sales, joined with today's morning sales."""

    def __init__(self, hidden_size: int = 16):
        super().__init__()
        self.lstm = nn.LSTM(input_size=2, hidden_size=hidden_size, batch_first=True)
        self.head = nn.Sequential(nn.Linear(hidden_size + 1, 16), nn.ReLU(), nn.Linear(16, 1))

    def forward(self, past: torch.Tensor, today_morning: torch.Tensor) -> torch.Tensor:
        # past: (batch, HISTORY_DAYS, 2), today_morning: (batch, 1)
        _, (hidden, _) = self.lstm(past)
        return self.head(torch.cat([hidden[-1], today_morning], dim=1))


def to_relative(past: np.ndarray, today_morning: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Divides by mean daily sales over the history window. Returns (past_rel, morning_rel, scale)."""
    scale = past.sum(axis=-1).mean(axis=-1)
    if np.any(scale <= 0):
        raise ValueError("Sales history must contain positive sales.")
    return past / scale[:, None, None], today_morning / scale, scale


@dataclass
class EveningForecast:
    expected: float
    floor: float


class Forecaster:
    def __init__(self, model: EveningRevenueLSTM, floor_ratio: float):
        self.model = model.eval()
        self.floor_ratio = floor_ratio

    @classmethod
    def load(cls, path: Path = DEFAULT_MODEL_PATH) -> "Forecaster":
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        if checkpoint.get("feature_version") != FEATURE_VERSION or checkpoint.get("history_days") != HISTORY_DAYS:
            raise ValueError(f"{path} was trained with a different feature layout; retrain with scripts/train_lstm.py")
        model = EveningRevenueLSTM(hidden_size=checkpoint["hidden_size"])
        model.load_state_dict(checkpoint["state_dict"])
        return cls(model, float(checkpoint["floor_ratio"]))

    def predict_batch(self, past: np.ndarray, today_morning: np.ndarray) -> np.ndarray:
        """past: (n, HISTORY_DAYS, 2) rupees, today_morning: (n,) rupees -> expected evening rupees (n,)."""
        past_rel, morning_rel, scale = to_relative(past.astype(np.float64), today_morning.astype(np.float64))
        with torch.no_grad():
            out = self.model(torch.tensor(past_rel, dtype=torch.float32),
                             torch.tensor(morning_rel[:, None], dtype=torch.float32))
        return np.maximum(out.numpy()[:, 0], 0.0) * scale

    def predict(self, past_days: Sequence[Sequence[float]], today_morning: float) -> EveningForecast:
        past = np.asarray(past_days, dtype=np.float64)
        if past.shape != (HISTORY_DAYS, 2):
            raise ValueError(f"Expected {HISTORY_DAYS} days of [morning, evening] sales.")
        expected = float(self.predict_batch(past[None], np.array([today_morning]))[0])
        return EveningForecast(expected=round(expected, 2), floor=round(expected * self.floor_ratio, 2))
