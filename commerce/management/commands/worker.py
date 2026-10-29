import json
import signal
import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections, OperationalError
from commerce.worker import expire_due, heartbeat, process_one

class Command(BaseCommand):
    help = "Process the durable outbox; no email or external payments are sent."
    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--drain", action="store_true")
        parser.add_argument("--name", default="worker-1")
        parser.add_argument("--interval", type=float, default=1)
    def handle(self, *args, **options):
        stopping = False
        def stop(signum, frame):
            nonlocal stopping
            stopping = True
        if not (options["once"] or options["drain"]):
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
        processed = 0
        while not stopping:
            close_old_connections()
            try:
                heartbeat(options["name"])
                expire_due()
                worked = process_one()
            except OperationalError as error:
                self.stderr.write(json.dumps({"event":"worker_database_unavailable","error":type(error).__name__}))
                if options["once"] or options["drain"]: raise
                time.sleep(min(5, max(.1, options["interval"])))
                continue
            if worked: processed += 1
            if options["once"] or (options["drain"] and not worked): break
            if processed >= 10000 and options["drain"]: break
            if not worked: time.sleep(max(.1, options["interval"]))
        self.stdout.write(json.dumps({"event":"worker_stopped","processed_claims":processed}))
