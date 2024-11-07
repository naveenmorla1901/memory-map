import os
import django
from django.core.management import execute_from_command_line
from django.test import Client
from django.urls import reverse

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def test_endpoints():
    client = Client()
    
    # Test endpoints
    endpoints = [
        '/',
        '/admin/',
        '/api/maps/',
        '/api/auth/login/',
    ]
    
    for endpoint in endpoints:
        response = client.get(endpoint)
        print(f"\nTesting {endpoint}:")
        print(f"Status Code: {response.status_code}")
        print(f"Content: {response.content[:100]}")  # First 100 chars

if __name__ == '__main__':
    test_endpoints()