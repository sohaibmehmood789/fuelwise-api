"""Optional real-provider smoke check. Uses the currently imported dataset."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.test import Client

client = Client()
payload = {'start': 'Los Angeles, CA, USA', 'finish': 'Dallas, TX, USA', 'initial_fuel_price_usd': 3.65}
response = client.post('/api/v1/plan/', json.dumps(payload), content_type='application/json')
data = response.json()
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/live-response.json').write_text(json.dumps(data, indent=2))
print(json.dumps({'status': response.status_code, 'fuel': data.get('fuel'), 'meta': data.get('meta'), 'map_url': data.get('map_url'), 'error': data.get('error')}, indent=2))
if response.status_code != 200:
    sys.exit(1)
repeat = client.post('/api/v1/plan/', json.dumps(payload), content_type='application/json').json()
print('Repeat:', json.dumps(repeat['meta']))
assert repeat['meta']['plan_cache_hit']
assert sum(repeat['meta']['external_calls'].values()) == 0
