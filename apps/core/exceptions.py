import logging

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def _first_message(data):
    if isinstance(data, list) and data:
        return _first_message(data[0])
    if isinstance(data, dict) and data:
        key, value = next(iter(data.items()))
        message = _first_message(value)
        if not message or key in ('non_field_errors', 'detail'):
            return message
        return f"{str(key).replace('_', ' ').capitalize()}: {message}"
    return str(data) if data else None


def api_exception_handler(exc, context):
    """
    Every API error is JSON with a human-readable `detail` the app can show
    as-is. Validation errors keep their per-field `errors` too.
    """
    response = exception_handler(exc, context)
    if response is None:
        logger.exception('Unhandled API error in %s', context.get('view'))
        return Response({'detail': 'Something went wrong on our side. Please try again.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if isinstance(exc, ValidationError):
        response.data = {'detail': _first_message(response.data) or 'Invalid input.', 'errors': response.data}
    elif isinstance(response.data, dict) and 'detail' in response.data:
        response.data = {'detail': str(response.data['detail'])}
    return response
