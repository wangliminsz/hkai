from django.urls import path

from . import views

urlpatterns = [
    path("keys/", views.keys, name="aikeys-keys"),
    path("keys/<int:pk>/", views.key_detail, name="aikeys-key-detail"),
    path("keys/<int:pk>/test/", views.key_test, name="aikeys-key-test"),
    path("credits/", views.credits, name="aikeys-credits"),
    path("overview/", views.overview, name="aikeys-overview"),
    path("settings/", views.settings_view, name="aikeys-settings"),
]
