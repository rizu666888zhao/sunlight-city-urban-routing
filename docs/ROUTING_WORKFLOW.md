# Routing workflow notes

The label-setting experiment expects:

- `od_all_hourly_unity_filtered.csv`
- `unique_hourly_wp_pairs.csv`
- the PostgreSQL road/shadow database

Run `src/routing/final_label_setting_v26_05.py` for one month at a time. Change `DATE_SELECTION` and `OUTPUT_DIR` between runs. The large, previously generated monthly Pareto folders remain in the shared Google Drive archive.

For result analysis, scripts under `src/visualization/` expect the generated monthly folders and may create local cache files. Those caches are ignored by Git.

