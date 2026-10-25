from django.urls import path

from . import views

app_name = "customer_services"
urlpatterns = [
    path("", views.assignment_list, name="list"),
    path("new/", views.assignment_create, name="create"),
    path("<uuid:pk>/", views.assignment_detail, name="detail"),
    path("<uuid:pk>/edit/", views.assignment_edit, name="edit"),
    path("<uuid:pk>/terminate/", views.assignment_terminate, name="terminate"),
]
