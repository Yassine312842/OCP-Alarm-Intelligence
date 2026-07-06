"""
Layer 2 storage — embedded DuckDB.

Zero-config so you can run today with no server. The schema mirrors what you'd
create in TimescaleDB (see schema.sql), and the queries are plain SQL, so the
move to TimescaleDB later is mostly a connection-string change.
"""
from __future__ import annotations

import duckdb
import pandas as pd

from src.acquisition.base import AlarmEvent, ProcessSample


class DuckStore:
    def __init__(self, path: str = "ocp_alarms.duckdb"):
        self.con = duckdb.connect(path)
        self._init_schema()

    def _init_schema(self) -> None:
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS process_samples (
                ts TIMESTAMP, tag VARCHAR, value DOUBLE);
            CREATE TABLE IF NOT EXISTS alarms (
                ts TIMESTAMP, tag VARCHAR, level VARCHAR, priority VARCHAR,
                state VARCHAR, value DOUBLE, incident_id VARCHAR);
        """)

    def reset(self) -> None:
        self.con.execute("DELETE FROM process_samples; DELETE FROM alarms;")

    def write_samples(self, samples: list[ProcessSample]) -> None:
        df = pd.DataFrame([s.__dict__ for s in samples])
        self.con.register("df_s", df)
        self.con.execute("INSERT INTO process_samples SELECT ts, tag, value FROM df_s")
        self.con.unregister("df_s")

    def write_alarms(self, alarms: list[AlarmEvent]) -> None:
        df = pd.DataFrame([a.__dict__ for a in alarms])
        self.con.register("df_a", df)
        self.con.execute("""INSERT INTO alarms
            SELECT ts, tag, level, priority, state, value, incident_id FROM df_a""")
        self.con.unregister("df_a")

    def alarms_df(self) -> pd.DataFrame:
        return self.con.execute("SELECT * FROM alarms ORDER BY ts").df()

    def samples_df(self) -> pd.DataFrame:
        return self.con.execute("SELECT * FROM process_samples ORDER BY ts").df()

    def query(self, sql: str) -> pd.DataFrame:
        return self.con.execute(sql).df()
