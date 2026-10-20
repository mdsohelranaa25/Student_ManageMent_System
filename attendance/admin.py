from django.contrib import admin

from .models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "date", "status", "marked_by")
    list_filter = ("course", "date", "status")
    search_fields = ("student__username", "student__first_name")