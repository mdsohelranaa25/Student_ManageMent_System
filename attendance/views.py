from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render

from academics.models import Batch, Course
from accounts.models import User
from .models import Attendance


def teacher_only(user):
    return user.is_authenticated and user.role == "teacher"


def student_only(user):
    return user.is_authenticated and user.role == "student"


@login_required
@user_passes_test(teacher_only)
def take_attendance(request):
    batches = Batch.objects.filter(is_running=True)
    return render(request, "take_attendance.html", {"active": "attendance", "batches": batches})


@login_required
@user_passes_test(teacher_only)
def attendance_options(request):
    batch_id = request.GET.get("batch")
    batch = Batch.objects.filter(id=batch_id).first()
    courses = []
    if batch:
        courses = list(
            Course.objects.filter(teacher=request.user, semester=batch.current_semester)
            .values("id", "code", "title")
        )
    return JsonResponse({"courses": courses})


@login_required
@user_passes_test(teacher_only)
def attendance_students(request):
    batch_id = request.GET.get("batch")
    course_id = request.GET.get("course")
    date = request.GET.get("date")

    students = User.objects.filter(role="student", batch_id=batch_id, is_active=True).order_by("roll", "username")
    existing = {}
    if course_id and date:
        existing = {
            a.student_id: a.status
            for a in Attendance.objects.filter(course_id=course_id, date=date, student__batch_id=batch_id)
        }

    data = [
        {
            "id": s.id,
            "name": s.first_name,
            "username": s.username,
            "roll": s.roll,
            "status": existing.get(s.id, "P"),
        }
        for s in students
    ]
    return JsonResponse({"students": data})


@login_required
@user_passes_test(teacher_only)
def save_attendance(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    course_id = request.POST["course"]
    date = request.POST["date"]
    course = Course.objects.get(id=course_id, teacher=request.user)

    student_ids = request.POST.getlist("student_id")
    statuses = request.POST.getlist("status")

    for student_id, status in zip(student_ids, statuses):
        Attendance.objects.update_or_create(
            student_id=student_id, course=course, date=date,
            defaults={"status": status, "marked_by": request.user},
        )

    return JsonResponse({"ok": True, "message": f"Attendance saved for {course.code} on {date}."})


@login_required
@user_passes_test(student_only)
def student_attendance(request):
    batch = request.user.batch
    courses = Course.objects.filter(semester=batch.current_semester) if batch else Course.objects.none()

    course_id = request.GET.get("course")
    selected_course = courses.filter(id=course_id).first() if course_id else courses.first()

    records = []
    present_count = 0
    total_count = 0
    percentage = 0

    if selected_course:
        records = Attendance.objects.filter(student=request.user, course=selected_course).order_by("-date")
        total_count = records.count()
        present_count = records.filter(status="P").count()
        percentage = round((present_count / total_count) * 100, 1) if total_count else 0

    context = {
        "active": "attendance",
        "courses": courses,
        "selected_course": selected_course,
        "records": records,
        "present_count": present_count,
        "total_count": total_count,
        "percentage": percentage,
    }
    return render(request, "student_attendance.html", context)