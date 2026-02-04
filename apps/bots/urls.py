"""Bots URL configuration."""

from django.urls import path

from .views import BotCreateView, BotDetailView, BotListView, BotStopView

app_name = "bots"

urlpatterns = [
    path("", BotListView.as_view(), name="bot_list"),
    path("create/", BotCreateView.as_view(), name="bot_create"),
    path("<int:pk>/", BotDetailView.as_view(), name="bot_detail"),
    path("<int:pk>/stop/", BotStopView.as_view(), name="bot_stop"),
]
