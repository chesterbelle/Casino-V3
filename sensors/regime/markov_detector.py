"""
Markov Regime Detector — Memory layer for regime sensor.

Maintains a 3x3 transition matrix learned from historical candle data.
Provides Bayesian priors to _synthesize() for regime persistence.

States: BALANCE, UP, DOWN
Matrix: P(next_state | current_state)

Usage:
    markov = MarkovRegimeDetector()
    markov.load("config/markov_transition.json")  # after training
    markov.update(return_pct)  # on each candle
    priors = markov.get_prior()  # {"BALANCE": 0.3, "UP": 0.5, "DOWN": 0.2}
"""

import json
import logging
import os
from typing import Dict

logger = logging.getLogger("MarkovRegimeDetector")

STATES = ["BALANCE", "UP", "DOWN"]


class MarkovRegimeDetector:
    """
    First-order Markov chain for regime detection.

    Learns transition probabilities from historical candle returns.
    At each step, updates state probabilities using the chain:
        P(next_state) = Σ P(next_state | prev_state) × P(prev_state)
    """

    def __init__(self):
        self.transitions: Dict[str, Dict[str, float]] = {}
        self.current_state: str = "BALANCE"
        self.prior: Dict[str, float] = {"BALANCE": 1.0, "UP": 0.0, "DOWN": 0.0}
        self._trained = False

    def calibrate(self, closes: list, threshold: float = 0.0005):
        """
        Learn transition matrix from a list of close prices.

        Args:
            closes: List of close prices in chronological order.
            threshold: |return| below this = BALANCE (default 0.05%).
        """
        if len(closes) < 3:
            logger.warning("Not enough candles to calibrate (need >= 3)")
            return

        # Classify each candle into a regime state
        states = self._classify_returns(closes, threshold)

        # Count transitions
        raw = self._count_transitions(states)

        # Normalize to probabilities
        self.transitions = self._normalize(raw)

        # Set uniform prior if not set
        self.prior = {"BALANCE": 1.0 / 3, "UP": 1.0 / 3, "DOWN": 1.0 / 3}

        self._trained = True

        logger.info(f"Calibrated from {len(closes)} candles, {len(states)-1} transitions")
        for s in STATES:
            logger.info(f"  {s}: {self.transitions[s]}")

    def update(self, return_pct: float):
        """
        Update state probabilities with a new candle return.

        Args:
            return_pct: Percentage return of the latest candle
                        (e.g., 0.001 = +0.1%).
        """
        if not self._trained or not self.transitions:
            return

        # Classify the new return
        new_state = self._classify_single(return_pct)

        # Bayesian update: P(new_state) = Σ P(new_state | prev) × P(prev)
        new_prior = {}
        for ns in STATES:
            prob = 0.0
            for ps in STATES:
                prob += self.transitions[ps].get(ns, 0.0) * self.prior[ps]
            new_prior[ns] = prob

        # Normalize (should already be ~1.0, but guard against floating point)
        total = sum(new_prior.values())
        if total > 0:
            for ns in new_prior:
                new_prior[ns] /= total

        self.prior = new_prior
        self.current_state = new_state

    def get_prior(self) -> Dict[str, float]:
        """
        Get current regime probability distribution.

        Returns:
            {"BALANCE": float, "UP": float, "DOWN": float}
        """
        return self.prior.copy()

    def get_dominant(self) -> str:
        """Return the regime with highest probability."""
        return max(self.prior, key=self.prior.get)

    def get_confidence(self) -> float:
        """Return the probability of the dominant regime."""
        return max(self.prior.values())

    def save(self, path: str):
        """Persist transition matrix to JSON."""
        output = {
            "meta": {
                "states": STATES,
                "trained": self._trained,
            },
            "transitions": self.transitions,
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(output, f, indent=2)
        logger.info(f"Saved Markov matrix to {path}")

    def load(self, path: str):
        """Load transition matrix from JSON."""
        with open(path, "r") as f:
            data = json.load(f)
        self.transitions = data["transitions"]
        self._trained = data.get("meta", {}).get("trained", True)
        self.prior = {"BALANCE": 1.0 / 3, "UP": 1.0 / 3, "DOWN": 1.0 / 3}
        logger.info(f"Loaded Markov matrix from {path}")

    # --- Private helpers ---

    def _classify_returns(self, closes: list, threshold: float) -> list:
        """Classify a list of closes into regime states."""
        states = ["BALANCE"]  # First candle has no return
        for i in range(1, len(closes)):
            ret = (closes[i] - closes[i - 1]) / closes[i - 1]
            states.append(self._classify_single(ret, threshold))
        return states

    def _classify_single(self, return_pct: float, threshold: float = 0.0005) -> str:
        """Classify a single return into a regime state."""
        if abs(return_pct) < threshold:
            return "BALANCE"
        return "UP" if return_pct > 0 else "DOWN"

    def _count_transitions(self, states: list) -> Dict[str, Dict[str, int]]:
        """Count transitions between states."""
        raw = {s: {ns: 0 for ns in STATES} for s in STATES}
        for i in range(1, len(states)):
            raw[states[i - 1]][states[i]] += 1
        return raw

    def _normalize(self, raw: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, float]]:
        """Normalize raw counts to probabilities."""
        normalized = {}
        for s in STATES:
            total = sum(raw[s].values())
            normalized[s] = {}
            for ns in STATES:
                normalized[s][ns] = round(raw[s][ns] / total, 4) if total > 0 else 0.0
        return normalized
