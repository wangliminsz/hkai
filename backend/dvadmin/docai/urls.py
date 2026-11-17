from django.urls import path

from . import views

urlpatterns = [
    path("access/", views.access, name="docai-access"),
    path("settings/", views.settings_view, name="docai-settings"),
    path("prompts/", views.prompts_view, name="docai-prompts"),
    path("analyze/", views.analyze, name="docai-analyze"),
    path("jobs/", views.jobs, name="docai-jobs"),
    path("jobs/<int:pk>/", views.job_detail, name="docai-job-detail"),
    path("jobs/<int:pk>/report/", views.report, name="docai-job-report"),
]
