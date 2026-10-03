from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        required=True,
        max_length=255,
        help_text="Starting location (e.g. 'Chicago, IL' or '41.8781, -87.6298')",
    )
    destination = serializers.CharField(
        required=True,
        max_length=255,
        help_text="Destination location (e.g. 'Dallas, TX' or '32.7767, -96.7970')",
    )
    corridor_radius_miles = serializers.FloatField(
        required=False,
        default=10.0,
        min_value=1.0,
        max_value=50.0,
        help_text="Search corridor radius in miles along route (default: 10.0)",
    )
