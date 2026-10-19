# Preduit — Data & Database Durability

How the serving database is backed up, versioned, seeded, and its scaling limits.

The serving layer is a single SQLite file (`FORECASTER_DB_PATH`, default
`backend-ai/data/forecast.db`; `/data/forecast.db` in containers). Pipeline tables are
rebuilt on every forecast run; **persistent** tables hold user data that must survive
(users, overrides, locks, audit log, season config, backtests, schema_meta).

---

## 1. Backups

Backups use SQLite's **online backup API**, so a consistent snapshot is taken while the app
is running — no downtime. Files are timestamped and pruned by count.

**CLI (recommended for scheduling):**
```bash
python -m preduit_engine.backup create          # snapshot + prune
python -m preduit_engine.backup list            # list snapshots
python -m preduit_engine.backup restore <file>  # restore (stop the app first)
```

**API (admin only):**
- `POST /api/admin/db/backup` — take a backup now.
- `GET  /api/admin/db/backups` — list backups.
- `GET  /api/admin/db/health` — schema version + integrity check.

**Config:**
- `FORECASTER_BACKUP_DIR` (default `<db-dir>/backups`)
- `FORECASTER_BACKUP_KEEP` (default `14` — newest N kept)

**Schedule a daily backup:**
```cron
# 02:30 every day (cron on the host or a sidecar)
30 2 * * *  cd /app && python -m preduit_engine.backup create >> /data/backups/backup.log 2>&1
```
On Azure Container Apps, run the same command as a scheduled Job, or call
`POST /api/admin/db/backup` from a timer. Store backups on the mounted Azure Files share so
they persist off the container.

**Restore:** stop the app (or scale to 0), run `restore <file>`, restart. The current DB is
copied aside to `<db>.pre-restore` first, and the backup is integrity-checked before it
overwrites anything.

---

## 2. Schema versioning & migrations

- `preduit_engine.database.SCHEMA_VERSION` is the current version; it's written to the
  `schema_meta` table on every startup.
- Persistent tables are created with `CREATE TABLE IF NOT EXISTS`, and additive changes use a
  safe `ADD COLUMN`-if-missing migration (`_add_missing_columns`) — e.g. the season
  `budget_band_pct` / `cost_ratio` columns were added this way without data loss.
- `GET /api/admin/db/health` reports the recorded vs expected version and runs
  `PRAGMA integrity_check`, so a deployment can verify the DB before serving traffic.

**When you change the schema:** add the column/table with an idempotent migration and bump
`SCHEMA_VERSION`. Destructive changes (rename/drop/retype) still need a written migration
step — note it in the PR and this file.

---

## 3. Sample / seed data

A fresh install has no source CSV, so the pipeline would raise `FileNotFoundError`. Generate
a small, anonymised, deterministic dataset instead:

```bash
python scripts/make_sample_data.py
# writes backend-ai/data/raw/sample_history.csv (~30 months, 4 clients × 3 products)
export FORECASTER_DATA_FILE=backend-ai/data/raw/sample_history.csv
```

This is enough monthly span for the pipeline to train (SARIMA/CatBoost) and to demo the whole
app. Replace it with the real export (or an ERP sync) for production.

> The sample is generated rather than committed raw so it stays reproducible and obviously
> synthetic — no real customer data lives in the repo.

---

## 4. Scaling limits (SQLite → Postgres)

SQLite is a great fit here: the workload is read-heavy, the pipeline is the only bulk writer,
and the API opens short-lived connections in WAL mode. Limits to watch:

- **Single writer.** SQLite serialises writes. Fine for one pipeline run + interactive
  overrides, but concurrent heavy writers will contend.
- **Single node.** The file must be on storage the app can lock (a mounted volume / Azure
  Files) — not object storage, and not shared across multiple write replicas.

**Migrate to Postgres when** any of these appear: multiple backend replicas needing to write,
many concurrent editors, or DB size / write volume causing lock contention. The data layer is
isolated in `preduit_engine/database.py`, so a Postgres port is contained to that module plus
connection config; the pipeline and API contracts don't change.
