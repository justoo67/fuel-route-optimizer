from django.db import models


class TruckStop(models.Model):
    """
    Normalized physical truck stop facility.
    Each OPIS Truckstop ID corresponds to a unique physical travel center location.
    """
    opis_id = models.IntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=10, db_index=True)
    country = models.CharField(max_length=10, default="US")
    latitude = models.FloatField(db_index=True)
    longitude = models.FloatField(db_index=True)

    # Active retail price used for route optimization (median across observations)
    retail_price = models.DecimalField(max_digits=7, decimal_places=4)
    min_price = models.DecimalField(max_digits=7, decimal_places=4)
    max_price = models.DecimalField(max_digits=7, decimal_places=4)
    price_count = models.IntegerField(default=1)
    rack_ids = models.CharField(max_length=100, blank=True)

    # Geocoding provenance
    geocode_source = models.CharField(max_length=50, default="highway_exit_exact")
    confidence = models.CharField(max_length=20, default="high")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["latitude", "longitude"]),
            models.Index(fields=["state", "city"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.city}, {self.state} (${self.retail_price}/gal)"


class FuelPriceObservation(models.Model):
    """
    Raw fuel price observation from OPIS feed.
    Preserves all original price records (different grades, rack terminals, etc.).
    """
    opis_id = models.IntegerField(db_index=True)
    truckstop_name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=10)
    rack_id = models.IntegerField()
    retail_price = models.DecimalField(max_digits=7, decimal_places=4)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"OPIS {self.opis_id} Rack {self.rack_id}: ${self.retail_price}"
