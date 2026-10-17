import logging
from datetime import datetime, timedelta, timezone

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import geocoding, planner
from .services.geo import haversine_mi
from .services.routing import RoutingError
from .services.weather import WeatherError

log = logging.getLogger(__name__)


class PlanTripSerializer(serializers.Serializer):
    origin_lat = serializers.FloatField(min_value=-90, max_value=90)
    origin_lon = serializers.FloatField(min_value=-180, max_value=180)
    dest_lat = serializers.FloatField(min_value=-90, max_value=90)
    dest_lon = serializers.FloatField(min_value=-180, max_value=180)
    departure_iso = serializers.DateTimeField(required=False)
    load_weight_lb = serializers.FloatField(min_value=0, max_value=80_000)
    sample_miles = serializers.ChoiceField(choices=[10, 25, 50], default=25)

    def validate_departure_iso(self, value):
        now = datetime.now(timezone.utc)
        # Open-Meteo forecasts reach 16 days; we need departure + 48 h + trip.
        if value > now + timedelta(days=13):
            raise serializers.ValidationError("Departure must be within the next 13 days.")
        if value < now - timedelta(days=2):
            raise serializers.ValidationError("Departure cannot be more than 2 days in the past.")
        return value

    def validate(self, attrs):
        miles = haversine_mi(attrs["origin_lat"], attrs["origin_lon"], attrs["dest_lat"], attrs["dest_lon"])
        if miles < 0.5:
            raise serializers.ValidationError("Origin and destination are the same place.")
        if miles > 3500:
            raise serializers.ValidationError("Trip is too long (straight-line distance > 3,500 mi).")
        return attrs


class PlanTripView(APIView):
    """POST /api/plan-trip - 3 routes with checkpoints, weather, risk and a recommendation."""

    def post(self, request):
        ser = PlanTripSerializer(data=request.data)
        if not ser.is_valid():
            return Response({"error": "Invalid input", "details": ser.errors}, status=400)
        d = ser.validated_data
        try:
            result = planner.plan_trip(
                origin=[d["origin_lat"], d["origin_lon"]],
                dest=[d["dest_lat"], d["dest_lon"]],
                departure=d.get("departure_iso") or datetime.now(timezone.utc),
                load_lb=d["load_weight_lb"],
                sample_miles=int(d["sample_miles"]),
            )
        except (RoutingError, WeatherError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception:  # noqa: BLE001 - never leak a stack trace to the client
            log.exception("plan-trip failed")
            return Response({"error": "Unexpected server error while planning trip."}, status=500)
        return Response(result)


class CorridorWeatherView(APIView):
    """GET /api/corridor-weather?trip_id=...&route_id=... - heatmap frames of a planned trip."""

    def get(self, request):
        trip_id = request.query_params.get("trip_id")
        route_id = request.query_params.get("route_id")
        if not trip_id:
            return Response({"error": "trip_id is required"}, status=400)
        if route_id is not None and not route_id.isdigit():
            return Response({"error": "route_id must be an integer"}, status=400)
        data = planner.get_corridor(trip_id, route_id)
        if data is None:
            return Response({"error": "Trip or route not found (results expire after 1 h)."}, status=404)
        return Response(data)


class GeocodeView(APIView):
    """GET /api/geocode?q=...&autocomplete=1 - address search / type-ahead."""

    def get(self, request):
        q = request.query_params.get("q", "")
        autocomplete = request.query_params.get("autocomplete") in ("1", "true")
        return Response({"results": geocoding.search(q, autocomplete=autocomplete)})


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok"})
