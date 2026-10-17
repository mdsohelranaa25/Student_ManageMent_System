from django.contrib import admin
from django.shortcuts import render

from .models import Batch, Course, ExamRoutine, Room, Routine, TimeSlot

@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("name", "is_running", "current_semester", "created_at")
    list_filter = ("is_running",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "credit", "semester", "teacher")
    list_filter = ("semester",)
    search_fields = ("code", "title")


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ("label", "order")


@admin.register(Routine)
class RoutineAdmin(admin.ModelAdmin):
    list_display = ("batch", "day", "time_slot", "room", "course")
    list_filter = ("batch", "day")

    def add_view(self, request, form_url="", extra_context=None):
        return render(request, "admin_routine_add_choice.html", {
            "title": "Add Routine",
            "opts": self.model._meta,
            "site_header": admin.site.site_header,
        })


@admin.register(ExamRoutine)
class ExamRoutineAdmin(admin.ModelAdmin):
    list_display = ("course", "date", "time_slot", "room", "created_by")
    list_filter = ("date",)

    def has_add_permission(self, request):
        return False