from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from datetime import date as date_today

from academics.models import Announcement, AnnouncementComment, Batch, Course, ExamRoutine, Routine, SemesterResult, TimeSlot
from .forms import ApplicationForm, ForgotPasswordForm, ProfilePictureForm, SetNewPasswordForm
from .models import Application, PasswordResetCode, User
from .utils import generate_password, generate_reset_code, generate_student_username, generate_teacher_username


def home(request):
    return render(request, "home.html")


def apply_choice(request):
    return render(request, "apply_choice.html")


def apply_student(request):
    if request.method == "POST":
        form = ApplicationForm(request.POST, role="student")
        if form.is_valid():
            application = form.save(commit=False)
            application.role = "student"
            application.save()
            messages.success(request, "Application submitted. The admin will review it soon.")
            return redirect("home")
    else:
        form = ApplicationForm(role="student")

    return render(request, "apply.html", {"form": form, "role": "Student"})


def apply_teacher(request):
    if request.method == "POST":
        form = ApplicationForm(request.POST, role="teacher")
        if form.is_valid():
            application = form.save(commit=False)
            application.role = "teacher"
            application.save()
            messages.success(request, "Application submitted. The admin will review it soon.")
            return redirect("home")
    else:
        form = ApplicationForm(role="teacher")

    return render(request, "apply.html", {"form": form, "role": "Teacher"})


class RoleBasedLoginView(auth_views.LoginView):
    template_name = "login.html"

    def get_success_url(self):
        role = self.request.user.role
        if role == "admin":
            return "/admin-dashboard/"
        elif role == "teacher":
            return "/teacher-dashboard/"
        return "/student-dashboard/"


def admin_only(user):
    return user.is_authenticated and user.role == "admin"


@login_required
@user_passes_test(admin_only)
def applications_list(request):
    pending = Application.objects.filter(status="pending")
    return render(request, "applications_list.html", {"applications": pending})


@login_required
@user_passes_test(admin_only)
def approve_application(request, application_id):
    application = get_object_or_404(Application, id=application_id, status="pending")

    if application.role == "student":
        username = generate_student_username(application.batch, application.name)
    else:
        username = generate_teacher_username(application.name)

    password = generate_password()

    user = User.objects.create_user(
        username=username,
        email=application.email,
        password=password,
        role=application.role,
        phone=application.phone,
        batch=application.batch if application.role == "student" else None,
        first_name=application.name,
    )

    application.status = "approved"
    application.user = user
    application.save()

    send_mail(
        "Your account has been approved",
        f"Hello {application.name},\n\n"
        f"Your application has been approved.\n\n"
        f"Username: {username}\n"
        f"Password: {password}\n\n"
        f"Log in and change your password after your first login.",
        None,
        [application.email],
    )

    messages.success(request, f"Approved. Login ID {username} was emailed to {application.email}.")
    return redirect("applications_list")


@login_required
@user_passes_test(admin_only)
def reject_application(request, application_id):
    application = get_object_or_404(Application, id=application_id, status="pending")
    application.status = "rejected"
    application.save()
    messages.success(request, f"Rejected the application from {application.name}.")
    return redirect("applications_list")


def forgot_password(request):
    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data["identifier"]
            user = User.objects.filter(
                Q(username=identifier) | Q(email__iexact=identifier)
            ).first()

            if user:
                code = generate_reset_code()
                PasswordResetCode.objects.filter(user=user).delete()
                PasswordResetCode.objects.create(
                    user=user,
                    code_hash=make_password(code),
                    expires_at=timezone.now() + timedelta(minutes=2),
                )
                send_mail(
                    "Your password reset code",
                    f"Your code is {code}. It expires in 2 minutes.",
                    None,
                    [user.email],
                )
                request.session["reset_user_id"] = user.id

            messages.success(request, "If that account exists, a reset code has been sent to its email.")
            return redirect("verify_reset_code")
    else:
        form = ForgotPasswordForm()

    return render(request, "forgot_password.html", {"form": form})


def verify_reset_code(request):
    user_id = request.session.get("reset_user_id")
    if not user_id:
        messages.error(request, "Please start the password reset process again.")
        return redirect("forgot_password")

    if request.method == "POST":
        entered_code = request.POST.get("code", "").strip()
        record = PasswordResetCode.objects.filter(user_id=user_id).first()

        if not record or record.expires_at < timezone.now() or record.attempts >= 5:
            messages.error(request, "This code is invalid or expired. Please request a new one.")
            return redirect("forgot_password")

        record.attempts += 1
        record.save()

        if check_password(entered_code, record.code_hash):
            request.session["reset_verified"] = True
            return redirect("set_new_password")
        else:
            messages.error(request, "Incorrect code. Please try again.")

    return render(request, "verify_reset_code.html")


