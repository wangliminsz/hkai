from django.urls import path

from . import views

urlpatterns = [
    path("products/", views.products, name="rag-products"),
    path("chat/", views.chat, name="rag-chat"),
    path("chat/stream/", views.chat_stream, name="rag-chat-stream"),
    path("explain/", views.explain, name="rag-explain"),
    path("admin/products/", views.admin_products, name="rag-admin-products"),
    path("admin/ingest/", views.admin_ingest, name="rag-admin-ingest"),
]
