from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from app.db.engine import get_engine
from app.utils.logging import setup_logging

setup_logging()

logger = logging.getLogger(__name__)
DATA_DIR = Path("data")


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with normalized, snake_case column names."""
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def _coerce_dates(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Coerce the given columns to datetime.date if present."""
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    return df


def _coerce_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Coerce the given columns to numeric if present."""
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_excels() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load and normalize Excel source files for clients, invoices, and items."""
    logger.info("Loading Excel files from %s", DATA_DIR)
    clients = _norm_cols(pd.read_excel(DATA_DIR / "Clients.xlsx"))
    invoices = _norm_cols(pd.read_excel(DATA_DIR / "Invoices.xlsx"))
    items = _norm_cols(pd.read_excel(DATA_DIR / "InvoiceLineItems.xlsx"))

    invoices = _coerce_dates(invoices, ["invoice_date", "due_date"])
    invoices = _coerce_numeric(invoices, ["fx_rate_to_usd"])

    items = _coerce_numeric(items, ["quantity", "unit_price", "tax_rate"])

    return clients, invoices, items


def apply_schema(engine) -> None:
    """Apply SQL schema scripts to the target engine."""
    logger.info("Applying schema from app/db/schema.sql")
    schema_sql = Path("app/db/schema.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        # Run as a multi-statement script safely
        for stmt in schema_sql.split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))


def ingest() -> None:
    """Ingest Excel data into the database with schema creation."""
    logger.info("Starting ingestion")
    engine = get_engine()
    apply_schema(engine)

    clients, invoices, items = load_excels()
    logger.info(
        "Loaded data frames: clients=%s invoices=%s items=%s",
        len(clients),
        len(invoices),
        len(items),
    )

    # Insert in FK order: clients -> invoices -> items
    clients.to_sql("clients", engine, if_exists="append", index=False, method="multi")
    invoices.to_sql("invoices", engine, if_exists="append", index=False, method="multi")
    items.to_sql("invoice_line_items", engine, if_exists="append", index=False, method="multi")

    logger.info("Inserted rows: clients=%s invoices=%s items=%s", len(clients), len(invoices), len(items))
    logger.info("Ingestion complete")


if __name__ == "__main__":
    ingest()
