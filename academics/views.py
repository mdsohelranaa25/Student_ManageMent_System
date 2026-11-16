from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
# this is without any reason
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from .models import (
    Batch, Course, CourseGrade, ExamRoutine, Room, Routine, SemesterResult,
    StudentCourseMark, TimeSlot,
)
from .marks_utils import (
    GRADE_POINT_MAP, GRADE_SCALE, calculate_ugc_grade, find_batch_by_name,
    find_course_by_code, generate_consolidated_batch_workbook,
    generate_sample_final_workbook, generate_sample_incourse_workbook,
    parse_final_file, parse_incourse_file, save_parsed_final_marks,
    save_parsed_incourse_marks,
)


def cleanup_past_exams():
    """
    Automatically deletes exam routines whose date has passed (date < today).
    Exams on today's date remain active until midnight. Once the date passes
    (on the next date), they are automatically purged from the database.
    """
    today = timezone.localdate()
    ExamRoutine.objects.filter(date__lt=today).delete()


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
    # Automatically purge past exams whose date has passed
    cleanup_past_exams()
    today = timezone.localdate()

    if request.method == "POST":
        course = Course.objects.get(id=request.POST["course"])
        if request.user.role == "teacher" and course.teacher_id != request.user.id:
            messages.error(request, "You can only schedule exams for your assigned courses.")
            return redirect("create_exam_routine")

        date_str = request.POST["date"]
        try:
            exam_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            messages.error(request, "Invalid date format.")
            return redirect("create_exam_routine")

        if exam_date < today:
            messages.error(request, "Examination date cannot be in the past.")
            return redirect("create_exam_routine")

        time_slot = TimeSlot.objects.get(id=request.POST["time_slot"])
        room = Room.objects.get(id=request.POST["room"])

        if ExamRoutine.objects.filter(room=room, date=exam_date, time_slot=time_slot).exists():
            messages.error(request, "That room is no longer available for this date/time. Please try again.")
        else:
            ExamRoutine.objects.create(
                course=course, date=exam_date, time_slot=time_slot, room=room, created_by=request.user,
            )
            messages.success(request, f"Exam added: {course.code} on {exam_date} at {time_slot}.")
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
        "today": today,
        "existing": ExamRoutine.objects.filter(date__gte=today).select_related("course", "time_slot", "room").order_by("date", "time_slot__order"),
    }
    return render(request, "create_exam_routine.html", context)


@login_required
@user_passes_test(admin_or_teacher)
def delete_exam_routine(request, exam_id):
    if request.method == "POST":
        if request.user.role == "admin":
            exam = ExamRoutine.objects.filter(id=exam_id).first()
        else:
            exam = ExamRoutine.objects.filter(id=exam_id, created_by=request.user).first()

        if exam:
            code = exam.course.code
            dt = exam.date
            exam.delete()
            messages.success(request, f"Exam schedule removed for {code} on {dt}.")
        else:
            messages.error(request, "Exam schedule not found or you do not have permission to delete it.")
    return redirect("create_exam_routine")


