from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import redirect, render

from accounts.models import User
from .models import Batch, Course, CourseGrade, ExamRoutine, Room, Routine, SemesterResult, TimeSlot


def admin_or_teacher(user):
    return user.is_authenticated and user.role in ("admin", "teacher")


@staff_member_required
def create_routine(request):
    if request.method == "POST":
        batch = Batch.objects.get(id=request.POST["batch"])
        day = request.POST["day"]
        time_slot = TimeSlot.objects.get(id=request.POST["time_slot"])
        room = Room.objects.get(id=request.POST["room"])
        course = Course.objects.get(id=request.POST["course"])

        conflict = Routine.objects.filter(batch=batch, day=day, time_slot=time_slot).exists() or \
            Routine.objects.filter(room=room, day=day, time_slot=time_slot).exists()

        if conflict:
            messages.error(request, "That batch or room is no longer available for this slot. Please try again.")
        else:
            Routine.objects.create(batch=batch, day=day, time_slot=time_slot, room=room, course=course)
            messages.success(request, f"Routine added: {batch} - {course.code} on {day} at {time_slot}.")
        return redirect("create_routine")

    context = {
        "batches": Batch.objects.filter(is_running=True),
        "days": Routine._meta.get_field("day").choices,
        "time_slots": TimeSlot.objects.all(),
        "existing": Routine.objects.select_related("batch", "time_slot", "room", "course"),
    }
    return render(request, "create_routine.html", context)


@staff_member_required
def routine_availability(request):
    batch_id = request.GET.get("batch")
    day = request.GET.get("day")
    time_slot_id = request.GET.get("time_slot")

    batch = Batch.objects.get(id=batch_id)
    courses = list(Course.objects.filter(semester=batch.current_semester).values("id", "code", "title"))

    rooms = []
    if day and time_slot_id:
        booked_room_ids = set(
            Routine.objects.filter(day=day, time_slot_id=time_slot_id).values_list("room_id", flat=True)
        )
        batch_taken = Routine.objects.filter(batch=batch, day=day, time_slot_id=time_slot_id).exists()
        for room in Room.objects.all():
            rooms.append({"id": room.id, "name": room.name, "available": room.id not in booked_room_ids})
    else:
        batch_taken = False
        for room in Room.objects.all():
            rooms.append({"id": room.id, "name": room.name, "available": True})

    return JsonResponse({"courses": courses, "rooms": rooms, "batch_slot_taken": batch_taken})


@login_required
@user_passes_test(admin_or_teacher)
def create_exam_routine(request):
    if request.method == "POST":
        course = Course.objects.get(id=request.POST["course"])
        date = request.POST["date"]
        time_slot = TimeSlot.objects.get(id=request.POST["time_slot"])
        room = Room.objects.get(id=request.POST["room"])

        if ExamRoutine.objects.filter(room=room, date=date, time_slot=time_slot).exists():
            messages.error(request, "That room is no longer available for this date/time. Please try again.")
        else:
            ExamRoutine.objects.create(
                course=course, date=date, time_slot=time_slot, room=room, created_by=request.user,
            )
            messages.success(request, f"Exam added: {course.code} on {date} at {time_slot}.")
        return redirect("create_exam_routine")

    course_qs = Course.objects.all() if request.user.role == "admin" else Course.objects.filter(teacher=request.user)

    courses_by_semester = {}
    for c in course_qs:
        courses_by_semester.setdefault(c.semester, []).append({"id": c.id, "code": c.code, "title": c.title})

    context = {
        "semesters": range(1, 9),
        "courses_by_semester": courses_by_semester,
        "time_slots": TimeSlot.objects.all(),
        "existing": ExamRoutine.objects.select_related("course", "time_slot", "room").order_by("date", "time_slot__order"),
    }
    return render(request, "create_exam_routine.html", context)


@login_required
@user_passes_test(admin_or_teacher)
def exam_room_availability(request):
    date = request.GET.get("date")
    time_slot_id = request.GET.get("time_slot")

    rooms = []
    if date and time_slot_id:
        booked_room_ids = set(
            ExamRoutine.objects.filter(date=date, time_slot_id=time_slot_id).values_list("room_id", flat=True)
        )
        for room in Room.objects.all():
            rooms.append({"id": room.id, "name": room.name, "available": room.id not in booked_room_ids})
    else:
        for room in Room.objects.all():
            rooms.append({"id": room.id, "name": room.name, "available": True})

    return JsonResponse({"rooms": rooms})


@staff_member_required
def post_result(request):
    if request.method == "POST":
        student = User.objects.get(id=request.POST["student"], role="student")
        semester = int(request.POST["semester"])
        gpa = request.POST["gpa"]
        cgpa = request.POST["cgpa"]

        semester_result, _ = SemesterResult.objects.update_or_create(
            student=student, semester=semester, defaults={"gpa": gpa, "cgpa": cgpa},
        )
        semester_result.course_grades.all().delete()

        course_ids = request.POST.getlist("course")
        grades = request.POST.getlist("grade")
        points = request.POST.getlist("grade_point")
        for course_id, grade, point in zip(course_ids, grades, points):
            if course_id and grade and point:
                CourseGrade.objects.create(
                    semester_result=semester_result, course_id=course_id, grade=grade, grade_point=point,
                )

        messages.success(request, f"Result posted for {student.username}, semester {semester}.")
        return redirect("post_result")

    edit_id = request.GET.get("edit")
    edit_result = None
    if edit_id:
        edit_result = SemesterResult.objects.filter(id=edit_id).prefetch_related("course_grades__course").first()

    students = User.objects.filter(role="student").order_by("username")
    courses_by_semester = {}
    for c in Course.objects.all():
        courses_by_semester.setdefault(c.semester, []).append({"id": c.id, "code": c.code, "title": c.title})

    existing_results = (
        SemesterResult.objects.select_related("student")
        .prefetch_related("course_grades__course")
        .order_by("-published_at")[:30]
    )

    context = {
        "students": students,
        "semesters": range(1, 9),
        "courses_by_semester": courses_by_semester,
        "existing_results": existing_results,
        "edit_result": edit_result,
    }
    return render(request, "post_result.html", context)


@staff_member_required
def delete_result(request, result_id):
    SemesterResult.objects.filter(id=result_id).delete()
    messages.success(request, "Result deleted.")
    return redirect("post_result")