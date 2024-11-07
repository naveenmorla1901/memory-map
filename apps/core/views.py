from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .instagram.analyzer import InstagramReelAnalyzer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import json
import logging

logger = logging.getLogger(__name__)

@swagger_auto_schema(
    method='post',
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['url'],
        properties={
            'url': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Instagram reel URL to analyze'
            )
        }
    ),
    responses={
        200: openapi.Response(
            description="Success",
            examples={
                "application/json": {
                    "url": "https://www.instagram.com/reel/DA0_T50u6lx/",
                    "likes": None,
                    "comments": None,
                    "date_posted": "October 7, 2024",
                    "date_extracted": "2024-11-01 01:06:56",
                    "description": "Best place for fall foliage. Highest peak in Pisgah National Forest.",
                    "locations": [
                        {
                            "name": "Pisgah National Forest",
                            "type": "forest",
                            "coordinates": None,
                            "category": "nature"
                        }
                    ]
                }
            }
        )
    }
)
@csrf_exempt  # Add this decorator
@api_view(['POST'])
@permission_classes([AllowAny])
def analyze_instagram_reel(request):
    """
    Analyze Instagram reel URL and extract information
    """
    try:
        url = request.data.get('url')
        if not url:
            return Response({
                'error': 'URL is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get API key from settings
        google_api_key = settings.GOOGLE_API_KEY
        if not google_api_key:
            return Response({
                'error': 'Google API key not configured'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Initialize the analyzer
        analyzer = InstagramReelAnalyzer(google_api_key)

        # Analyze the reel
        result = analyzer.analyze_reel(url)

        if result:
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Failed to analyze reel'
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.error(f"Error analyzing reel: {str(e)}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def test_analyzer_page(request):
    """Render test page for the analyzer"""
    return render(request, 'core/test_analyzer.html')