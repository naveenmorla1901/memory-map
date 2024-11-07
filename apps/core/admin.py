# apps/core/admin.py
from django.contrib import admin
from .models import MemoryMap, MemoryNode

@admin.register(MemoryMap)
class MemoryMapAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_by', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at', 'created_by')
    search_fields = ('title', 'description', 'tags')

@admin.register(MemoryNode)
class MemoryNodeAdmin(admin.ModelAdmin):
    list_display = ('title', 'memory_map', 'created_at')
    list_filter = ('memory_map', 'created_at')
    search_fields = ('title', 'content')
