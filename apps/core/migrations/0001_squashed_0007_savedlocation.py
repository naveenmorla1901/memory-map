"""
Squashed schema for fresh databases (and the only one Postgres can run: the
old 0003 converts a bigint primary key to a UUID in place, which SQLite
tolerates and Postgres rejects).

A database that already applied some of the replaced migrations keeps
running the old chain instead - including 0007, which copies saved places
into SavedLocation. Once every deployment is past 0007 the replaced files
can be deleted.
"""

import django.core.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    replaces = [
        ("core", "0001_initial"),
        ("core", "0002_delete_locationmedia"),
        ("core", "0003_userlocation_and_more"),
        ("core", "0004_remove_location_core_locati_is_inst_2a9e9c_idx_and_more"),
        ("core", "0005_location_is_deleted_location_last_modified_and_more"),
        ("core", "0006_instagramreelcache_delete_instagramreel"),
        ("core", "0007_savedlocation"),
    ]

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InstagramReelCache",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("url", models.URLField(max_length=500, unique=True)),
                ("description", models.TextField(blank=True)),
                ("locations", models.JSONField(blank=True, default=list)),
                ("date_posted", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("analyzed", "Analyzed"),
                            ("no_locations", "No Locations Found"),
                            ("failed", "Failed"),
                        ],
                        max_length=20,
                    ),
                ),
                ("failure_reason", models.TextField(blank=True)),
                ("analyzed_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-analyzed_at"],
            },
        ),
        migrations.CreateModel(
            name="SavedLocation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("notes", models.TextField(blank=True)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("food", "Food"),
                            ("cafe", "Café"),
                            ("bar", "Bars & Nightlife"),
                            ("nature", "Nature"),
                            ("beach", "Beach"),
                            ("viewpoint", "Viewpoint"),
                            ("landmark", "Landmark"),
                            ("culture", "Culture"),
                            ("shopping", "Shopping"),
                            ("stay", "Stay"),
                            ("activity", "Activity"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=20,
                    ),
                ),
                (
                    "latitude",
                    models.FloatField(
                        validators=[
                            django.core.validators.MinValueValidator(-90),
                            django.core.validators.MaxValueValidator(90),
                        ]
                    ),
                ),
                (
                    "longitude",
                    models.FloatField(
                        validators=[
                            django.core.validators.MinValueValidator(-180),
                            django.core.validators.MaxValueValidator(180),
                        ]
                    ),
                ),
                ("address", models.CharField(blank=True, max_length=500)),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("manual", "Added manually"),
                            ("instagram", "From an Instagram reel"),
                        ],
                        default="manual",
                        max_length=20,
                    ),
                ),
                ("instagram_url", models.URLField(blank=True, max_length=500)),
                ("is_favorite", models.BooleanField(default=False)),
                ("visited", models.BooleanField(default=False)),
                ("notify_enabled", models.BooleanField(default=False)),
                (
                    "notify_radius_km",
                    models.FloatField(
                        default=1.0,
                        validators=[
                            django.core.validators.MinValueValidator(0.1),
                            django.core.validators.MaxValueValidator(50),
                        ],
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saved_locations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["user", "-created_at"],
                        name="core_savedl_user_id_c9bf7a_idx",
                    ),
                    models.Index(
                        fields=["user", "category"],
                        name="core_savedl_user_id_440cc5_idx",
                    ),
                    models.Index(
                        fields=["user", "is_favorite"],
                        name="core_savedl_user_id_5d292e_idx",
                    ),
                    models.Index(
                        fields=["user", "instagram_url"],
                        name="core_savedl_user_id_4e5d38_idx",
                    ),
                ],
            },
        ),
    ]
