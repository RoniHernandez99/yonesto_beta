# Generated by Django 4.1.5 on 2023-03-25 01:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0002_product_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="userclient",
            name="email",
            field=models.EmailField(
                blank=True, max_length=254, null=True, verbose_name="Email: "
            ),
        ),
    ]
