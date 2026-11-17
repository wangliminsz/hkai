from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("admin/companies", views.CardCompanyViewSet, basename="card-companies")

urlpatterns = [
    path("detect/", views.detect, name="cards-detect"),
    path("jobs/", views.jobs, name="cards-jobs"),
    path("jobs/<int:job_id>/", views.job_detail, name="cards-job-detail"),
    path("jobs/<int:job_id>/zip/", views.job_zip, name="cards-job-zip"),
    path("jobs/<int:job_id>/card/<int:idx>/", views.job_card, name="cards-job-card"),
    path("products/", views.product_catalog, name="cards-product-catalog"),
    path("admin/products/", views.admin_products, name="cards-admin-products"),
    path("admin/products/ai-draft/", views.admin_ai_draft, name="cards-admin-ai-draft"),
    path("admin/products/<str:pid>/rename/", views.admin_rename, name="cards-admin-rename"),
    path("admin/products/<str:pid>/validate/", views.admin_validate, name="cards-admin-validate"),
    path("admin/products/<str:pid>/publish/", views.admin_publish, name="cards-admin-publish"),
    path("admin/products/<str:pid>/<str:kind>/", views.admin_product_doc, name="cards-admin-product-doc"),
    path("admin/preview/", views.admin_preview, name="cards-admin-preview"),
    path("admin/upload-asset/", views.admin_upload_asset, name="cards-admin-upload-asset"),
    path("admin/asset/", views.admin_asset, name="cards-admin-asset"),
    path("", include(router.urls)),
]
