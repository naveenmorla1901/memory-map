from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core import views as core_views
from apps.core import web_views

admin.site.site_header = 'Memory Map admin'
admin.site.site_title = 'Memory Map admin'

urlpatterns = [
    path('', web_views.landing, name='landing'),
    path('privacy/', web_views.privacy, name='privacy'),
    path('terms/', web_views.terms, name='terms'),
    path('delete-account/', web_views.delete_account, name='delete-account'),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='web/password_reset_confirm.html', success_url='/reset/done/'
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(template_name='web/password_reset_complete.html'),
        name='password_reset_complete',
    ),
    path('healthz/', core_views.healthz, name='healthz'),
    path(settings.ADMIN_URL, admin.site.urls),
    path('api/v1/auth/', include('apps.users.api_urls')),
    path('api/v1/', include('apps.core.urls')),
]

if settings.API_DOCS_ENABLED:
    urlpatterns += [
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='api-docs'),
    ]

handler404 = 'apps.core.web_views.page_not_found'
handler500 = 'apps.core.web_views.server_error'
