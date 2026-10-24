from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("contacts", "0001_initial")]

    operations = [
        # Django CheckConstraint cannot join related rows. This additive composite
        # FK protects the redundant customer/contact pair even outside services.
        # The referenced unique key is declared in Contact.Meta and 0001.
        migrations.RunSQL(
            sql="""
                ALTER TABLE contacts_contactpoint
                ADD CONSTRAINT point_contact_customer_fk
                FOREIGN KEY (contact_id, customer_id)
                REFERENCES contacts_contact (id, customer_id)
            """,
            reverse_sql="ALTER TABLE contacts_contactpoint DROP CONSTRAINT point_contact_customer_fk",
        ),
    ]
