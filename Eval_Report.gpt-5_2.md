# Golden Evaluation Report

- Model: `gpt-5.2`
- Passed: **8/8**

## Summary

- QUERY tests: **6**
- Freeform used (QUERY): **0/6**
- Freeform repair used (QUERY): **0/6**
- Avg timings (QUERY): total=2.31s, router=2.28s, sql=0.02s

| Test ID | Status | Details |
|---|---|---|
| `list_clients` | ✅ PASS | PASS. mode=deterministic rows=20 total_time=2.42s |
| `clients_uk` | ✅ PASS | PASS. mode=deterministic rows=2 total_time=3.23s |
| `invoices_march_2024` | ✅ PASS | PASS. mode=deterministic rows=2 total_time=2.21s |
| `overdue_invoices` | ✅ PASS | PASS. mode=deterministic rows=9 total_time=1.92s |
| `line_item_count_by_service` | ✅ PASS | PASS. mode=deterministic rows=8 total_time=2.22s |
| `invoice_i1001_line_items` | ✅ PASS | PASS. mode=deterministic rows=3 total_time=1.85s |
| `clarify_missing_year` | ✅ PASS | CLARIFY as expected. (router_time=1.46s) |
| `refuse_out_of_domain` | ✅ PASS | REFUSE as expected. (router_time=2.32s) |