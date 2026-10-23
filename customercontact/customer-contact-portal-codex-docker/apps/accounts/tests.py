from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from .permissions import permission_required

User = get_user_model()


class AccountsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.users = {}
        for role in ("Viewer", "Editor", "Administrator"):
            user = User.objects.create_user(username=role.lower(), password="test-only-Strong-Password-762")
            user.groups.add(Group.objects.get(name=role))
            cls.users[role] = user
        cls.unassigned = User.objects.create_user(username="unassigned", password="test-only-Strong-Password-762")
        cls.superuser = User.objects.create_superuser(username="superuser", password="test-only-Strong-Password-762")

    def test_anonymous_redirects_to_login(self):
        response = self.client.get("/", secure=True)
        self.assertRedirects(response, "/accounts/login/?next=/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/admin/", secure=True).status_code, 302)

    def test_login_valid_invalid_inactive_and_logout(self):
        url = reverse("accounts:login")
        self.assertContains(self.client.get(url, secure=True), "Sign in")
        self.assertContains(self.client.post(url, {"username": "viewer", "password": "wrong"}, secure=True), "Please enter a correct")
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post(url, {"username": "viewer", "password": "test-only-Strong-Password-762"}, secure=True)
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertTrue(response.cookies["sessionid"]["secure"])
        self.assertEqual(self.client.get(reverse("accounts:logout"), secure=True).status_code, 405)
        self.assertRedirects(self.client.post(reverse("accounts:logout"), secure=True), url, fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        user = self.users["Viewer"]
        user.is_active = False
        user.save()
        self.client.post(url, {"username": "viewer", "password": "test-only-Strong-Password-762"}, secure=True)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_rejects_external_redirect(self):
        response = self.client.post(reverse("accounts:login"), {
            "username": "viewer", "password": "test-only-Strong-Password-762", "next": "https://evil.invalid/",
        }, secure=True)
        self.assertRedirects(response, "/", fetch_redirect_response=False)

    def test_csrf_login_and_logout(self):
        client = Client(enforce_csrf_checks=True, HTTP_ORIGIN="https://testserver")
        url = reverse("accounts:login")
        self.assertEqual(client.post(url, {}, secure=True).status_code, 403)
        response = client.get(url, secure=True)
        self.assertTrue(response.cookies["csrftoken"]["secure"])
        token = client.cookies["csrftoken"].value
        response = client.post(url, {"username": "viewer", "password": "test-only-Strong-Password-762", "csrfmiddlewaretoken": token}, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.post(reverse("accounts:logout"), secure=True).status_code, 403)
        response = client.post(reverse("accounts:logout"), {"csrfmiddlewaretoken": client.cookies["csrftoken"].value}, secure=True)
        self.assertEqual(response.status_code, 302)

    def test_roles_and_navigation(self):
        for role, user in self.users.items():
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get("/", secure=True)
                self.assertContains(response, f"{role} access")
                self.assertEqual(user.has_perm("accounts.edit_portal"), role != "Viewer")
                self.assertEqual(user.has_perm("accounts.administer_portal"), role == "Administrator")
                if role == "Administrator":
                    self.assertContains(response, "Administration")
                    self.assertEqual(self.client.get("/admin/", secure=True).status_code, 200)
                else:
                    self.assertNotContains(response, "Administration")
                    self.assertEqual(self.client.get("/admin/", secure=True).status_code, 302)
                    self.assertEqual(self.client.post("/admin/accounts/user/add/", {}, secure=True).status_code, 302)

    def test_no_role_and_staff_flag_do_not_grant_access(self):
        self.unassigned.is_staff = True
        self.unassigned.save()
        self.client.force_login(self.unassigned)
        self.assertEqual(self.client.get("/", secure=True).status_code, 403)
        self.assertEqual(self.client.get("/admin/", secure=True).status_code, 302)

    def test_mutation_gate_checks_permissions_on_server(self):
        from django.core.exceptions import PermissionDenied

        view = permission_required("accounts.edit_portal")(lambda request: HttpResponse("ok"))
        for role, user in self.users.items():
            request = RequestFactory().post("/future-action/")
            request.user = user
            if role == "Viewer":
                with self.assertRaises(PermissionDenied):
                    view(request)
            else:
                self.assertEqual(view(request).status_code, 200)
        user = self.users["Editor"]
        user.is_active = False
        request.user = user
        with self.assertRaises(PermissionDenied):
            view(request)

    def test_setup_roles_is_idempotent_and_preserves_membership(self):
        group = Group.objects.get(name="Viewer")
        group.permissions.add(Permission.objects.get(content_type__app_label="accounts", codename="change_user"))
        call_command("setup_roles", verbosity=0)
        call_command("setup_roles", verbosity=0)
        self.assertEqual(Group.objects.count(), 3)
        self.assertTrue(self.users["Viewer"].groups.filter(pk=group.pk).exists())
        self.assertEqual(set(group.permissions.values_list("codename", flat=True)), {"access_portal", "view_customer"})

    def test_administrator_can_create_user_with_role_but_not_superuser(self):
        self.client.force_login(self.users["Administrator"])
        url = reverse("admin:accounts_user_add")
        self.assertEqual(self.client.get(url, secure=True).status_code, 200)
        response = self.client.post(url, {
            "username": "new-staff", "password1": "new-test-Password-6428", "password2": "new-test-Password-6428",
            "groups": [Group.objects.get(name="Viewer").pk],
            "is_superuser": "on", "is_staff": "on", "_save": "Save",
        }, secure=True)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="new-staff")
        self.assertTrue(user.check_password("new-test-Password-6428"))
        self.assertTrue(user.has_perm("accounts.access_portal"))
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

    def test_administrator_cannot_escalate_through_user_form(self):
        self.client.force_login(self.users["Administrator"])
        viewer = self.users["Viewer"]
        url = reverse("admin:accounts_user_change", args=[viewer.pk])
        response = self.client.post(url, {
            "username": viewer.username, "is_active": "on", "groups": [Group.objects.get(name="Editor").pk],
            "is_superuser": "on", "is_staff": "on", "user_permissions": [Permission.objects.get(codename="delete_user").pk], "_save": "Save",
        }, secure=True)
        self.assertEqual(response.status_code, 302)
        viewer.refresh_from_db()
        self.assertFalse(viewer.is_superuser)
        self.assertFalse(viewer.is_staff)
        self.assertFalse(viewer.user_permissions.exists())
        self.assertTrue(viewer.groups.filter(name="Editor").exists())
        self.assertEqual(self.client.get(reverse("admin:accounts_user_change", args=[self.superuser.pk]), secure=True).status_code, 302)
        self.assertEqual(self.client.post(reverse("admin:auth_user_password_change", args=[self.superuser.pk]), {}, secure=True).status_code, 404)
        self.assertEqual(self.client.post(reverse("admin:accounts_user_delete", args=[viewer.pk]), {}, secure=True).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:auth_group_changelist"), secure=True).status_code, 403)

    def test_unmanaged_group_cannot_be_assigned_by_administrator(self):
        group = Group.objects.create(name="Unmanaged")
        self.client.force_login(self.users["Administrator"])
        response = self.client.post(reverse("admin:accounts_user_add"), {
            "username": "invalid-role", "password1": "new-test-Password-6428", "password2": "new-test-Password-6428",
            "groups": [group.pk], "_save": "Save",
        }, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="invalid-role").exists())

    def test_superuser_can_bootstrap_roles(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get("/", secure=True).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:auth_group_changelist"), secure=True).status_code, 200)

    def test_admin_login_uses_administrator_permission_without_staff_flag(self):
        for role in ("Viewer", "Editor", "Administrator"):
            self.client.logout()
            response = self.client.post(reverse("admin:login"), {
                "username": role.lower(), "password": "test-only-Strong-Password-762", "next": "/admin/",
            }, secure=True)
            self.assertEqual(response.status_code, 302 if role == "Administrator" else 200)
            self.assertEqual("_auth_user_id" in self.client.session, role == "Administrator")
