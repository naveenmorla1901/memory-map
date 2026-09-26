from rest_framework.throttling import SimpleRateThrottle


class _PerUserOrIPThrottle(SimpleRateThrottle):
    """Rate-limits by user when signed in, by client IP otherwise."""

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = f'user-{request.user.pk}'
        else:
            ident = f'ip-{self.get_ident(request)}'
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class AuthThrottle(_PerUserOrIPThrottle):
    scope = 'auth'


class ReelAnalysisThrottle(_PerUserOrIPThrottle):
    scope = 'reel_analysis'


class GeocodeThrottle(_PerUserOrIPThrottle):
    scope = 'geocode'
