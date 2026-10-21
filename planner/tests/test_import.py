import io
import tempfile
import uuid
from pathlib import Path
from django.core.management import call_command, CommandError
from django.test import TestCase
from planner.models import Dataset, FuelQuote, Station
from django.conf import settings
from planner.locations import STATES


class ImportTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'stations.csv'

    def run_import(self, content, **kwargs):
        self.path.write_text(content)
        call_command('import_stations', str(self.path), stdout=io.StringIO(), **kwargs)

    def test_imports_assignment_headers_with_companion_coordinates(self):
        coordinates = Path(self.temp.name) / 'coordinates.csv'
        coordinates.write_text('id,latitude,longitude\n123,35,-100\n')
        self.run_import('OPIS Truckstop ID,Truckstop Name,Address,City,State,Retail Price\n123,Station,Main Road,Amarillo,TX,3.1990\n', coordinates=str(coordinates))
        self.assertEqual(Station.objects.get().external_id, '123')
        self.assertEqual(str(Station.objects.get().price), '3.19900000')
        self.assertEqual(Dataset.objects.count(), 1)

    def test_bad_rows_preserve_previous_dataset(self):
        self.run_import('id,name,address,city,state,price,latitude,longitude\n1,Station,Main Road,Test,TX,3.1,35,-100\n')
        version = Dataset.objects.get().version
        for value in ['NaN', '-1', '0', '3.123456789', '999']:
            with self.subTest(value=value), self.assertRaises(CommandError):
                self.run_import(f'id,name,address,city,state,price,latitude,longitude\n2,Station,Main Road,Test,TX,{value},35,-100\n')
            self.assertEqual(Station.objects.get().external_id, '1')
            self.assertEqual(Dataset.objects.get().version, version)

    def test_missing_coordinates_are_actionable(self):
        with self.assertRaisesMessage(CommandError, '--coordinates'):
            self.run_import('id,name,address,city,state,price\n1,Station,Main Road,Test,TX,3.1\n')

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaisesMessage(CommandError, 'duplicate'):
            self.run_import('id,name,address,city,state,price,latitude,longitude\n1,Station,Main Road,Test,TX,3.1,35,-100\n1,Station,Main Road,Test,TX,3.2,35,-100\n')

    def test_actual_assessment_file_is_imported_without_loss_of_precision(self):
        call_command('import_stations', str(settings.BASE_DIR / 'data' / 'fuel-prices-for-be-assessment.csv'), usa_only=True, duplicate_policy='min-price', allow_unlocated=True, stdout=io.StringIO())
        self.assertEqual(Station.objects.count(), 6626)
        self.assertEqual(FuelQuote.objects.count(), 7531)
        report = Dataset.objects.get().report
        self.assertEqual(report['source_rows'], 8151)
        self.assertEqual(report['excluded_non_usa_rows'], 620)
        self.assertEqual(report['duplicate_quote_rows'], 905)
        self.assertEqual(report['unlocated_stations'], 6626)
        self.assertEqual(str(Station.objects.get(external_id='7').price), '3.00733333')
        station = Station.objects.get(external_id='105')
        self.assertEqual(station.quotes.count(), 6)
        self.assertEqual(station.price, min(station.quotes.values_list('price', flat=True)))
        self.assertFalse(Station.objects.exclude(state__in=STATES).exists())

    def test_coordinates_can_be_applied_without_changing_quotes(self):
        self.run_import('id,name,address,city,state,price\n1,Station,Main Road,Test,TX,3.00733333\n', allow_unlocated=True)
        old_version = Dataset.objects.get().version
        self.path.write_text('id,latitude,longitude,source\n1,35,-100,test_verified_source\n')
        call_command('apply_coordinates', str(self.path), stdout=io.StringIO())
        station = Station.objects.get()
        self.assertEqual((station.latitude, station.longitude), (35, -100))
        self.assertEqual(station.coordinate_source, 'test_verified_source')
        self.assertEqual(str(station.price), '3.00733333')
        self.assertEqual(str(station.quotes.get().price), '3.00733333')
        self.assertNotEqual(Dataset.objects.get().version, old_version)
        self.assertEqual(Dataset.objects.get().report['unlocated_stations'], 0)

    def test_assessment_bootstrap_with_bundled_coordinates(self):
        call_command('import_stations', str(settings.BASE_DIR / 'data' / 'fuel-prices-for-be-assessment.csv'), coordinates=str(settings.BASE_DIR / 'data' / 'station-coordinates.csv'), usa_only=True, duplicate_policy='min-price', allow_unlocated=True, stdout=io.StringIO())
        report = Dataset.objects.get().report
        self.assertEqual(report['located_stations'], 518)
        self.assertEqual(report['unlocated_stations'], 6108)
        self.assertEqual(FuelQuote.objects.count(), 7531)
        self.assertEqual(str(Station.objects.get(external_id='63855').price), '3.27900000')

    def test_official_directory_match_uses_identity_and_never_live_prices(self):
        self.run_import('id,name,address,city,state,price\n1,LOVES TRAVEL STOP #123,I-10 Exit 1,Test,TX,3.00733333\n', allow_unlocated=True)
        source = Path(self.temp.name) / 'directory.json'
        import json
        source.write_text(json.dumps({'stores': [{'number': 123, 'state': 'TX', 'city': 'Test', 'latitude': 35, 'longitude': -100, 'fuelPrices': {'diesel': 99}}]}))
        output = Path(self.temp.name) / 'coordinates.csv'
        call_command('match_loves_coordinates', str(source), output=str(output), stdout=io.StringIO())
        call_command('apply_coordinates', str(output), stdout=io.StringIO())
        station = Station.objects.get()
        self.assertEqual(station.coordinate_source, 'https://www.loves.com/locations/123')
        self.assertEqual(str(station.price), '3.00733333')
        self.assertEqual(str(station.quotes.get().price), '3.00733333')
