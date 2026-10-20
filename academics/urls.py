from django.urls import path

from . import views

urlpatterns = [
    path("routine/create/", views.create_routine, name="create_routine"),
    path("routine/availability/", views.routine_availability, name="routine_availability"),
    path("exam-routine/create/", views.create_exam_routine, name="create_exam_routine"),
    path("exam-routine/availability/", views.exam_room_availability, name="exam_room_availability"),
    path("result/post/", views.post_result, name="post_result"),
    path("result/<int:result_id>/delete/", views.delete_result, name="delete_result"),
]