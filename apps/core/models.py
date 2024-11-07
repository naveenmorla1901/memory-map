# apps/core/models.py
from django.db import models
from django.contrib.auth.models import User

class MemoryMap(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    tags = models.CharField(max_length=500, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_name = models.CharField(max_length=255, blank=True)
    instagram_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']

class MemoryNode(models.Model):
    memory_map = models.ForeignKey(MemoryMap, related_name='nodes', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    content = models.TextField()
    media_url = models.URLField(blank=True)
    media_type = models.CharField(max_length=50, choices=[
        ('image', 'Image'),
        ('video', 'Video'),
        ('instagram', 'Instagram')
    ], default='image')
    position_x = models.FloatField()
    position_y = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.memory_map.title} - {self.title}"
    

class InstagramReel(models.Model):
    memory_map = models.ForeignKey(MemoryMap, related_name='reels', on_delete=models.CASCADE)
    url = models.URLField()
    description = models.TextField(blank=True)
    likes = models.IntegerField(default=0)
    comments = models.IntegerField(default=0)
    date_posted = models.DateTimeField()
    date_extracted = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Reel for {self.memory_map.title}"

class Location(models.Model):
    memory_map = models.ForeignKey(MemoryMap, related_name='locations', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()
    extracted_from = models.ForeignKey(InstagramReel, related_name='extracted_locations', 
                                     on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return self.name