import logging
from django.shortcuts import render
from django.views import View
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from routes.serializers import RouteRequestSerializer
from routes.services.fuel_optimizer import InfeasibleRouteError
from routes.services.route_planner import RoutePlanner

logger = logging.getLogger(__name__)


class RoutePlanAPIView(APIView):
    """
    POST /api/routes/
    Calculates driving route, identifies optimal fuel stops along the corridor,
    and returns route geometry and total fuel expenditure.
    """

    def post(self, request, *args, **kwargs):
        serializer = RouteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid request parameters", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start = serializer.validated_data["start"]
        destination = serializer.validated_data["destination"]
        corridor_radius = serializer.validated_data.get("corridor_radius_miles", 10.0)

        try:
            plan_result = RoutePlanner.plan(
                start_location=start,
                destination_location=destination,
                corridor_radius_miles=corridor_radius,
            )
            return Response(plan_result, status=status.HTTP_200_OK)

        except ValueError as ve:
            return Response(
                {"error": "Location or routing error", "message": str(ve)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except InfeasibleRouteError as ire:
            return Response(
                {
                    "error": "Infeasible route under vehicle constraints",
                    "message": str(ire),
                    "vehicle_constraints": {
                        "max_range_miles": 500.0,
                        "mpg": 10.0,
                        "tank_capacity_gallons": 50.0,
                    },
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except RuntimeError as re:
            logger.error(f"Upstream service error during route planning: {re}")
            return Response(
                {"error": "Upstream service unavailable", "message": str(re)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as e:
            logger.exception("Unexpected error during route planning")
            return Response(
                {"error": "Internal server error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class MapPreviewView(View):
    """
    Renders an interactive Leaflet map interface for visual inspection
    and Loom demonstration.
    """

    def get(self, request, *args, **kwargs):
        return render(request, "map_preview.html")
