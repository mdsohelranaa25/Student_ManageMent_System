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
@user_passes_test(teacher_only)
def attendance_sheet(request):
    batches = Batch.objects.filter(is_running=True)
    batch_id = request.GET.get("batch", "")
    course_id = request.GET.get("course", "")

    selected_batch = Batch.objects.filter(id=batch_id).first() if batch_id.isdigit() else None

    course_options = []
    selected_course = None
    if selected_batch:
        course_options = Course.objects.filter(teacher=request.user, semester=selected_batch.current_semester)
        if course_id.isdigit():
            selected_course = course_options.filter(id=course_id).first()

    dates = []
    rows = []
    class_average = None

    if selected_batch and selected_course:
        students = User.objects.filter(
            role="student", batch=selected_batch, is_active=True
        ).order_by("roll", "username")
        records = Attendance.objects.filter(course=selected_course, student__batch=selected_batch)
        dates = sorted(set(records.values_list("date", flat=True)))
        lookup = {(r.student_id, r.date): r.status for r in records}

        for s in students:
            statuses = [lookup.get((s.id, d), "") for d in dates]
            marked = [x for x in statuses if x]
            present = marked.count("P")
            total = len(marked)
            percentage = round(present / total * 100, 1) if total else 0
            rows.append({
                "student": s,
                "statuses": statuses,
                "present": present,
                "total": total,
                "percentage": percentage,
            })

        if rows:
            class_average = round(sum(r["percentage"] for r in rows) / len(rows), 1)

    context = {
        "active": "attendance",
        "batches": batches,
        "selected_batch": selected_batch,
        "selected_course": selected_course,
        "course_options": course_options,
        "dates": dates,
        "rows": rows,
        "class_average": class_average,
    }
    return render(request, "attendance_sheet.html", context)


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