"""
The few server-rendered pages: a landing page, the legal pages the app
stores require a public URL for, the password-reset form linked from reset
emails, and a web form for deleting an account without the app (required by
Google Play).
"""
from django import forms
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponseServerError, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods

from apps.users.views import revoke_all_tokens


def landing(request):
    return render(request, 'web/landing.html')


def privacy(request):
    return render(request, 'web/privacy.html')


def terms(request):
    return render(request, 'web/terms.html')


class DeleteAccountForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))
    confirm = forms.BooleanField(label='I understand this permanently deletes my account and every place I saved.')


DELETE_ATTEMPT_LIMIT = 10
DELETE_ATTEMPT_WINDOW_SECONDS = 15 * 60


def _client_ip(request):
    # Same proxy-awareness as the API throttles (NUM_PROXIES), so a client
    # can't dodge the limit by sending its own X-Forwarded-For header.
    num_proxies = settings.REST_FRAMEWORK.get('NUM_PROXIES') or 0
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if num_proxies and forwarded:
        addresses = [a.strip() for a in forwarded.split(',')]
        return addresses[-min(num_proxies, len(addresses))]
    return request.META.get('REMOTE_ADDR', '')


def _bump(key):
    attempts = cache.get(key, 0) + 1
    cache.set(key, attempts, DELETE_ATTEMPT_WINDOW_SECONDS)
    return attempts


@require_http_methods(['GET', 'POST'])
def delete_account(request):
    form = DeleteAccountForm(request.POST or None)
    if request.method == 'POST':
        ip_key = f'web-delete-attempts:ip:{_client_ip(request)}'
        email_key = f"web-delete-attempts:email:{request.POST.get('email', '').strip().lower()}"
        if max(cache.get(ip_key, 0), cache.get(email_key, 0)) >= DELETE_ATTEMPT_LIMIT:
            form.add_error(None, 'Too many attempts. Please wait a few minutes and try again.')
        elif form.is_valid():
            user = authenticate(request, username=form.cleaned_data['email'], password=form.cleaned_data['password'])
            if user is None:
                _bump(ip_key)
                _bump(email_key)
                form.add_error(None, 'That email and password do not match an account.')
            else:
                with transaction.atomic():
                    revoke_all_tokens(user)
                    user.delete()
                return render(request, 'web/delete_account_done.html')
    return render(request, 'web/delete_account.html', {'form': form})


# --- Error pages ----------------------------------------------------------
# The app expects JSON from anything under /api/, even for URLs that don't
# exist; people in a browser get a page that matches the rest of the site.

def _wants_json(request):
    return request.path.startswith('/api/')


def page_not_found(request, exception=None):
    if _wants_json(request):
        return JsonResponse({'detail': 'Not found.'}, status=404)
    return render(request, 'web/error.html', {
        'title': 'Page not found', 'message': "The page you're looking for doesn't exist or has moved.",
    }, status=404)


def server_error(request):
    if _wants_json(request):
        return JsonResponse({'detail': 'Something went wrong on our side. Please try again.'}, status=500)
    # Rendered without the request so a broken context processor can't
    # turn the error page itself into another error.
    html = render_to_string('web/error.html', {
        'site_name': 'Memory Map', 'support_email': settings.SUPPORT_EMAIL, 'title': 'Something went wrong',
        'message': "That's on us. Please try again in a moment.",
    })
    return HttpResponseServerError(html)
