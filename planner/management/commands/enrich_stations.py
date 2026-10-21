import csv
import io
import json
from collections import defaultdict
from pathlib import Path
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from planner.models import FuelQuote, Station
from planner.station_matching import match_elements


class Command(BaseCommand):
    help = 'Create a coordinate companion by matching an OSM fuel extract. Never called by the trip API. Review/apply separately.'

    def add_arguments(self, parser):
        parser.add_argument('--input', help='Existing Overpass JSON extract; no network calls when set.')
        parser.add_argument('--bbox', help='Download a bounded extract: south,west,north,east. Explicit bounds required for network use.')
        parser.add_argument('--endpoint', default='https://overpass.private.coffee/api/interpreter')
        parser.add_argument('--output', required=True, help='Output coordinate companion CSV; review before apply_coordinates.')

    def handle(self, *args, **options):
        output = Path(options['output'])
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            if options['input']:
                data = json.loads(Path(options['input']).read_text())
            else:
                try:
                    south, west, north, east = map(float, (options['bbox'] or '').split(','))
                    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
                        raise ValueError()
                except ValueError:
                    raise CommandError('Provide --input or a valid explicit --bbox south,west,north,east.')
                query = f'[out:json][timeout:55];nwr["amenity"="fuel"]({south},{west},{north},{east});out center tags;'
                self.stdout.write('Downloading one bounded OSM extract (no retries); all matching is offline.')
                response = requests.get(options['endpoint'], params={'data': query}, headers={'User-Agent': settings.PROVIDER_USER_AGENT}, timeout=(5, 65), stream=True)
                response.raise_for_status()
                buffer = io.BytesIO()
                try:
                    for chunk in response.iter_content(65536):
                        buffer.write(chunk)
                        if buffer.tell() > 64 * 1024 * 1024:
                            raise CommandError('Extract exceeds 64 MiB; use a smaller bounding box.')
                finally:
                    response.close()
                raw = buffer.getvalue()
                data = json.loads(raw)
                output.with_suffix('.osm.json').write_bytes(raw)
            if data.get('remark'):
                raise CommandError('Overpass returned an incomplete extract: ' + data['remark'])
            elements = data['elements']
            aliases = defaultdict(set)
            for station_id, raw in FuelQuote.objects.values_list('station__external_id', 'raw'):
                if raw.get('name'):
                    aliases[station_id].add(raw['name'])
            matches, ambiguous = match_elements(list(Station.objects.all()), aliases, elements)
            with output.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=['id', 'latitude', 'longitude', 'source'])
                writer.writeheader()
                writer.writerows({k: row[k] for k in writer.fieldnames} for row in matches)
            report = {'osm_snapshot': data.get('osm3s', {}).get('timestamp_osm_base'), 'element_count': len(elements), 'matched_count': len(matches), 'conflicting_station_ids': ambiguous, 'matches': matches, 'license': 'OpenStreetMap contributors, ODbL 1.0; https://www.openstreetmap.org/copyright', 'limitations': 'Conservative automated identity matching; review results. OSM object centers do not guarantee driveway access. Unmatched records have no invented coordinates.'}
            output.with_suffix('.report.json').write_text(json.dumps(report, indent=2))
            self.stdout.write(self.style.SUCCESS(f'Wrote {len(matches)} coordinate matches. Review {output.with_suffix(".report.json")} before applying; {len(ambiguous)} conflicting identities excluded.'))
        except (OSError, ValueError, KeyError, TypeError, requests.RequestException) as error:
            raise CommandError(f'Coordinate enrichment failed; source station data is unchanged: {type(error).__name__}: {error}')
