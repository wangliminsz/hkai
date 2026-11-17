from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    InsurerPortalViewSet,
    internal_users,
    job_detail,
    job_pdf,
    jobs,
    portal_options,
)

router = DefaultRouter()
router.register("admin/portals", InsurerPortalViewSet, basename="insurer-portals")

urlpatterns = [
    path("portals/", portal_options, name="proposal-portal-options"),
    path("admin/internal-users/", internal_users, name="proposal-internal-users"),
    path("jobs/", jobs, name="proposal-jobs"),
    path("jobs/<int:job_id>/", job_detail, name="proposal-job-detail"),
    path("jobs/<int:job_id>/pdf/", job_pdf, name="proposal-job-pdf"),
    path("", include(router.urls)),
]
