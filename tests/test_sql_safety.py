import pytest
from app.rag.sql_safety import enforce_sql_safety, SQLSafetyError

def test_blocks_write():
    with pytest.raises(SQLSafetyError):
        enforce_sql_safety("DROP TABLE clients")

def test_adds_limit():
    out = enforce_sql_safety("SELECT * FROM clients")
    assert "LIMIT" in out.upper()

def test_allows_aggregate_without_limit():
    out = enforce_sql_safety("SELECT COUNT(*) AS c FROM clients")
    assert "LIMIT" not in out.upper()
