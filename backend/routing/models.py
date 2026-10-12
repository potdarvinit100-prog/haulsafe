from django.conf import settings
from django.db import models


class Trip(models.Model):
    """A saved route plan belonging to one driver."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trips"
    )
    name = models.CharField(max_length=200, blank=True, default="")
    origin = models.CharField(max_length=200)
    destination = models.CharField(max_length=200)
    departure = models.DateTimeField()
    load_weight_lb = models.FloatField()
    sample_miles = models.FloatField()
    plan_result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.origin} -> {self.destination} ({self.user})"
