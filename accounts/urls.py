from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from .views import DevDeskPasswordChangeView

urlpatterns = [
    path("login/", LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("password/", DevDeskPasswordChangeView.as_view(), name="password_change"),
]