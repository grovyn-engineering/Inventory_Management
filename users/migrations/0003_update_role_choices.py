from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_update_admin_role"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("admin", "Admin"),
                    ("manager", "Manager"),
                    ("worker", "Worker"),
                ],
                db_index=True,
                default="worker",
                max_length=20,
            ),
        ),
    ]
