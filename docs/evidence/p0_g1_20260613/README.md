# P0 G1 evidence package

Promoted P0 input-substitution audit review package, dated 2026-06-13. The 112 original reports, tables, figures, and manifest files were moved byte-for-byte from `phases/p0-audit/docs/G1_package/` by `DOC-IA-08`. Ten figures referenced from those reports were completed in `DOC-IA-10` as byte-identical copies of `phases/p0-audit/docs/figs/`; the original phase figures remain in place.

- [`REPORT_v6_protect.md`](REPORT_v6_protect.md) — protected report entry
- [`core_table.md`](core_table.md) and [`g1_core_table.csv`](g1_core_table.csv) — core evidence
- [`appendix_tables.md`](appendix_tables.md) — appendix entry
- [`manifest.json`](manifest.json) — package manifest
- [`figs/`](figs/) — package figures

The P0 Docker Compose file mounts this owner directory at the historical container path `/workspace/docs/G1_package`. Existing P0 scripts therefore keep their closed-phase container contract without a duplicate repository copy.
