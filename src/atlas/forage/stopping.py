"""Stopping criteria (SCORING.md §4). The loop halts when any fires.

    a. budget      — papers / USD / minutes for the mode
    b. saturation  — EMA of new-information falls below ratio·max for `patience` papers
    c. exhausted   — no pending paper above the read threshold
    d. hard fail   — three consecutive ingestion failures

`new_info = 1·new_claims + 2·new_contradictions + 3·new_concepts`. Contradictions and
concepts are 0 until Phases 4-5, so saturation currently rides on new claims alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from atlas.config_files import mode_budget, scoring


@dataclass
class Stopper:
    mode: str
    ema: float = 0.0
    max_ema: float = 0.0
    below_streak: int = 0
    fail_streak: int = 0
    series: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        cfg = scoring()["stopping"]
        self._min_papers = int(cfg["min_papers"])
        self._alpha = float(cfg["alpha"])
        self._ratio = float(cfg["saturation_ratio"])
        self._patience = int(cfg["saturation_patience"])
        self.read_below_score = float(cfg["read_below_score"])
        weights = cfg.get("new_info_weights", {"claims": 1, "contradictions": 2, "concepts": 3})
        self._w_claims = float(weights["claims"])
        self._w_contra = float(weights["contradictions"])
        self._w_concepts = float(weights["concepts"])
        budget = mode_budget(self.mode)
        self.max_papers = int(budget["papers"])
        self.max_usd = float(budget["max_usd"])
        self.max_seconds = float(budget["max_minutes"]) * 60.0

    def record_failure(self) -> str | None:
        self.fail_streak += 1
        if self.fail_streak >= 3:
            return "hard_failure: 3 consecutive ingestion failures"
        return None

    def record_paper(
        self, *, new_claims: int, new_contradictions: int = 0, new_concepts: int = 0
    ) -> float:
        self.fail_streak = 0
        new_info = (
            self._w_claims * new_claims
            + self._w_contra * new_contradictions
            + self._w_concepts * new_concepts
        )
        self.ema = self._alpha * new_info + (1.0 - self._alpha) * self.ema
        self.max_ema = max(self.max_ema, self.ema)
        self.series.append(round(self.ema, 4))
        return new_info

    def check(
        self, *, papers_read: int, total_usd: float, elapsed_s: float, pending_above: int
    ) -> str | None:
        if papers_read >= self.max_papers:
            return f"budget: {papers_read} papers read"
        if total_usd >= self.max_usd:
            return f"budget: ${total_usd:.2f} spent"
        if elapsed_s >= self.max_seconds:
            return f"budget: {elapsed_s / 60:.0f} minutes elapsed"
        if pending_above == 0:
            return "frontier exhausted"
        if papers_read >= self._min_papers and self.max_ema > 0.0:
            if self.ema < self._ratio * self.max_ema:
                self.below_streak += 1
                if self.below_streak >= self._patience:
                    return (
                        f"saturation: EMA {self.ema:.2f} < "
                        f"{self._ratio}·{self.max_ema:.2f} for {self._patience} papers"
                    )
            else:
                self.below_streak = 0
        return None
