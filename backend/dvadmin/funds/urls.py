from django.urls import path

from . import views

urlpatterns = [
    path("groups/", views.groups, name="funds-groups"),
    path("groups/<int:pk>/", views.group_detail, name="funds-group-detail"),
    path("schedule/", views.schedule_preview, name="funds-schedule"),
    path("broadcasts/", views.broadcasts, name="funds-broadcasts"),
    path("broadcasts/<int:pk>/", views.broadcast_detail, name="funds-broadcast-detail"),
    path("qveris-credits/", views.qveris_credits, name="funds-qveris-credits"),
    path("analysis/", views.fund_analysis, name="funds-analysis"),
    path("report/<str:lot>/<str:name>", views.fund_report, name="funds-report"),
    path("prompts/", views.prompt_list, name="funds-prompts"),
    path("prompts/<str:key>/", views.prompt_update, name="funds-prompt-update"),
    path("prompts/<str:key>/reset/", views.prompt_reset, name="funds-prompt-reset"),
    path("news-sources/", views.news_sources, name="funds-news-sources"),
    path("news-sources/<int:pk>/", views.news_source_detail, name="funds-news-source-detail"),
    path("news/preview/", views.news_preview, name="funds-news-preview"),
    path("news/html/<str:date>/<str:edition>/<str:kind>/", views.news_html, name="funds-news-html"),
    path("news/broadcasts/", views.news_broadcasts, name="funds-news-broadcasts"),
    path("news/broadcasts/<int:pk>/", views.news_broadcast_detail, name="funds-news-broadcast-detail"),
]
