from django.contrib import admin
from django.urls import include, path

from admin_control.admin_site import admin_site

urlpatterns = [
    path("admin/", admin_site.urls),
    path("api/v1/", include("admin_control.schema_urls")),
    path("api/v1/", include("admin_control.urls")),
]
