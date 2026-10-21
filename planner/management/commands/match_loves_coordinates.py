import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from planner.models import FuelQuote, Station
from planner.station_matching import normalized, store_number


class Command(BaseCommand):
    help = "Build a coordinate companion from an offline export of Love's official location directory. Prices always remain from the assessment CSV."

    def add_arguments(self, parser):
        parser.add_argument('input_json')
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        try:
            data = json.loads(Path(options['input_json']).read_text())
            stores = data['stores']
            stations = {s.external_id: s for s in Station.objects.all()}
            identities = defaultdict(set)
            for station_id, raw in FuelQuote.objects.values_list('station__external_id', 'raw'):
                name = raw.get('name', '')
                if normalized(name).startswith('loves') and (number := store_number(name)):
                    station = stations[station_id]
                    identities[(number, station.state, normalized(station.city))].add(station_id)
            matches = {}
            conflicts = set()
            for store in stores:
                number = str(int(store['number']))
                key = (number, store['state'], normalized(store['city']))
                ids = identities.get(key, set())
                if len(ids) != 1:
                    continue
                station_id = next(iter(ids))
                lat, lon = float(store['latitude']), float(store['longitude'])
                if not all(math.isfinite(v) for v in (lat, lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError('invalid source coordinates')
                row = {'id': station_id, 'latitude': lat, 'longitude': lon, 'source': f'https://www.loves.com/locations/{number}'}
                if station_id in matches and (matches[station_id]['latitude'], matches[station_id]['longitude']) != (lat, lon):
                    conflicts.add(station_id)
                matches[station_id] = row
            output = Path(options['output'])
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=['id', 'latitude', 'longitude', 'source'])
                writer.writeheader()
                writer.writerows(matches[k] for k in sorted(matches) if k not in conflicts)
            report = {'source': 'https://www.loves.com/locations', 'source_endpoint': 'https://www.loves.com/api/fetch_stores', 'input_records': len(stores), 'matched_stations': len(matches)-len(conflicts), 'matching_rule': 'Exact chain + store number + state + normalized city; unique assessment station ID only.', 'conflicts_excluded': sorted(conflicts), 'prices': 'No live chain prices imported. All prices come from the supplied assessment CSV.', 'coverage': 'Partial: only confidently matched Love\'s stations. Other CSV stations remain unlocated.', 'coordinates': 'Official published location point; road snapping does not guarantee station driveway access.'}
            output.with_suffix('.report.json').write_text(json.dumps(report, indent=2))
            self.stdout.write(self.style.SUCCESS(f'Wrote {report["matched_stations"]} exact chain/store/city/state matches; excluded {len(conflicts)} conflicts.'))
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise CommandError(str(error))
