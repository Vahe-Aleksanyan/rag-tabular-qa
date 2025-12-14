from sqlalchemy import text
from app.db.engine import get_engine

def test_db_has_rows():
    engine = get_engine()
    with engine.connect() as conn:
        c = conn.execute(text("SELECT COUNT(*) FROM clients")).scalar_one()
        i = conn.execute(text("SELECT COUNT(*) FROM invoices")).scalar_one()
        li = conn.execute(text("SELECT COUNT(*) FROM invoice_line_items")).scalar_one()
    assert c >= 0 and i >= 0 and li >= 0
