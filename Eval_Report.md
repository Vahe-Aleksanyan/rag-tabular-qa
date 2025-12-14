# Golden Evaluation Report

Passed: **8/8**

| Test ID | Status | Details |
|---|---|---|
| `list_clients` | ✅ PASS | PASS. mode=deterministic rows=20 total_time=9.10s |
| `clients_uk` | ✅ PASS | PASS. mode=deterministic rows=2 total_time=4.84s |
| `invoices_march_2024` | ✅ PASS | PASS. mode=deterministic rows=2 total_time=5.67s |
| `overdue_invoices` | ✅ PASS | PASS. mode=deterministic rows=9 total_time=12.19s |
| `line_item_count_by_service` | ✅ PASS | PASS. mode=deterministic rows=8 total_time=9.85s |
| `invoice_i1001_line_items` | ✅ PASS | PASS. mode=deterministic rows=3 total_time=8.54s |
| `clarify_missing_year` | ✅ PASS | CLARIFY as expected. (router_time=5.38s) |
| `refuse_out_of_domain` | ✅ PASS | REFUSE as expected. (router_time=7.04s) |