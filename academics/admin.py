from django.contrib import admin

from .models import Batch


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("name", "is_running", "created_at")
    list_filter = ("is_running",)