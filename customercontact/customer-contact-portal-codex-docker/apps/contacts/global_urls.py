from django.urls import path
from . import views

app_name = "global_contacts"
urlpatterns = [
    path("", views.global_contact_list, name="list"),
    path("new/", views.global_contact_create, name="create"),
    path("<uuid:pk>/", views.global_contact_detail, name="detail"),
    path("<uuid:pk>/edit/", views.global_contact_edit, name="edit"),
    path("<uuid:pk>/archive/", views.global_contact_archive, name="archive"),
    path("<uuid:pk>/restore/", views.global_contact_restore, name="restore"),
]
