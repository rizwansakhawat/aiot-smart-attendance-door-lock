"""
URL Configuration for Smart Attendance Project
"""

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as static_serve
from pathlib import Path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('attendance.urls')),
    path('door-control/', include('door_control.urls')),
]

# Serve media files in development and local DEBUG=False runs.
media_root = Path(settings.MEDIA_ROOT)
if settings.DEBUG or (media_root.exists() and any(media_root.iterdir())):
    if settings.DEBUG:
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    else:
        media_prefix = str(settings.MEDIA_URL).lstrip('/').rstrip('/')
        urlpatterns += [
            re_path(
                rf'^{media_prefix}/(?P<path>.*)$',
                static_serve,
                {'document_root': settings.MEDIA_ROOT},
            )
        ]

# Local fallback: allow static serving with DEBUG=False when using runserver.
# Use STATIC_ROOT when collectstatic has been run; otherwise serve from STATICFILES_DIRS.
static_root = Path(settings.STATIC_ROOT)
if static_root.exists() and any(static_root.iterdir()):
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
elif settings.STATICFILES_DIRS:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])