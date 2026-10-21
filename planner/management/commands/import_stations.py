import csv
import hashlib
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from planner.locations import STATES
from planner.models import Dataset, FuelQuote, Station

CANADIAN_PROVINCES = set('AB BC MB NB NL NS NT NU ON PE QC SK YT'.split())
ALIASES = {'opis truckstop id': 'id', 'truckstop name': 'name', 'retail price': 'price', 'rack id': 'rack_id', 'lat': 'latitude', 'lon': 'longitude', 'lng': 'longitude', 'price_per_gallon': 'price', 'station_id': 'id'}


def rows(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise CommandError('CSV has no header.')
        normalized = [ALIASES.get(k.strip().lower(), k.strip().lower()) for k in reader.fieldnames]
        if len(normalized) != len(set(normalized)):
            raise CommandError('Duplicate CSV columns after normalization.')
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise CommandError(f'Malformed CSV row at line {reader.line_num}.')
            yield {ALIASES.get(k.strip().lower(), k.strip().lower()): v.strip() for k, v in row.items()}


class Command(BaseCommand):
    help = 'Atomically import fuel CSV. Explicit flags support USA filtering, repeated quotes, and pending coordinates. No network calls.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path')
        parser.add_argument('--coordinates', help='CSV with id,latitude,longitude, optional source; join using station ID.')
        parser.add_argument('--usa-only', action='store_true', help='Exclude Canadian province rows, reporting their count.')
        parser.add_argument('--duplicate-policy', choices=['error', 'min-price'], default='error', help='min-price retains every quote and uses the minimum quoted price at each station.')
        parser.add_argument('--allow-unlocated', action='store_true', help='Retain stations without coordinates; exclude them from routing until enriched.')

    def handle(self, *args, **options):
        try:
            coordinates = {}
            if options['coordinates']:
                for row in rows(options['coordinates']):
                    if row['id'] in coordinates:
                        raise CommandError('Duplicate ID in coordinates CSV.')
                    coordinates[row['id']] = row
            stations, quote_rows = {}, []
            total_rows = skipped = 0
            for line, row in enumerate(rows(options['csv_path']), 2):
                total_rows += 1
                try:
                    state = row['state'].upper()
                    if options['usa_only'] and state in CANADIAN_PROVINCES:
                        skipped += 1
                        continue
                    if state not in STATES:
                        raise ValueError('state must be a USA postal abbreviation; use --usa-only to exclude Canadian records')
                    station_id = row['id']
                    if not station_id or len(station_id) > 100:
                        raise ValueError('missing or overlong station ID')
                    if station_id in stations and options['duplicate_policy'] == 'error':
                        raise ValueError('duplicate station ID; use --duplicate-policy min-price to retain multiple quotes')
                    price = Decimal(row['price'])
                    if not price.is_finite() or not 0 < price < 100:
                        raise ValueError('price must be finite and strictly between 0 and 100')
                    if price != price.quantize(Decimal('.00000001')):
                        raise ValueError('price must have at most eight decimal places')
                    geo = coordinates.get(station_id, row)
                    lat, lon = geo.get('latitude', ''), geo.get('longitude', '')
                    if not lat and not lon and options['allow_unlocated']:
                        lat = lon = None
                        coordinate_source = ''
                    else:
                        if not lat or not lon:
                            raise ValueError('missing latitude/longitude; use --coordinates or explicitly retain unresolved records with --allow-unlocated')
                        lat, lon = Decimal(lat), Decimal(lon)
                        if not all(v.is_finite() for v in (lat, lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                            raise ValueError('coordinates out of range or non-finite')
                        lat, lon = float(lat), float(lon)
                        coordinate_source = geo.get('source') or 'provided_coordinates'
                    for field, maximum in [('name', 200), ('address', 300), ('city', 100)]:
                        if not row[field] or len(row[field]) > maximum:
                            raise ValueError(f'{field} is empty or too long')
                    if len(row.get('rack_id', '')) > 100:
                        raise ValueError('rack_id too long')
                    if station_id in stations:
                        existing = stations[station_id]
                        if (existing.city.casefold(), existing.state) != (row['city'].casefold(), state):
                            raise ValueError('same station ID refers to different cities/states')
                        if price < existing.price:
                            existing.price, existing.name, existing.address = price, row['name'], row['address']
                    else:
                        stations[station_id] = Station(external_id=station_id, name=row['name'], address=row['address'], city=row['city'], state=state, latitude=lat, longitude=lon, coordinate_source=coordinate_source, price=price)
                    quote_rows.append((station_id, line, row))
                except (KeyError, ValueError, InvalidOperation) as error:
                    raise CommandError(f'CSV line {line}: {error}. Required: id,name,address,city,state,price; location: latitude,longitude or --coordinates.')
            if not stations:
                raise CommandError('No USA stations found; existing dataset was preserved.')
            located = sum(s.latitude is not None for s in stations.values())
            report = {'source_sha256': hashlib.sha256(Path(options['csv_path']).read_bytes()).hexdigest(), 'source_rows': total_rows, 'excluded_non_usa_rows': skipped, 'usa_quote_rows': len(quote_rows), 'unique_usa_stations': len(stations), 'duplicate_quote_rows': len(quote_rows)-len(stations), 'located_stations': located, 'unlocated_stations': len(stations)-located, 'price_policy': options['duplicate_policy'], 'price_decimal_places': 8}
            with transaction.atomic():
                Station.objects.all().delete()
                Station.objects.bulk_create(stations.values(), batch_size=1000)
                station_ids = dict(Station.objects.values_list('external_id', 'pk'))
                FuelQuote.objects.bulk_create([FuelQuote(station_id=station_ids[station_id], source_row=line, rack_id=row.get('rack_id', ''), price=Decimal(row['price']), raw=row) for station_id, line, row in quote_rows], batch_size=1000)
                Dataset.objects.update_or_create(pk=1, defaults={'version': uuid.uuid4(), 'source': Path(options['csv_path']).name, 'report': report})
            self.stdout.write(self.style.SUCCESS(f'Imported {len(stations)} USA stations and {len(quote_rows)} quotes; excluded {skipped} non-USA rows. Located: {located}; pending coordinates: {len(stations)-located}.'))
        except OSError as error:
            raise CommandError(str(error))
