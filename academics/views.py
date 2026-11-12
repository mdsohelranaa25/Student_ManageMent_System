from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import redirect, render

from accounts.models import User
from .models import Batch, Course, CourseGrade, ExamRoutine, Room, Routine, SemesterResult, TimeSlot


# Bangladesh University (UGC) Standard Grading Scale
GRADE_SCALE = [
    ("A+", Decimal("4.00")),
    ("A",  Decimal("3.75")),
    ("A-", Decimal("3.50")),
    ("B+", Decimal("3.25")),
    ("B",  Decimal("3.00")),
    ("B-", Decimal("2.75")),
    ("C+", Decimal("2.50")),
    ("C",  Decimal("2.25")),
    ("D",  Decimal("2.00")),
    ("F",  Decimal("0.00")),
]
GRADE_POINT_MAP = dict(GRADE_SCALE)


def recalculate_student_cgpas(student):
    """
    Recalculates cumulative CGPA for each semester result of the student,
    from semester 1 up to each semester.
    CGPA = sum(course.credit * grade_point) / sum(course.credit)
    for all courses taken in semesters <= S.
    """
    results = SemesterResult.objects.filter(student=student).order_by("semester")
    for res in results:
        prior_and_current_grades = CourseGrade.objects.filter(
            semester_result__student=student,
            semester_result__semester__lte=res.semester,
        ).select_related("course")

        total_weighted_points = Decimal("0.00")
        total_credits = Decimal("0.00")

        for cg in prior_and_current_grades:
            credit = cg.course.credit
            total_weighted_points += credit * cg.grade_point
            total_credits += credit

        if total_credits > 0:
            cgpa = (total_weighted_points / total_credits).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            cgpa = Decimal("0.00")

        if res.cgpa != cgpa:
            res.cgpa = cgpa
            res.save(update_fields=["cgpa"])


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
        if request.user.role == "teacher" and course.teacher_id != request.user.id:
            messages.error(request, "You can only schedule exams for your assigned courses.")
            return redirect("create_exam_routine")

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

    batches = Batch.objects.filter(is_running=True).order_by("-name")
    courses_by_batch = {}
    for b in batches:
        if b.current_semester:
            if request.user.role == "admin":
                c_qs = Course.objects.filter(semester=b.current_semester)
            else:
                c_qs = Course.objects.filter(semester=b.current_semester, teacher=request.user)
            courses_list = [{"id": c.id, "code": c.code, "title": c.title} for c in c_qs]
        else:
            courses_list = []
        courses_by_batch[str(b.id)] = {
            "name": b.name,
            "semester": b.current_semester,
            "courses": courses_list,
        }

    context = {
        "batches": batches,
        "courses_by_batch": courses_by_batch,
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
        student_id = request.POST.get("student")
        semester_val = request.POST.get("semester")

        if not student_id or not semester_val:
            messages.error(request, "Both student and semester must be selected.")
            return redirect("post_result")

        student = User.objects.get(id=student_id, role="student")
        semester = int(semester_val)

        semester_courses = list(Course.objects.filter(semester=semester).order_by("code"))
        if not semester_courses:
            messages.error(request, f"No courses found for Semester {semester}. Please add courses in academic curriculum first.")
            return redirect("post_result")

        course_ids = request.POST.getlist("course")
        grades = request.POST.getlist("grade")

        submitted_grades = {}
        for cid, gr in zip(course_ids, grades):
            gr = gr.strip().upper()
            if cid and gr:
                try:
                    submitted_grades[int(cid)] = gr
                except ValueError:
                    pass

        # Validate that EVERY course of this semester has a valid grade
        missing_courses = []
        invalid_grades = []
        for course in semester_courses:
            if course.id not in submitted_grades:
                missing_courses.append(course.code)
            else:
                gr = submitted_grades[course.id]
                if gr not in GRADE_POINT_MAP:
                    invalid_grades.append(f"{course.code} ({gr})")

        if missing_courses:
            messages.error(
                request,
                f"Grade is mandatory for all courses in Semester {semester}. Missing grades for: {', '.join(missing_courses)}."
            )
            return redirect("post_result")

        if invalid_grades:
            messages.error(
                request,
                f"Invalid letter grades for: {', '.join(invalid_grades)}. Allowed: A+, A, A-, B+, B, B-, C+, C, D, F."
            )
            return redirect("post_result")

        # Calculate Semester GPA
        total_sem_points = Decimal("0.00")
        total_sem_credits = Decimal("0.00")
        course_grade_data = []

        for course in semester_courses:
            gr = submitted_grades[course.id]
            point = GRADE_POINT_MAP[gr]
            total_sem_points += course.credit * point
            total_sem_credits += course.credit
            course_grade_data.append((course, gr, point))

        if total_sem_credits > 0:
            sem_gpa = (total_sem_points / total_sem_credits).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            sem_gpa = Decimal("0.00")

        # Save or update SemesterResult
        semester_result, _ = SemesterResult.objects.update_or_create(
            student=student, semester=semester, defaults={"gpa": sem_gpa, "cgpa": sem_gpa},
        )
        semester_result.course_grades.all().delete()
        for course, gr, point in course_grade_data:
            CourseGrade.objects.create(
                semester_result=semester_result,
                course=course,
                grade=gr,
                grade_point=point,
            )

        # Automatically recalculate CGPA from 1st semester up to this and subsequent semesters
        recalculate_student_cgpas(student)
        semester_result.refresh_from_db()

        student_label = student.first_name or student.username
        reg_or_roll = student.registration_no or student.roll or student.username
        messages.success(
            request,
            f"Result successfully published for {student_label} (ID: {reg_or_roll}), Semester {semester}! "
            f"Calculated Semester GPA: {semester_result.gpa} | Cumulative CGPA: {semester_result.cgpa}."
        )
        return redirect("post_result")

    edit_id = request.GET.get("edit")
    edit_result = None
    if edit_id:
        edit_result = SemesterResult.objects.filter(id=edit_id).select_related("student__batch").prefetch_related("course_grades__course").first()

    batches = list(Batch.objects.all().order_by("-name"))
    students_by_batch = {}
    for b in batches:
        s_list = User.objects.filter(role="student", batch=b).order_by("roll", "username")
        students_by_batch[str(b.id)] = [
            {
                "id": s.id,
                "name": s.first_name or s.username,
                "username": s.username,
                "roll": s.roll or "",
                "reg": s.registration_no or "",
            }
            for s in s_list
        ]
    unassigned_students = User.objects.filter(role="student", batch__isnull=True).order_by("username")
    if unassigned_students.exists():
        students_by_batch["unassigned"] = [
            {
                "id": s.id,
                "name": s.first_name or s.username,
                "username": s.username,
                "roll": s.roll or "",
                "reg": s.registration_no or "",
            }
            for s in unassigned_students
        ]

    courses_by_semester = {}
    for c in Course.objects.all().order_by("code"):
        courses_by_semester.setdefault(c.semester, []).append({
            "id": c.id,
            "code": c.code,
            "title": c.title,
            "credit": float(c.credit),
        })

    existing_results = (
        SemesterResult.objects.select_related("student", "student__batch")
        .prefetch_related("course_grades__course")
        .order_by("-published_at")[:40]
    )

    batch_meta = {
        str(b.id): {
            "name": b.name,
            "current_semester": b.current_semester,
        }
        for b in batches
    }

    context = {
        "batches": batches,
        "batch_meta": batch_meta,
        "students_by_batch": students_by_batch,
        "semesters": range(1, 9),
        "courses_by_semester": courses_by_semester,
        "grade_scale": [(g, str(p)) for g, p in GRADE_SCALE],
        "existing_results": existing_results,
        "edit_result": edit_result,
    }
    return render(request, "post_result.html", context)


@staff_member_required
def delete_result(request, result_id):
    res = SemesterResult.objects.filter(id=result_id).first()
    if res:
        student = res.student
        res.delete()
        recalculate_student_cgpas(student)
        messages.success(request, "Result deleted and CGPA recalculated successfully.")
    else:
        messages.error(request, "Result not found.")
    return redirect("post_result")
