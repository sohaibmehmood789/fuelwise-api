import math
import uuid
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from planner.management.commands.import_stations import rows
from planner.models import Dataset, Station


class Command(BaseCommand):
    help = 'Apply an auditable coordinate CSV without changing source fuel quotes or prices.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path')
        parser.add_argument('--replace', action='store_true', help='Allow replacing existing coordinates.')

    def handle(self, *args, **options):
        updates, seen = [], set()
        stations = {s.external_id: s for s in Station.objects.all()}
        try:
            for row in rows(options['csv_path']):
                station_id = row['id']
                if station_id in seen:
                    raise ValueError('duplicate station ID')
                seen.add(station_id)
                if station_id not in stations:
                    raise ValueError(f'unknown station ID {station_id}')
                station = stations[station_id]
                lat, lon = float(row['latitude']), float(row['longitude'])
                if not all(math.isfinite(v) for v in (lat, lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError('invalid coordinates')
                source = row.get('source', 'provided_coordinates')
                if not source or len(source) > 200:
                    raise ValueError('source is empty or too long')
                if station.latitude is not None and not options['replace']:
                    continue
                station.latitude, station.longitude, station.coordinate_source = lat, lon, source
                updates.append(station)
            if not updates:
                raise CommandError('No new coordinates to apply.')
            with transaction.atomic():
                Station.objects.bulk_update(updates, ['latitude', 'longitude', 'coordinate_source'], batch_size=1000)
                dataset = Dataset.objects.get(pk=1)
                dataset.version = uuid.uuid4()
                located = Station.objects.filter(latitude__isnull=False, longitude__isnull=False).count()
                dataset.report = {**dataset.report, 'located_stations': located, 'unlocated_stations': Station.objects.count()-located}
                dataset.save(update_fields=['version', 'report'])
        except (OSError, KeyError, ValueError) as error:
            raise CommandError(str(error))
        self.stdout.write(self.style.SUCCESS(f'Applied {len(updates)} coordinates. Located stations: {located}. Source prices and all quotes preserved.'))
