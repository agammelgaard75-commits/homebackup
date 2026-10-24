"""Move personless customer details into retained, associated contact records."""
from django.db import migrations, models


def attach_general_points(apps, schema_editor):
    Contact = apps.get_model("contacts", "Contact")
    ContactCustomer = apps.get_model("contacts", "ContactCustomer")
    ContactPoint = apps.get_model("contacts", "ContactPoint")
    database = schema_editor.connection.alias
    orphan_points = ContactPoint.objects.using(database).filter(contact__isnull=True)
    customer_ids = list(orphan_points.order_by().values_list("customer_id", flat=True).distinct())
    for customer_id in customer_ids:
        points = orphan_points.filter(customer_id=customer_id)
        placeholders = list(Contact.objects.using(database).filter(
            customer_id=customer_id, full_name__iexact="General Contact",
        ).order_by("pk")[:2])
        reusable = None
        if len(placeholders) == 1:
            candidate = placeholders[0]
            links = ContactCustomer.objects.using(database).filter(contact_id=candidate.pk, is_active=True)
            if not ContactPoint.objects.using(database).filter(contact_id=candidate.pk).exists() and \
                    links.count() == 1 and links.filter(customer_id=customer_id).exists():
                reusable = candidate
        if reusable:
            general_contact = reusable
            Contact.objects.using(database).filter(pk=general_contact.pk).update(is_general=True)
        else:
            name = "Imported General Contact" if placeholders else "General Contact"
            general_contact = Contact.objects.using(database).create(
                customer_id=customer_id,
                full_name=name,
                contact_type="other",
                is_general=True,
                is_active=points.filter(is_active=True).exists(),
            )
            ContactCustomer.objects.using(database).create(contact_id=general_contact.pk, customer_id=customer_id)
        points.update(contact_id=general_contact.pk)
    if orphan_points.exists():
        raise RuntimeError("Unassigned customer contact details remain after migration.")


class Migration(migrations.Migration):
    dependencies = [("contacts", "0003_contact_customers")]

    operations = [
        migrations.AddField(
            model_name="contact",
            name="is_general",
            field=models.BooleanField(default=False, help_text="Use for a team or shared contact such as Support Desk or Reception."),
        ),
        migrations.RunPython(attach_general_points),
    ]
