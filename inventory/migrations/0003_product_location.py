from django.db import migrations, models
import django.db.models.deletion


def link_existing_products_to_locations(apps, schema_editor):
    Product = apps.get_model("inventory", "Product")
    Stock = apps.get_model("inventory", "Stock")

    for product in Product.objects.filter(location__isnull=True):
        stock_locations = list(
            Stock.objects.filter(product=product)
            .values_list("location_id", flat=True)
            .distinct()[:2]
        )
        if len(stock_locations) == 1:
            product.location_id = stock_locations[0]
            product.save(update_fields=["location"])


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0002_product_product_price_gt_zero_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="products",
                to="inventory.location",
            ),
        ),
        migrations.RunPython(link_existing_products_to_locations, migrations.RunPython.noop),
    ]