@login_required
@user_passes_test(admin_or_teacher)
def exam_room_availability(request):
    cleanup_past_exams()
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
    """
    Unified Semester Results Hub for Admins:
      - Tab 1: Batch & Semester Review & Publishing Overview (Matrix, Status, Publish, Export)
      - Tab 2: Excel Upload (Incourse 40/60 & Final 60/40/100) with flexible header/batch matching
      - Tab 3: Manual Single-Student Entry & Adjustments (backward compatible)
    """
    if request.method == "POST" and "manual_submit" in request.POST:
        # Handle original single-student manual entry
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

        recalculate_student_cgpas(student)
        semester_result.refresh_from_db()

        student_label = student.first_name or student.username
        reg_or_roll = student.registration_no or student.roll or student.username
        messages.success(
            request,
            f"Result successfully published for {student_label} (ID: {reg_or_roll}), Semester {semester}! "
            f"Semester GPA: {semester_result.gpa} | Cumulative CGPA: {semester_result.cgpa}."
        )
        return redirect("post_result")

    # Filter selections for Overview Tab
    batches = list(Batch.objects.all().order_by("-name"))
    batch_param = request.GET.get("batch")
    selected_batch = None
    if batch_param:
        selected_batch = Batch.objects.filter(id=batch_param).first()
    if not selected_batch and batches:
        # Prefer first running batch
        running = [b for b in batches if b.is_running]
        selected_batch = running[0] if running else batches[0]

    semester_param = request.GET.get("semester")
    if semester_param:
        try:
            selected_semester = int(semester_param)
        except ValueError:
            selected_semester = selected_batch.current_semester or 1 if selected_batch else 1
    else:
        selected_semester = selected_batch.current_semester or 1 if selected_batch else 1

    active_tab = request.GET.get("tab", "overview")

    # Courses of selected semester
    semester_courses = list(Course.objects.filter(semester=selected_semester).order_by("code"))
    batch_students = []
    if selected_batch:
        batch_students = list(User.objects.filter(role="student", batch=selected_batch).order_by("roll", "registration_no", "username"))

    total_students_count = len(batch_students)

    # Fetch marks map for selected batch and semester
    marks_map = {}
    if selected_batch:
        for scm in StudentCourseMark.objects.filter(batch=selected_batch, semester=selected_semester).select_related("course"):
            marks_map[(scm.student_id, scm.course_id)] = scm

    # Course status checklist
    course_statuses = []
    ready_courses_count = 0

    for c in semester_courses:
        incourse_count = 0
        final_count = 0
        complete_count = 0

        for s in batch_students:
            scm = marks_map.get((s.id, c.id))
            if scm:
                if scm.incourse_marks is not None:
                    incourse_count += 1
                if scm.final_marks is not None:
                    final_count += 1
                if scm.total_marks is not None:
                    complete_count += 1

        is_viva = (c.course_type == "viva")
        incourse_ready = is_viva or (total_students_count > 0 and incourse_count >= total_students_count)
        final_ready = (total_students_count > 0 and final_count >= total_students_count)
        is_ready = incourse_ready and final_ready
        if is_ready:
            ready_courses_count += 1

        course_statuses.append({
            "course": c,
            "incourse_count": incourse_count,
            "final_count": final_count,
            "complete_count": complete_count,
            "total_students": total_students_count,
            "is_viva": is_viva,
            "incourse_ready": incourse_ready,
            "final_ready": final_ready,
            "is_ready": is_ready,
        }) 

    is_all_courses_ready = (len(semester_courses) > 0 and ready_courses_count == len(semester_courses))

    # Published Status for this batch and semester
    published_results = {}
    if selected_batch:
        for sr in SemesterResult.objects.filter(student__batch=selected_batch, semester=selected_semester):
            published_results[sr.student_id] = sr

    is_already_published = (total_students_count > 0 and len(published_results) >= total_students_count)

    # Consolidated student rows for review table
    student_review_rows = []
    for s in batch_students:
        c_marks = []
        tot_points = Decimal("0.00")
        tot_credits = Decimal("0.00")

        for c in semester_courses:
            scm = marks_map.get((s.id, c.id))
            c_marks.append({
                "course": c,
                "mark_obj": scm,
                "incourse": scm.incourse_marks if (scm and scm.incourse_marks is not None) else None,
                "final": scm.final_marks if (scm and scm.final_marks is not None) else None,
                "total": scm.total_marks if (scm and scm.total_marks is not None) else None,
                "grade": scm.grade if (scm and scm.grade) else None,
                "gp": scm.grade_point if (scm and scm.grade_point is not None) else None,
            })
            if scm and scm.grade_point is not None:
                tot_points += c.credit * scm.grade_point
                tot_credits += c.credit

        proj_gpa = (tot_points / tot_credits).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tot_credits > 0 else None
        published_sr = published_results.get(s.id)

        student_review_rows.append({
            "student": s,
            "course_marks": c_marks,
            "projected_gpa": proj_gpa,
            "published_result": published_sr,
        })

    # Data for Manual Entry Tab
    edit_id = request.GET.get("edit")
    edit_result = None
    if edit_id:
        edit_result = SemesterResult.objects.filter(id=edit_id).select_related("student__batch").prefetch_related("course_grades__course").first()

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
        .order_by("-published_at")[:30]
    )

    batch_meta = {
        str(b.id): {
            "name": b.name,
            "current_semester": b.current_semester,
        }
        for b in batches
    }

    all_courses_all_semesters = list(Course.objects.all().order_by("semester", "code"))

    context = {
        "active_tab": active_tab,
        "batches": batches,
        "selected_batch": selected_batch,
        "selected_semester": selected_semester,
        "semester_courses": semester_courses,
        "course_statuses": course_statuses,
        "is_all_courses_ready": is_all_courses_ready,
        "is_already_published": is_already_published,
        "student_review_rows": student_review_rows,
        "total_students_count": total_students_count,
        "ready_courses_count": ready_courses_count,
        "all_courses": all_courses_all_semesters,
        # Manual tab data
        "batch_meta": batch_meta,
        "students_by_batch": students_by_batch,
        "semesters": range(1, 9),
        "courses_by_semester": courses_by_semester,
        "grade_scale": [(g, str(p)) for g, p in GRADE_SCALE],
        "existing_results": existing_results,
        "edit_result": edit_result,
    }
    return render(request, "post_result.html", context)


