from django.urls import path

from . import views

app_name = "contacts"
urlpatterns = [
    path("", views.contact_list, name="list"),
    path("new/", views.contact_form, name="create"),
    path("general/new/", views.legacy_general_create, name="general_create"),
    path("general/<uuid:point_pk>/edit/", views.legacy_general_action, {"action": "edit"}, name="general_edit"),
    path("general/<uuid:point_pk>/archive/", views.legacy_general_action, {"action": "archive"}, name="general_archive"),
    path("general/<uuid:point_pk>/restore/", views.legacy_general_action, {"action": "restore"}, name="general_restore"),
    path("<uuid:pk>/", views.contact_detail, name="detail"),
    path("<uuid:pk>/edit/", views.contact_form, name="edit"),
    path("<uuid:pk>/archive/", views.contact_status, {"is_active": False}, name="archive"),
    path("<uuid:pk>/restore/", views.contact_status, {"is_active": True}, name="restore"),
    path("<uuid:contact_pk>/details/new/", views.point_form, name="point_create"),
    path("<uuid:contact_pk>/details/<uuid:point_pk>/edit/", views.point_form, name="point_edit"),
    path("<uuid:contact_pk>/details/<uuid:point_pk>/archive/", views.point_status, {"is_active": False}, name="point_archive"),
    path("<uuid:contact_pk>/details/<uuid:point_pk>/restore/", views.point_status, {"is_active": True}, name="point_restore"),
]
