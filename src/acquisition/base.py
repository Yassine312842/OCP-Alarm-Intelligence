"""
Layer 1 — Acquisition.

`DataSource` is the seam that keeps the rest of the platform independent of
where data comes from. Today it's `SyntheticDataSource`; later you implement
`PIHistorianDataSource` / `OpcUaDataSource` with the SAME two methods and
nothing downstream changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ProcessSample:
    ts: datetime
    tag: str
    value: float


@dataclass
class AlarmEvent:
    ts: datetime
    tag: str
    level: str          # LO / LOLO / HI / HIHI
    priority: str       # LOW / HIGH / CRITICAL
    state: str          # ACTIVE / CLEARED
    value: float
    incident_id: str | None = None   # ground-truth link (None in real data)


class DataSource(ABC):
    """Any data source yields two streams: continuous samples and discrete
    alarm events, both already timestamped."""

    @abstractmethod
    def process_samples(self) -> list[ProcessSample]:
        ...

    @abstractmethod
    def alarm_events(self) -> list[AlarmEvent]:
        ...