@login_required
@user_passes_test(admin_or_teacher)
def upload_marks(request):
    """
    Handles Excel/CSV upload for:
      - Incourse Marks (Max 40 for Theory, 60 for Lab, 0 for Viva)
      - Final Exam Marks (Max 60 for Theory, 40 for Lab, 100 for Viva)
    Matches Course and Batch flexibly (case/space-tolerant).
    """
    if request.method != "POST":
        return redirect("post_result")

    mark_type = request.POST.get("mark_type", "incourse")
    uploaded_file = request.FILES.get("file")

    if not uploaded_file:
        messages.error(request, "Please choose an Excel (.xlsx) or CSV file to upload.")
        return redirect("post_result")

    batch_id = request.POST.get("batch")
    course_id = request.POST.get("course")

    target_batch = Batch.objects.filter(id=batch_id).first() if batch_id else None
    target_course = Course.objects.filter(id=course_id).first() if course_id else None

    # If teacher is uploading, they can only submit incourse marks for their assigned courses
    if request.user.role == "teacher":
        if mark_type != "incourse":
            messages.error(request, "Faculty members are authorized to upload Incourse marks only.")
            return redirect("teacher_submit_marks")
        if target_course and target_course.teacher_id != request.user.id:
            messages.error(request, "You can only upload marks for your assigned courses.")
            return redirect("teacher_submit_marks")

    redirect_url = "/academics/result/post/"
    if request.user.role == "teacher":
        redirect_url = "/teacher-dashboard/marks/"

    if mark_type == "incourse":
        parsed = parse_incourse_file(uploaded_file, target_batch=target_batch, target_course=target_course)
        if parsed.get("errors"):
            for err in parsed["errors"]:
                messages.error(request, f"Incourse upload error: {err}")
            return redirect(redirect_url)

        # Check teacher permission on detected course
        if request.user.role == "teacher" and parsed["course"].teacher_id != request.user.id:
            messages.error(request, f"Course {parsed['course'].code} is not assigned to your faculty profile.")
            return redirect(redirect_url)

        success_count, updated_count = save_parsed_incourse_marks(parsed, request.user)
        total_saved = success_count + updated_count

        if parsed.get("warnings"):
            for w in parsed["warnings"][:5]:  # show up to 5 warnings
                messages.warning(request, w)
            if len(parsed["warnings"]) > 5:
                messages.warning(request, f"...and {len(parsed['warnings']) - 5} more warning(s).")

        messages.success(
            request,
            f"Successfully processed incourse marks for {total_saved} student(s) in "
            f"{parsed['course'].code} ({parsed['batch'].name})."
        )
        if request.user.role == "admin":
            return redirect(f"/academics/result/post/?batch={parsed['batch'].id}&semester={parsed['course'].semester}&tab=overview")
        return redirect(redirect_url)

    elif mark_type == "final":
        if request.user.role != "admin":
            messages.error(request, "Only institute administrators can upload semester final exam marks.")
            return redirect(redirect_url)

        parsed = parse_final_file(uploaded_file, target_batch=target_batch, target_course=target_course)
        if parsed.get("errors"):
            for err in parsed["errors"]:
                messages.error(request, f"Final exam upload error: {err}")
            return redirect(redirect_url)

        success_count, updated_count = save_parsed_final_marks(parsed, request.user)
        total_saved = success_count + updated_count

        if parsed.get("warnings"):
            for w in parsed["warnings"][:5]:
                messages.warning(request, w)
            if len(parsed["warnings"]) > 5:
                messages.warning(request, f"...and {len(parsed['warnings']) - 5} more warning(s).")

        messages.success(
            request,
            f"Successfully processed final marks for {total_saved} student(s) in {parsed['course'].code}! "
            f"Marks combined with incourse & UGC grades generated."
        )
        redirect_batch_id = parsed['batch'].id if parsed.get('batch') else (target_batch.id if target_batch else "")
        return redirect(f"/academics/result/post/?batch={redirect_batch_id}&semester={parsed['course'].semester}&tab=overview")

    messages.error(request, "Invalid mark upload type.")
    return redirect(redirect_url)


