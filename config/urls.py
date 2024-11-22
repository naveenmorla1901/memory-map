# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

# Swagger/OpenAPI configuration
schema_view = get_schema_view(
    openapi.Info(
        title="Memory Map API",
        default_version='v1',
        description="API documentation for Memory Map project",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@memorymap.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    # Admin URLs
    path('admin/', admin.site.urls),
    
    # Web URLs
    path('', include(('apps.core.web_urls', 'core'), namespace='core')),
    
    # User Web URLs (for templates)
    path('accounts/', include(('apps.users.web_urls', 'users-web'), namespace='users')),
    
    # API URLs
    path('api/v1/', include([
        path('auth/', include(('apps.users.api_urls', 'users-api'), namespace='users-api')),
        path('', include(('apps.core.urls', 'core-api'), namespace='core-api')),
    ])),
    
    # API Documentation
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)