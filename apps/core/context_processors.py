from django.conf import settings


def site(request):
    return {
        'site_name': 'Memory Map',
        'support_email': settings.SUPPORT_EMAIL,
        'public_base_url': settings.PUBLIC_BASE_URL,
    }