def set_new_password(request):
    user_id = request.session.get("reset_user_id")
    verified = request.session.get("reset_verified")

    if not user_id or not verified:
        messages.error(request, "Please verify your code first.")
        return redirect("forgot_password")

    if request.method == "POST":
        form = SetNewPasswordForm(request.POST)
        if form.is_valid():
            user = get_object_or_404(User, id=user_id)
            user.set_password(form.cleaned_data["new_password"])
            user.save()

            PasswordResetCode.objects.filter(user=user).delete()
            del request.session["reset_user_id"]
            del request.session["reset_verified"]

            messages.success(request, "Password changed. You can log in now.")
            return redirect("login")
    else:
        form = SetNewPasswordForm()

    return render(request, "set_new_password.html", {"form": form})


def student_only(user):
    return user.is_authenticated and user.role == "student"


@login_required
@user_passes_test(student_only)
def student_dashboard_home(request):
    return render(request, "student_dashboard_home.html", {"active": "home"})


@login_required
@user_passes_test(student_only)
def student_profile(request):
    if request.method == "POST":
        form = ProfilePictureForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile picture updated.")
            return redirect("student_profile")
    else:
        form = ProfilePictureForm(instance=request.user)

    return render(request, "student_profile.html", {"form": form, "active": "profile"})

@login_required
@user_passes_test(student_only)
def student_routine(request):
    view_mode = request.GET.get("view", "mine")

    if view_mode == "combined":
        batches = Batch.objects.filter(is_running=True)
        routines_qs = Routine.objects.filter(batch__in=batches).select_related("batch", "time_slot", "room", "course")
        selected_batch = None
    else:
        if view_mode == "mine" or not view_mode.isdigit():
            selected_batch = request.user.batch
        else:
            selected_batch = Batch.objects.filter(id=view_mode).first()
        routines_qs = (
            Routine.objects.filter(batch=selected_batch).select_related("batch", "time_slot", "room", "course")
            if selected_batch else Routine.objects.none()
        )

    time_slots = list(TimeSlot.objects.all())
    days = Routine._meta.get_field("day").choices

    grid = {d[0]: {ts.id: [] for ts in time_slots} for d in days}
    for r in routines_qs:
        grid[r.day][r.time_slot_id].append(r)

    if view_mode == "combined":
        semesters = set(Batch.objects.filter(is_running=True).values_list("current_semester", flat=True))
    elif selected_batch:
        semesters = {selected_batch.current_semester}
    else:
        semesters = set()

    upcoming_exams = ExamRoutine.objects.filter(
        course__semester__in=semesters, date__gte=date_today.today()
    ).select_related("course", "time_slot", "room").order_by("date", "time_slot__order")

    rows = []
    for day_value, day_label in days:
        rows.append({
            "label": day_label,
            "cells": [grid[day_value][ts.id] for ts in time_slots],
        })

    context = {
        "active": "routine",
        "view_mode": view_mode,
        "time_slots": time_slots,
        "rows": rows,
        "selected_batch": selected_batch,
        "all_batches": Batch.objects.filter(is_running=True),
        "upcoming_exams": upcoming_exams,
    }
    return render(request, "student_routine.html", context)
def teacher_only(user):
    return user.is_authenticated and user.role == "teacher"


@login_required
@user_passes_test(teacher_only)
def teacher_dashboard_home(request):
    return render(request, "teacher_dashboard_home.html", {"active": "home"})


@login_required
@user_passes_test(teacher_only)
def teacher_profile(request):
    if request.method == "POST":
        form = ProfilePictureForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile picture updated.")
            return redirect("teacher_profile")
    else:
        form = ProfilePictureForm(instance=request.user)
    return render(request, "teacher_profile.html", {"form": form, "active": "profile"})
@login_required
@user_passes_test(teacher_only)
def teacher_routine(request):
    view_mode = request.GET.get("view", "combined")

    if view_mode == "combined" or not view_mode.isdigit():
        batches = Batch.objects.filter(is_running=True)
        routines_qs = Routine.objects.filter(batch__in=batches).select_related("batch", "time_slot", "room", "course")
        selected_batch = None
        view_mode = "combined"
    else:
        selected_batch = Batch.objects.filter(id=view_mode).first()
        routines_qs = (
            Routine.objects.filter(batch=selected_batch).select_related("batch", "time_slot", "room", "course")
            if selected_batch else Routine.objects.none()
        )

    time_slots = list(TimeSlot.objects.all())
    days = Routine._meta.get_field("day").choices

    grid = {d[0]: {ts.id: [] for ts in time_slots} for d in days}
    for r in routines_qs:
        grid[r.day][r.time_slot_id].append(r)

    if view_mode == "combined":
        for day_value in grid:
            for ts_id in grid[day_value]:
                grid[day_value][ts_id].sort(key=lambda r: r.batch.current_semester or 0)

    rows = []
    for day_value, day_label in days:
        rows.append({"label": day_label, "cells": [grid[day_value][ts.id] for ts in time_slots]})

    if view_mode == "combined":
        semesters = set(Batch.objects.filter(is_running=True).values_list("current_semester", flat=True))
    elif selected_batch:
        semesters = {selected_batch.current_semester}
    else:
        semesters = set()

    upcoming_exams = ExamRoutine.objects.filter(
        course__semester__in=semesters, date__gte=date_today.today()
    ).select_related("course", "time_slot", "room").order_by("date", "time_slot__order")

    context = {
        "active": "routine",
        "view_mode": view_mode,
        "time_slots": time_slots,
        "rows": rows,
        "selected_batch": selected_batch,
        "all_batches": Batch.objects.filter(is_running=True),
        "upcoming_exams": upcoming_exams,
    }
    return render(request, "teacher_routine.html", context)
