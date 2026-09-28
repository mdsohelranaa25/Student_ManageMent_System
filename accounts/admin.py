from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Application, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "batch", "is_active")
    list_filter = ("role", "batch", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    fieldsets = UserAdmin.fieldsets + (
        ("Department info", {"fields": ("role", "phone", "batch")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Department info", {"fields": ("email", "role", "phone", "batch")}),
    )


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "email", "phone", "batch", "status", "created_at")
    list_filter = ("role", "status")
    search_fields = ("name", "email", "phone")