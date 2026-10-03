from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("apply/", views.apply_choice, name="apply_choice"),
    path("apply/student/", views.apply_student, name="apply_student"),
    path("apply/teacher/", views.apply_teacher, name="apply_teacher"),
    path("login/", views.RoleBasedLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]