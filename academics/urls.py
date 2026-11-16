from django.urls import path

from . import views

urlpatterns = [
    path("routine/create/", views.create_routine, name="create_routine"),
    path("routine/availability/", views.routine_availability, name="routine_availability"),
    path("exam-routine/create/", views.create_exam_routine, name="create_exam_routine"),
    path("exam-routine/<int:exam_id>/delete/", views.delete_exam_routine, name="delete_exam_routine"),
    path("exam-routine/availability/", views.exam_room_availability, name="exam_room_availability"),
    path("result/post/", views.post_result, name="post_result"),
    path("result/upload/", views.upload_marks, name="upload_marks"),
    path("result/template/", views.download_mark_template, name="download_mark_template"),
    path("result/export/", views.export_batch_marks_excel, name="export_batch_marks_excel"),
    path("result/publish-batch/", views.publish_batch_results, name="publish_batch_results"),
    path("result/publish-incourse/", views.publish_incourse_marks, name="publish_incourse_marks"),
    path("result/mark/update/", views.update_student_mark_ajax, name="update_student_mark_ajax"),
    path("result/<int:result_id>/delete/", views.delete_result, name="delete_result"),
    path("teacher/marks/", views.teacher_submit_marks, name="teacher_submit_marks"),
]
