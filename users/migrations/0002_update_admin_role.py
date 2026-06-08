from django.db import migrations


def forward(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role="super_admin").update(role="admin")
    User.objects.filter(is_superuser=True).update(role="admin")


def backward(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role="admin").update(role="super_admin")


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
