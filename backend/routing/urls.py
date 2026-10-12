from django.urls import path
from . import views

urlpatterns = [
    path("plan/", views.plan),
    path("corridor/", views.corridor),
    path("smart-departure/", views.smart_departure),
    path("auth/signup/", views.signup),
    path("auth/login/", views.login),
    path("auth/me/", views.me),
    path("trips/", views.trips),
    path("trips/<int:pk>/", views.trip_detail),
]
