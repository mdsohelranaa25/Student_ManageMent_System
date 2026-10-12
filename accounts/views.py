from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

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
def student_profile(request):
    if request.method == "POST":
        form = ProfilePictureForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile picture updated.")
            return redirect("student_dashboard")
    else:
        form = ProfilePictureForm(instance=request.user)

    return render(request, "student_profile.html", {"form": form, "active": "profile"})