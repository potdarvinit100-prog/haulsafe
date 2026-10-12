from django.contrib import admin
from .models import Trip


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("name", "origin", "destination", "user", "departure", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "origin", "destination", "user__username")
