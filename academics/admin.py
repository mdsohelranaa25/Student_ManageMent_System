from django.contrib import admin

from .models import Batch, Course, Room, TimeSlot


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