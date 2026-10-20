from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts import views as account_views
from attendance import views as attendance_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", account_views.home, name="home"),
    path("accounts/", include("accounts.urls")),
    path("academics/", include("academics.urls")),
    path("student-dashboard/", account_views.student_dashboard_home, name="student_dashboard"),
    path("student-dashboard/profile/", account_views.student_profile, name="student_profile"),
    path("student-dashboard/routine/", account_views.student_routine, name="student_routine"),
    path("student-dashboard/attendance/", attendance_views.student_attendance, name="student_attendance"),
    path("student-dashboard/notice/", account_views.student_notice_board, name="student_notice_board"),
    path("student-dashboard/notice/<int:announcement_id>/comment/", account_views.student_post_comment, name="student_post_comment"),
    path("student-dashboard/notice/comment/<int:comment_id>/delete/", account_views.student_delete_comment, name="student_delete_comment"),
    path("student-dashboard/results/", account_views.student_results, name="student_results"),
    path("student-dashboard/change-password/", account_views.student_change_password, name="student_change_password"),
    path("admin-dashboard/", account_views.admin_dashboard_home, name="admin_dashboard"),
    path("teacher-dashboard/", account_views.teacher_dashboard_home, name="teacher_dashboard"),
    path("teacher-dashboard/profile/", account_views.teacher_profile, name="teacher_profile"),
    path("teacher-dashboard/routine/", account_views.teacher_routine, name="teacher_routine"),
    path("teacher-dashboard/attendance/", attendance_views.take_attendance, name="take_attendance"),
    path("teacher-dashboard/attendance/options/", attendance_views.attendance_options, name="attendance_options"),
    path("teacher-dashboard/attendance/students/", attendance_views.attendance_students, name="attendance_students"),
    path("teacher-dashboard/attendance/save/", attendance_views.save_attendance, name="save_attendance"),
    path("teacher-dashboard/announcement/", account_views.teacher_announcement, name="teacher_announcement"),
    path("teacher-dashboard/announcement/<int:announcement_id>/comment/", account_views.teacher_announcement_comment, name="teacher_announcement_comment"),
    path("teacher-dashboard/announcement/<int:announcement_id>/edit/", account_views.teacher_edit_announcement, name="teacher_edit_announcement"),
    path("teacher-dashboard/announcement/<int:announcement_id>/delete/", account_views.teacher_delete_announcement, name="teacher_delete_announcement"),
    path("teacher-dashboard/announcement/comment/<int:comment_id>/delete/", account_views.teacher_delete_comment, name="teacher_delete_comment"),
    path("teacher-dashboard/change-password/", account_views.teacher_change_password, name="teacher_change_password"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)