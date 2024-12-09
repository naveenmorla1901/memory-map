# apps/core/admin.py
from django.contrib import admin
from .models import Location, InstagramReel, UserLocation
@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'location_type', 'category', 'is_instagram_source', 'created_at')
    list_filter = ('location_type', 'category', 'is_instagram_source', 'created_at')
    search_fields = ('name', 'description', 'address')
    readonly_fields = ('created_at', 'updated_at', 'last_synced')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'latitude', 'longitude', 'description', 'address')
        }),
        ('Classification', {
            'fields': ('location_type', 'category')
        }),
        ('Instagram Data', {
            'fields': ('is_instagram_source', 'instagram_url', 'date_posted'),
            'classes': ('collapse',)
        }),
        ('Sync Information', {
            'fields': ('sync_status', 'last_synced', 'firebase_id'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

@admin.register(UserLocation)
class UserLocationAdmin(admin.ModelAdmin):
    list_display = ('user', 'location', 'is_favorite', 'notify_enabled', 'saved_at')
    list_filter = ('is_favorite', 'notify_enabled', 'saved_at')
    search_fields = ('user__username', 'location__name', 'custom_name')
    readonly_fields = ('saved_at', 'updated_at', 'last_synced')
    
    fieldsets = (
        ('Relationship', {
            'fields': ('user', 'location')
        }),
        ('Customization', {
            'fields': ('custom_name', 'custom_description', 'custom_category', 'notes')
        }),
        ('Preferences', {
            'fields': ('is_favorite', 'notify_enabled', 'notify_radius')
        }),
        ('Sync Information', {
            'fields': ('sync_status', 'last_synced', 'firebase_id'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('saved_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'location')

@admin.register(InstagramReel)
class InstagramReelAdmin(admin.ModelAdmin):
    list_display = ('url', 'created_by', 'date_posted', 'likes', 'comments')
    list_filter = ('date_posted', 'created_at')
    search_fields = ('url', 'description')
    readonly_fields = ('date_extracted', 'created_at')