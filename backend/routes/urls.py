from django.urls import path

from . import views

urlpatterns = [
    path("health", views.HealthView.as_view()),
    path("geocode", views.GeocodeView.as_view()),
    path("plan-trip", views.PlanTripView.as_view()),
    path("corridor-weather", views.CorridorWeatherView.as_view()),
]
