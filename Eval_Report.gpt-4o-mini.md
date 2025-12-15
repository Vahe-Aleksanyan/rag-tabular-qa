# Golden Evaluation Report

- Model: `gpt-4o-mini`
- Passed: **8/8**

## Summary

- QUERY tests: **6**
- Freeform used (QUERY): **0/6**
- Freeform repair used (QUERY): **0/6**
- Avg timings (QUERY): total=4.71s, router=4.68s, sql=0.02s

| Test ID | Status | Details |
|---|---|---|
| `list_clients` | ✅ PASS | PASS. mode=deterministic rows=20 total_time=7.35s |
| `clients_uk` | ✅ PASS | PASS. mode=deterministic rows=2 total_time=4.42s |
| `invoices_march_2024` | ✅ PASS | PASS. mode=deterministic rows=2 total_time=3.51s |
| `overdue_invoices` | ✅ PASS | PASS. mode=deterministic rows=9 total_time=4.65s |
| `line_item_count_by_service` | ✅ PASS | PASS. mode=deterministic rows=8 total_time=4.30s |
| `invoice_i1001_line_items` | ✅ PASS | PASS. mode=deterministic rows=3 total_time=4.03s |
| `clarify_missing_year` | ✅ PASS | CLARIFY as expected. (router_time=2.89s) |
| `refuse_out_of_domain` | ✅ PASS | REFUSE as expected. (router_time=1.85s) |