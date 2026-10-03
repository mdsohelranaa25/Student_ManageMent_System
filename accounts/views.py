from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ApplicationForm
from .models import Application, User
from .utils import generate_password, generate_student_username, generate_teacher_username


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