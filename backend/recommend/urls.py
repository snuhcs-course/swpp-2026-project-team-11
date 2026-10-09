# AI-generated: written with Claude (Anthropic) and reviewed by the team.
from django.urls import path

from . import views

urlpatterns = [
    path("sessions/", views.create_session),
    path("sessions/<str:session_id>/", views.session_state),
    path("sessions/<str:session_id>/answer/", views.answer),
    path("sessions/<str:session_id>/feedback/", views.feedback),
    path("sessions/<str:session_id>/recommend-now/", views.recommend_now),
    path("sessions/<str:session_id>/undo/", views.undo),
]
