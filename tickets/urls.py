from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("tickets/", views.ticket_list, name="ticket_list"),
    path("tickets/new/", views.ticket_create, name="ticket_create"),
    path("tickets/queue/", views.ticket_queue, name="ticket_queue"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("tickets/<int:pk>/comment/", views.ticket_add_comment, name="ticket_add_comment"),
    path("tickets/<int:pk>/status/", views.ticket_change_status, name="ticket_change_status"),
    path("tickets/<int:pk>/priority/", views.ticket_change_priority, name="ticket_change_priority"),
    path("tickets/<int:pk>/assign/", views.ticket_assign, name="ticket_assign"),
]