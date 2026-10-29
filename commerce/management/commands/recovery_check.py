"""Local SQLite backup/restore rehearsal; does not replace the live database."""
import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

TABLES=("commerce_company","commerce_order","commerce_orderitem","commerce_invoice",
        "commerce_stock","commerce_payment","commerce_refund","commerce_outboxevent","commerce_auditevent")
def counts(db):
    queries = {
        'commerce_company': 'SELECT count(*) FROM "commerce_company"',
        'commerce_order': 'SELECT count(*) FROM "commerce_order"',
        'commerce_orderitem': 'SELECT count(*) FROM "commerce_orderitem"',
        'commerce_invoice': 'SELECT count(*) FROM "commerce_invoice"',
        'commerce_stock': 'SELECT count(*) FROM "commerce_stock"',
        'commerce_payment': 'SELECT count(*) FROM "commerce_payment"',
        'commerce_refund': 'SELECT count(*) FROM "commerce_refund"',
        'commerce_outboxevent': 'SELECT count(*) FROM "commerce_outboxevent"',
        'commerce_auditevent': 'SELECT count(*) FROM "commerce_auditevent"',
    }
    return {table:db.execute(query).fetchone()[0] for table,query in queries.items()}
class Command(BaseCommand):
    help="Back up SQLite and restore into an isolated file; verify integrity and business table counts."
    def handle(self,**options):
        if settings.ENV=="production" or connection.vendor!="sqlite":
            raise CommandError("Only local SQLite is supported here. Use the PostgreSQL recovery runbook.")
        source=Path(connection.settings_dict["NAME"])
        if not source.is_file(): raise CommandError("Create the local database first.")
        folder=settings.BASE_DIR/".local"/"recovery"
        folder.mkdir(parents=True,exist_ok=True);os.chmod(folder,0o700)
        tag=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:6]
        backup=folder/(tag+"-backup.sqlite3");restored=folder/(tag+"-restored.sqlite3")
        with sqlite3.connect(source.as_uri()+"?mode=ro",uri=True) as live,sqlite3.connect(backup) as copy:
            live.backup(copy)
        with sqlite3.connect(backup) as copy,sqlite3.connect(restored) as target:
            before=counts(copy)
            copy.backup(target)
        with sqlite3.connect(restored) as target:
            integrity=target.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_keys=target.execute("PRAGMA foreign_key_check").fetchall()
            after=counts(target)
        passed=integrity=="ok" and not foreign_keys and before==after
        report={"environment":"local-sqlite","timestamp":datetime.now(timezone.utc).isoformat(),
            "backup":backup.name,"restored":restored.name,"integrity":integrity,
            "foreign_key_violations":len(foreign_keys),"table_counts":after,
            "counts_match":before==after,"backup_sha256":hashlib.sha256(backup.read_bytes()).hexdigest(),
            "passed":passed,"live_database_replaced":False,"postgresql_recovery_proven":False}
        (folder/(tag+"-evidence.json")).write_text(json.dumps(report,indent=2)+"\n")
        self.stdout.write(json.dumps(report,indent=2))
        if not passed: raise CommandError("Restore validation failed.")
