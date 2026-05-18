"""Lightweight in-memory metrics registry."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MetricsRegistry:
    counters: dict[str, int] = field(default_factory=dict)
    timings_ms: dict[str, list[float]] = field(default_factory=dict)

    def increment(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def record_timing(self, name: str, duration_ms: float) -> None:
        self.timings_ms.setdefault(name, []).append(float(duration_ms))


metrics_registry = MetricsRegistry()
