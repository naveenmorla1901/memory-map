# Generated by Django 4.2 on 2024-11-11 11:25

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Location",
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
                ("name", models.CharField(max_length=255)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
                ("description", models.TextField(blank=True)),
                (
                    "location_type",
                    models.CharField(
                        choices=[
                            ("manual", "Manually Added"),
                            ("instagram", "From Instagram"),
                        ],
                        default="manual",
                        max_length=20,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("nature", "Nature"),
                            ("restaurant", "Restaurant"),
                            ("landmark", "Landmark"),
                            ("hotel", "Hotel"),
                            ("shopping", "Shopping"),
                            ("entertainment", "Entertainment"),
                            ("transport", "Transportation"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=20,
                    ),
                ),
                ("instagram_url", models.URLField(blank=True)),
                # ("instagram_media_type", models.CharField(blank=True, max_length=20)),
                ("date_posted", models.DateTimeField(blank=True, null=True)),
                (
                    "date_extracted",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("likes", models.IntegerField(blank=True, null=True)),
                ("comments", models.IntegerField(blank=True, null=True)),
                ("address", models.TextField(blank=True)),
                ("tags", models.CharField(blank=True, max_length=500)),
                ("image_url", models.URLField(blank=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="LocationMedia",
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
                (
                    "media_type",
                    models.CharField(
                        choices=[
                            ("image", "Image"),
                            ("video", "Video"),
                            ("instagram", "Instagram Post"),
                        ],
                        max_length=20,
                    ),
                ),
                ("url", models.URLField()),
                ("thumbnail_url", models.URLField(blank=True)),
                ("caption", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="media",
                        to="core.location",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Location media",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="InstagramReel",
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
                ("url", models.URLField(unique=True)),
                ("description", models.TextField(blank=True)),
                ("likes", models.IntegerField(default=0)),
                ("comments", models.IntegerField(default=0)),
                ("date_posted", models.DateTimeField(blank=True, null=True)),
                (
                    "date_extracted",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reels",
                        to="core.location",
                    ),
                ),
            ],
            options={
                "ordering": ["-date_posted"],
            },
        ),
        migrations.AddIndex(
            model_name="location",
            index=models.Index(
                fields=["latitude", "longitude"], name="core_locati_latitud_367ccc_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="location",
            index=models.Index(
                fields=["category"], name="core_locati_categor_4c1198_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="location",
            index=models.Index(
                fields=["created_by"], name="core_locati_created_101beb_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="instagramreel",
            index=models.Index(fields=["url"], name="core_instag_url_d0bad4_idx"),
        ),
        migrations.AddIndex(
            model_name="instagramreel",
            index=models.Index(
                fields=["created_by"], name="core_instag_created_fcd584_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="instagramreel",
            index=models.Index(
                fields=["date_posted"], name="core_instag_date_po_da2fe1_idx"
            ),
        ),
    ]