@login_required
@user_passes_test(admin_or_teacher)
def download_mark_template(request):
    """
    Downloads pre-populated Excel template (.xlsx) for:
      - Incourse (Roll, Reg, Name, Blank Mark)
      - Final (Registration No, Roll, Name, Blank Mark)
    """
    tmpl_type = request.GET.get("type", "incourse")
    batch_id = request.GET.get("batch")
    course_id = request.GET.get("course")

    batch = Batch.objects.filter(id=batch_id).first() if batch_id else None
    course = Course.objects.filter(id=course_id).first() if course_id else None

    if tmpl_type == "incourse":
        output = generate_sample_incourse_workbook(batch, course)
        b_name = batch.name if batch else "Batch"
        c_code = (course.code.replace(" ", "_") if course else "Course")
        filename = f"Incourse_Template_{c_code}_{b_name}.xlsx"
    else:
        output = generate_sample_final_workbook(batch, course)
        b_name = f"_{batch.name}" if batch else ""
        c_code = (course.code.replace(" ", "_") if course else "Course")
        filename = f"Final_Exam_Template_{c_code}{b_name}.xlsx"

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@staff_member_required
def export_batch_marks_excel(request):
    """
    Exports full consolidated semester evaluation sheet for a batch (.xlsx).
    """
    batch_id = request.GET.get("batch")
    semester_val = request.GET.get("semester", "1")

    batch = get_object_or_404(Batch, id=batch_id)
    try:
        semester = int(semester_val)
    except ValueError:
        semester = 1

    output = generate_consolidated_batch_workbook(batch, semester)
    filename = f"Consolidated_Batch_{batch.name}_Semester_{semester}.xlsx"

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@staff_member_required
def publish_batch_results(request):
    """
    Officially publishes semester results for the selected batch and semester.
    Computes UGC semester GPA and updates cumulative CGPA.
    Transfers marks from StudentCourseMark into official SemesterResult and CourseGrade.
    """
    if request.method != "POST":
        return redirect("post_result")

    batch_id = request.POST.get("batch")
    semester_val = request.POST.get("semester")

    batch = get_object_or_404(Batch, id=batch_id)
    try:
        semester = int(semester_val)
    except (ValueError, TypeError):
        messages.error(request, "Invalid semester specified.")
        return redirect("post_result")

    semester_courses = list(Course.objects.filter(semester=semester).order_by("code"))
    if not semester_courses:
        messages.error(request, f"No courses found for Semester {semester}.")
        return redirect(f"/academics/result/post/?batch={batch.id}&semester={semester}")

    batch_students = list(User.objects.filter(role="student", batch=batch))
    if not batch_students:
        messages.error(request, f"No students enrolled in Batch {batch.name}.")
        return redirect(f"/academics/result/post/?batch={batch.id}&semester={semester}")

    published_count = 0
    now = timezone.now()

    for student in batch_students:
        total_pts = Decimal("0.00")
        total_crs = Decimal("0.00")
        grade_entries = []

        # Find or ensure marks for all courses
        for course in semester_courses:
            scm = StudentCourseMark.objects.filter(student=student, course=course).first()
            if not scm or scm.grade_point is None or not scm.grade:
                # If mark is missing or not computed yet
                # Check if viva (incourse 0, final might be present)
                if scm and scm.final_marks is not None and course.course_type == "viva":
                    tot = scm.final_marks
                    gr, gp = calculate_ugc_grade(tot)
                    scm.incourse_marks = Decimal("0.00")
                    scm.total_marks = tot
                    scm.grade = gr
                    scm.grade_point = gp
                    scm.save()
                elif scm and scm.incourse_marks is not None and scm.final_marks is not None:
                    tot = scm.incourse_marks + scm.final_marks
                    gr, gp = calculate_ugc_grade(tot)
                    scm.total_marks = tot
                    scm.grade = gr
                    scm.grade_point = gp
                    scm.save()
                else:
                    # Default zero / incomplete
                    gr = "F"
                    gp = Decimal("0.00")
                    scm, _ = StudentCourseMark.objects.get_or_create(
                        student=student, course=course,
                        defaults={
                            "batch": batch,
                            "semester": semester,
                            "grade": gr,
                            "grade_point": gp,
                        }
                    )

            gr = scm.grade or "F"
            gp = scm.grade_point if scm.grade_point is not None else Decimal("0.00")
            total_pts += course.credit * gp
            total_crs += course.credit
            grade_entries.append((course, gr, gp, scm.incourse_marks, scm.final_marks, scm.total_marks))

        if total_crs > 0:
            sem_gpa = (total_pts / total_crs).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            sem_gpa = Decimal("0.00")

        # Save or update official SemesterResult
        sem_res, _ = SemesterResult.objects.update_or_create(
            student=student, semester=semester,
            defaults={"gpa": sem_gpa, "cgpa": sem_gpa, "published_at": now}
        )

        # Sync CourseGrade records
        sem_res.course_grades.all().delete()
        for c, gr, gp, inc, fin, tot in grade_entries:
            CourseGrade.objects.create(
                semester_result=sem_res,
                course=c,
                grade=gr,
                grade_point=gp,
                incourse_marks=inc,
                final_marks=fin,
                total_marks=tot,
            )

        # Recalculate CGPA across all completed semesters
        recalculate_student_cgpas(student)

        # Mark draft marks as officially published
        StudentCourseMark.objects.filter(student=student, course__in=semester_courses).update(
            is_final_published=True, is_incourse_published=True
        )
        published_count += 1

    messages.success(
        request,
        f"Congratulations! Officially published Semester {semester} results for {published_count} "
        f"student(s) in Batch {batch.name}. CGPAs recalculated via UGC standard."
    )
    return redirect(f"/academics/result/post/?batch={batch.id}&semester={semester}&tab=overview")


