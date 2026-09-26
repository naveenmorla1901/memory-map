from django.contrib import admin

from .models import InstagramReelCache, SavedLocation


@admin.register(SavedLocation)
class SavedLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'category', 'source', 'is_favorite', 'visited', 'created_at')
    list_filter = ('category', 'source', 'is_favorite', 'visited', 'notify_enabled')
    search_fields = ('name', 'address', 'user__username', 'user__email')
    readonly_fields = ('id', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    fieldsets = (
        (None, {'fields': ('id', 'user', 'name', 'category', 'description', 'notes')}),
        ('Place', {'fields': ('latitude', 'longitude', 'address')}),
        ('Source', {'fields': ('source', 'instagram_url')}),
        ('Preferences', {'fields': ('is_favorite', 'visited', 'notify_enabled', 'notify_radius_km')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(InstagramReelCache)
class InstagramReelCacheAdmin(admin.ModelAdmin):
    list_display = ('url', 'status', 'date_posted', 'analyzed_at')
    list_filter = ('status',)
    search_fields = ('url', 'description')
    readonly_fields = ('analyzed_at', 'created_at')
