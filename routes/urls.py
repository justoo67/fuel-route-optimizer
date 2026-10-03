from django.urls import path
from routes.views import RoutePlanAPIView, MapPreviewView

urlpatterns = [
    path("api/routes/", RoutePlanAPIView.as_view(), name="api-routes"),
    path("map/", MapPreviewView.as_view(), name="map-preview"),
    path("", MapPreviewView.as_view(), name="home"),
]
