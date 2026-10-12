from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("apply/", views.apply_choice, name="apply_choice"),
    path("apply/student/", views.apply_student, name="apply_student"),
    path("apply/teacher/", views.apply_teacher, name="apply_teacher"),
    path("login/", views.RoleBasedLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("applications/", views.applications_list, name="applications_list"),
    path("applications/<int:application_id>/approve/", views.approve_application, name="approve_application"),
    path("applications/<int:application_id>/reject/", views.reject_application, name="reject_application"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("verify-code/", views.verify_reset_code, name="verify_reset_code"),
    path("set-new-password/", views.set_new_password, name="set_new_password"),
]