@login_required
@user_passes_test(teacher_only)
def teacher_announcement(request):
    my_courses = Course.objects.filter(teacher=request.user)

    if request.method == "POST":
        course = Course.objects.get(id=request.POST["course"], teacher=request.user)
        batch = Batch.objects.get(id=request.POST["batch"])
        Announcement.objects.create(
            teacher=request.user,
            course=course,
            batch=batch,
            text=request.POST["text"],
            image=request.FILES.get("image"),
            attachment=request.FILES.get("attachment"),
     )
        messages.success(request, "Announcement posted.")
        return redirect("teacher_announcement")

    announcements = Announcement.objects.filter(teacher=request.user).select_related("course", "batch").prefetch_related("comments__student")

    context = {
        "active": "announcement",
        "my_courses": my_courses,
        "all_batches": Batch.objects.filter(is_running=True),
        "announcements": announcements,
    }
    return render(request, "teacher_announcement.html", context)


@login_required
@user_passes_test(teacher_only)
def teacher_announcement_comment(request, announcement_id):
    announcement = Announcement.objects.get(id=announcement_id, teacher=request.user)
    if request.method == "POST":
        AnnouncementComment.objects.create(
            announcement=announcement, student=request.user, text=request.POST["text"],
        )
    return redirect("teacher_announcement")


@login_required
@user_passes_test(student_only)
def student_notice_board(request):
    batch = request.user.batch
    announcements = (
        Announcement.objects.filter(batch=batch).select_related("course", "teacher")
        .prefetch_related("comments__student")
        if batch else Announcement.objects.none()
    )
    context = {"active": "notice", "announcements": announcements}
    return render(request, "student_notice_board.html", context)


@login_required
@user_passes_test(student_only)
def student_post_comment(request, announcement_id):
    announcement = Announcement.objects.get(id=announcement_id, batch=request.user.batch)
    if request.method == "POST":
        AnnouncementComment.objects.create(
            announcement=announcement, student=request.user, text=request.POST["text"],
        )
    return redirect("student_notice_board")

@login_required
@user_passes_test(teacher_only)
def teacher_edit_announcement(request, announcement_id):
    announcement = Announcement.objects.get(id=announcement_id, teacher=request.user)
    if request.method == "POST":
        announcement.text = request.POST["text"]
        if request.FILES.get("image"):
            announcement.image = request.FILES["image"]
        if request.FILES.get("attachment"):
            announcement.attachment = request.FILES["attachment"]
        announcement.save()
        messages.success(request, "Announcement updated.")
    return redirect("teacher_announcement")


@login_required
@user_passes_test(teacher_only)
def teacher_delete_announcement(request, announcement_id):
    Announcement.objects.filter(id=announcement_id, teacher=request.user).delete()
    messages.success(request, "Announcement deleted.")
    return redirect("teacher_announcement")


@login_required
@user_passes_test(teacher_only)
def teacher_delete_comment(request, comment_id):
    AnnouncementComment.objects.filter(id=comment_id, announcement__teacher=request.user).delete()
    return redirect("teacher_announcement")


@login_required
@user_passes_test(student_only)
def student_delete_comment(request, comment_id):
    AnnouncementComment.objects.filter(id=comment_id, student=request.user).delete()
    return redirect("student_notice_board")
@login_required
@user_passes_test(student_only)
def student_results(request):
    results = (
        SemesterResult.objects.filter(student=request.user)
        .prefetch_related("course_grades__course")
        .order_by("semester")
    )
    latest_cgpa = results.last().cgpa if results else None
    context = {"active": "results", "results": results, "latest_cgpa": latest_cgpa}
    return render(request, "student_results.html", context)
@login_required
@user_passes_test(admin_only)
def admin_dashboard_home(request):
    stats = {
        "pending_applications": Application.objects.filter(status="pending").count(),
        "total_students": User.objects.filter(role="student").count(),
        "total_teachers": User.objects.filter(role="teacher").count(),
        "total_courses": Course.objects.count(),
        "running_batches": Batch.objects.filter(is_running=True).count(),
    }
    return render(request, "admin_dashboard_home.html", {"stats": stats})