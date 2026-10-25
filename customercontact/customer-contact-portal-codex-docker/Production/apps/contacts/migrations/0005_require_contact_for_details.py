"""Enforce contact ownership after the data migration has committed."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("contacts", "0004_unify_general_contact_points")]

    operations = [
        migrations.RemoveConstraint(model_name="contactpoint", name="general_primary_point_unique"),
        migrations.AlterField(
            model_name="contactpoint",
            name="contact",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="points", to="contacts.contact"),
        ),
    ]
