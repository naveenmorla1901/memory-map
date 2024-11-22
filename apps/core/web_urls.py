#apps/core/web_urls.py
from django.urls import path
from django.views.generic import TemplateView

app_name = 'core'

urlpatterns = [
    path('', TemplateView.as_view(template_name='core/index.html'), name='index'),
    path('test-analyzer/', TemplateView.as_view(template_name='core/test_analyzer.html'), name='test-analyzer'),
]