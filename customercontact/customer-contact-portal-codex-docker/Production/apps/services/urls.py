from django.urls import path

from . import views

app_name = "services"
urlpatterns = [
    path("", views.catalog_list, name="list"),
    path("new/", views.catalog_create, name="create"),
    path("<uuid:pk>/", views.catalog_detail, name="detail"),
    path("<uuid:pk>/edit/", views.catalog_edit, name="edit"),
    path("<uuid:pk>/archive/", views.catalog_status, {"active": False}, name="archive"),
    path("<uuid:pk>/restore/", views.catalog_status, {"active": True}, name="restore"),
]
