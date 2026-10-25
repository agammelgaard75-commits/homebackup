"""Make Technical the default for new contacts without changing existing rows."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("contacts", "0005_require_contact_for_details")]

    operations = [
        migrations.AlterField(
            model_name="contact",
            name="contact_type",
            field=models.CharField(choices=[("technical", "Technical"), ("management", "Management"),
                                            ("billing", "Billing"), ("support", "Support"), ("other", "Other")],
                                   default="technical", max_length=10),
        ),
    ]
