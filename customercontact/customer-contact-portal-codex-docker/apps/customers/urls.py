from django.urls import path

from . import views

app_name = "customers"
urlpatterns = [
    path("", views.customer_list, name="list"),
    path("new/", views.customer_create, name="create"),
    path("<uuid:pk>/", views.customer_detail, name="detail"),
    path("<uuid:pk>/edit/", views.customer_edit, name="edit"),
    path("<uuid:pk>/archive/", views.customer_archive, name="archive"),
]
