import json
from functools import lru_cache
from django.conf import settings
from django.http import JsonResponse, FileResponse
from django.shortcuts import render
from django.core.cache import cache
from django.core.exceptions import RequestDataTooBig
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from .errors import PlanningError
from .service import plan_trip, validate
from .models import Dataset


@require_GET
def health(request):
    return JsonResponse({'status': 'ok'})


@require_GET
def index(request):
    return render(request, 'planner/index.html', {'dataset': Dataset.objects.first()})


@csrf_exempt
def plan(request):
    # Stateless JSON API: no cookie authentication or session privileges.
    if request.method != 'POST':
        response = JsonResponse({'error': {'code': 'method_not_allowed', 'message': 'Use POST.'}}, status=405)
        response['Allow'] = 'POST'
        return response
    if request.content_type != 'application/json':
        return JsonResponse({'error': {'code': 'unsupported_media_type', 'message': 'Use application/json.'}}, status=415)
    try:
        payload = json.loads(request.body, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except RequestDataTooBig:
        return JsonResponse({'error': {'code': 'request_too_large', 'message': 'JSON body must be at most 16 KiB.'}}, status=413)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': {'code': 'invalid_json', 'message': 'Body must contain valid JSON.'}}, status=400)
    try:
        result = plan_trip(validate(payload))
        return JsonResponse(result)
    except PlanningError as error:
        response = JsonResponse({'error': {'code': error.code, 'message': error.message}}, status=error.status)
        if error.status == 503:
            response['Retry-After'] = '5'
        return response


@require_GET
def route_map(request, map_id):
    result = cache.get('map:' + str(map_id))
    if result is None:
        return JsonResponse({'error': {'code': 'map_expired', 'message': 'Map expired; submit the plan again.'}}, status=404)
    return render(request, 'planner/map.html', {'plan': result, 'basemap': basemap()})


@lru_cache(maxsize=1)
def basemap():
    return json.loads((settings.BASE_DIR / 'data' / 'us_states.geojson').read_text())


@require_GET
def map_asset(request, name):
    # Only two fixed names are registered in URLs; no user-selected paths.
    content_type = 'text/javascript' if name.endswith('.js') else 'text/css'
    response = FileResponse((settings.BASE_DIR / 'planner' / 'static' / 'planner' / name).open('rb'), content_type=content_type)
    response['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response
