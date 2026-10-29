from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from commerce.models import WorkerHeartbeat
class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--name", default="worker-1")
        parser.add_argument("--max-age", type=int, default=90)
    def handle(self, *args, **options):
        fresh = WorkerHeartbeat.objects.filter(name=options["name"],
            last_seen__gte=timezone.now()-timedelta(seconds=options["max_age"])).exists()
        if not fresh: raise CommandError("worker heartbeat missing or stale")
        self.stdout.write("worker heartbeat fresh")
