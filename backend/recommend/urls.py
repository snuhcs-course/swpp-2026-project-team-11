from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),
    path("sessions/", views.create_session),
    path("sessions/<str:session_id>/", views.session_state),
    path("sessions/<str:session_id>/answer/", views.answer),
    path("sessions/<str:session_id>/feedback/", views.feedback),
    path("sessions/<str:session_id>/recommend-now/", views.recommend_now),
    path("sessions/<str:session_id>/undo/", views.undo),
    path("sessions/<str:session_id>/ban/", views.ban),
    path("sessions/<str:session_id>/reason/", views.reason),
    path("sessions/<str:session_id>/menu/", views.menu),
    path("rooms/", views.create_room),
    path("rooms/join/", views.join_room),
    path("rooms/<str:code>/", views.room_state),
    path("rooms/<str:code>/start/", views.start_room),
    path("rooms/<str:code>/answer/", views.answer_room),
    path("rooms/<str:code>/recommend-now/", views.recommend_room_now),
    path("rooms/<str:code>/decide/", views.decide_room),
    path("rooms/<str:code>/leave/", views.leave_room),
]
