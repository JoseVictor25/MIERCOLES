"""
URL configuration for UML Tool project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.projects.urls")),
    path("api/", include("apps.chat.urls")),
    path("api/", include("apps.generator.urls")),
    path("api/", include("apps.ai_core.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
