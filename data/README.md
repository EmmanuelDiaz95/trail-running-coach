# data/ — Runtime Data (gitignored)

This directory stores cached Garmin data and generated reports. Contents are not committed to git.

## activities/

Cached raw JSON responses from Garmin Connect, one file per sync call:

```
2026-03-02_2026-03-08.json   # Week 1 activities
2026-01-01_2026-01-31.json   # January full month
```

These files are created by `scripts/sync.py` and read by `scripts/report.py` to avoid hitting Garmin's API repeatedly. Delete a file and re-sync to refresh.

## reports/

Generated markdown weekly reports:

```
week_01.md
week_02.md
...
```

Created by `scripts/report.py`. Each report contains the planned vs actual comparison table, compliance score, activity details, and any triggered alerts for that week.
