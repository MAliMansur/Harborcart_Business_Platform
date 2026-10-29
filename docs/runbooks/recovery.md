# Runbook: backup and isolated recovery
A backup is evidence only after restoration and validation. Preserve the original database. Never test restore by overwriting the only working copy.

## SQLite gate
```bash
make reconcile
make recovery
```
The command uses SQLite's online backup API, restores into a second new file under .local/recovery/, checks database integrity, foreign keys and critical table counts, and records a SHA-256 checksum. It does not replace the live database or prove PostgreSQL recovery.

For deeper validation, stop your local web/worker, choose the exact restored path printed in the JSON evidence, then run a read-only reconciliation against that copy:
```bash
SQLITE_PATH="$PWD/.local/recovery/YOUR-RECORDED-restored.sqlite3" python manage.py reconcile
```
Do not paste that placeholder unchanged. Keep the original file. Record the actual backup/restore durations from your execution; no RPO/RTO is claimed by this command.

## PostgreSQL gate — supplied, not executed here
Create a private backup directory and a timestamped custom-format dump:
```bash
mkdir -p .local/backups
chmod 700 .local/backups
backup_file=".local/backups/harborcart-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T db pg_dump -U hc_owner -d harborcart --format=custom --no-owner --no-acl > "$backup_file"
test -s "$backup_file"
sha256sum "$backup_file"
docker compose exec -T db pg_restore --list < "$backup_file"
```
Only a successful dump command plus nonempty output is a candidate backup. Abort if pg_dump fails.

Restore into a new uniquely named database; do not use --clean on the active database:
```bash
restore_db="hc_restore_$(date -u +%Y%m%d%H%M%S)"
docker compose exec -T db createdb -U hc_owner "$restore_db"
docker compose exec -T db pg_restore -U hc_owner -d "$restore_db" --exit-on-error --no-owner --no-acl < "$backup_file"
docker compose exec -T db psql -U hc_owner -d "$restore_db" -c "SELECT status, count(*) FROM commerce_order GROUP BY status;"
```
In an isolated application process, point DATABASE_URL to that restored database using a securely supplied connection string, run reconciliation and a controlled purchase journey. Do not put passwords in shell history or expose the restored environment publicly. Record schema version, row counts, order/invoice/payment relationships, stock and credit, elapsed restore time and what transactions could be missing.

Keep the restored database until evidence is reviewed. Its later deletion is an explicitly authorized cleanup action. Cloud recovery additionally needs encrypted backups, retention policy, RDS PITR, separate failure domain and a tested connection cutover/rollback plan.
