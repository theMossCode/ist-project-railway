from django.urls import path
from django.contrib.auth import views as auth_views

from . import views
from .forms import LoginForm

app_name = "authentication"

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="authentication/login.html"),
         name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", auth_views.LogoutView.as_view(next_page="dashboard:index"), name="logout"),
]
