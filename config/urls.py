from django.urls import path
from planner import views

urlpatterns = [
    path('', views.index, name='index'),
    path('health/', views.health),
    path('api/v1/plan/', views.plan),
    path('api/v1/maps/<uuid:map_id>/', views.route_map, name='route-map'),
    path('assets/leaflet-1.9.4.js', views.map_asset, {'name': 'leaflet.js'}),
    path('assets/leaflet-1.9.4.css', views.map_asset, {'name': 'leaflet.css'}),
]