@login_required
@user_passes_test(admin_or_teacher)
def publish_incourse_marks(request):
    """
    Enables students to view their incourse marks early for a specific course.
    """
    if request.method != "POST":
        return redirect("post_result")

    batch_id = request.POST.get("batch")
    course_id = request.POST.get("course")

    batch = get_object_or_404(Batch, id=batch_id)
    course = get_object_or_404(Course, id=course_id)

    if request.user.role == "teacher" and course.teacher_id != request.user.id:
        messages.error(request, "Permission denied.")
        return redirect("teacher_submit_marks")

    updated = StudentCourseMark.objects.filter(batch=batch, course=course).update(is_incourse_published=True)
    messages.success(request, f"Incourse marks published for {course.code} (Batch {batch.name}). Students can now view these scores.")

    if request.user.role == "teacher":
        return redirect("teacher_submit_marks")
    return redirect(f"/academics/result/post/?batch={batch.id}&semester={course.semester}&tab=overview")


@staff_member_required
def update_student_mark_ajax(request):
    """
    Allows rapid inline mark adjustments from the admin consolidated preview table.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    student_id = request.POST.get("student_id")
    course_id = request.POST.get("course_id")
    incourse_raw = request.POST.get("incourse_marks", "").strip()
    final_raw = request.POST.get("final_marks", "").strip()

    student = get_object_or_404(User, id=student_id, role="student")
    course = get_object_or_404(Course, id=course_id)

    try:
        inc = Decimal(incourse_raw) if incourse_raw != "" else None
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Invalid incourse mark format"})

    try:
        fin = Decimal(final_raw) if final_raw != "" else None
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Invalid final mark format"})

    scm, _ = StudentCourseMark.objects.get_or_create(
        student=student, course=course,
        defaults={"batch": student.batch, "semester": course.semester}
    )
    scm.incourse_marks = inc
    scm.final_marks = fin

    if course.course_type == "viva":
        if fin is not None:
            scm.total_marks = fin
            scm.grade, scm.grade_point = calculate_ugc_grade(fin)
    elif inc is not None and fin is not None:
        scm.total_marks = inc + fin
        scm.grade, scm.grade_point = calculate_ugc_grade(scm.total_marks)
    else:
        scm.total_marks = None
        scm.grade = ""
        scm.grade_point = None

    scm.save()

    return JsonResponse({
        "success": True,
        "total": float(scm.total_marks) if scm.total_marks is not None else None,
        "grade": scm.grade or "",
        "grade_point": float(scm.grade_point) if scm.grade_point is not None else None,
    })


@login_required
@user_passes_test(lambda u: u.is_authenticated and u.role == "teacher")
def teacher_submit_marks(request):
    """
    Faculty portal page for teachers to manage and upload Incourse marks for their assigned courses.
    """
    teacher = request.user
    assigned_courses = Course.objects.filter(teacher=teacher).order_by("code")
    batches = Batch.objects.filter(is_running=True).order_by("-name")

    selected_course_id = request.GET.get("course")
    selected_batch_id = request.GET.get("batch")

    selected_course = None
    if selected_course_id:
        selected_course = assigned_courses.filter(id=selected_course_id).first()
    if not selected_course and assigned_courses.exists():
        selected_course = assigned_courses.first()

    selected_batch = None
    if selected_batch_id:
        selected_batch = batches.filter(id=selected_batch_id).first()
    if not selected_batch and batches.exists():
        selected_batch = batches.first()

    student_marks = []
    if selected_course and selected_batch:
        students = User.objects.filter(role="student", batch=selected_batch).order_by("roll", "username")
        marks_dict = {
            scm.student_id: scm
            for scm in StudentCourseMark.objects.filter(batch=selected_batch, course=selected_course)
        }
        for s in students:
            student_marks.append({
                "student": s,
                "mark_obj": marks_dict.get(s.id),
            })

    context = {
        "active": "marks",
        "assigned_courses": assigned_courses,
        "batches": batches,
        "selected_course": selected_course,
        "selected_batch": selected_batch,
        "student_marks": student_marks,
    }
    return render(request, "teacher_submit_marks.html", context)


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
