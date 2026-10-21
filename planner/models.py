from django.db import models


class Dataset(models.Model):
    """A single row makes every successful atomic import invalidate plan caches."""
    version = models.UUIDField()
    imported_at = models.DateTimeField(auto_now=True)
    source = models.CharField(max_length=255)
    report = models.JSONField(default=dict)


class Station(models.Model):
    external_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    latitude = models.FloatField(db_index=True, null=True)
    longitude = models.FloatField(db_index=True, null=True)
    coordinate_source = models.CharField(max_length=200, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=8)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(price__gt=0), name='positive_station_price')]


class FuelQuote(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='quotes')
    source_row = models.PositiveIntegerField()
    rack_id = models.CharField(max_length=100, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=8)
    raw = models.JSONField(default=dict)
