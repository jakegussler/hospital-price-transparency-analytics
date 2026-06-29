-- CSV code_N / code_N_type columns unpivoted to one row per (row, code ordinal).
-- Materialized once as a table so val__code_violations does not re-run the
-- unpivot self-join (the dominant temp-spill driver for the wide CSV
-- hospitals) for both the code grain and the "rows without codes" anti-join.
-- See docs/cleanup.md.
{{ hpt_csv_code_unpivot("select * from " ~ hpt_scoped_ref('stg_bronze__csv_charge_rows')) }}
