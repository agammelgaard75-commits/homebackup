from django.urls import path

from . import views

app_name = "customers"
urlpatterns = [
    path("", views.customer_list, name="list"),
    path("new/", views.customer_create, name="create"),
    path("import/", views.customer_import, name="import"),
    path("import/example/", views.customer_import_reference, {"asset": "example"}, name="import_example"),
    path("import/schema/", views.customer_import_reference, {"asset": "schema"}, name="import_schema"),
    path("import/guide/", views.customer_import_reference, {"asset": "guide"}, name="import_guide"),
    path("<uuid:pk>/", views.customer_detail, name="detail"),
    path("<uuid:pk>/edit/", views.customer_edit, name="edit"),
    path("<uuid:pk>/archive/", views.customer_archive, name="archive"),
]
