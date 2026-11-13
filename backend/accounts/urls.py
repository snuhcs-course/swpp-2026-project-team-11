from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.sign_up),
    path("login/", views.log_in),
    path("google/", views.google_sign_in),
    path("google/link/", views.link_google),
    path("me/", views.me),
    path("logout/", views.log_out),
]
