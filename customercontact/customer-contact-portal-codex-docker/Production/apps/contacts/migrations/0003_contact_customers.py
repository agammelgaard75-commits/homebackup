"""Add membership rows, then backfill every existing contact without altering it."""
import django.db.models.deletion
import uuid
from django.db import migrations, models


def backfill_legacy_links(apps, schema_editor):
    Contact = apps.get_model("contacts", "Contact")
    ContactCustomer = apps.get_model("contacts", "ContactCustomer")
    database = schema_editor.connection.alias
    batch = []
    for contact in Contact.objects.using(database).only("id", "customer_id").iterator(chunk_size=500):
        batch.append(ContactCustomer(contact_id=contact.pk, customer_id=contact.customer_id, is_active=True))
        if len(batch) == 500:
            ContactCustomer.objects.using(database).bulk_create(batch, batch_size=500)
            batch.clear()
    if batch:
        ContactCustomer.objects.using(database).bulk_create(batch, batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("contacts", "0002_contact_point_customer_integrity")]

    operations = [
        migrations.CreateModel(
            name="ContactCustomer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("contact", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="customer_links", to="contacts.contact")),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="contact_links", to="customers.customer")),
            ],
            options={
                "ordering": ["customer__name", "id"],
                "constraints": [models.UniqueConstraint(fields=["contact", "customer"], name="contact_customer_pair_unique")],
                "indexes": [models.Index(fields=["customer", "is_active"], name="contact_link_customer_active")],
            },
        ),
        migrations.RunPython(backfill_legacy_links),
    ]
