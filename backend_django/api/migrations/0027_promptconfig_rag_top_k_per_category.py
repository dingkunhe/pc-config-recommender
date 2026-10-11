from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0026_hardware_weight_adjustment'),
    ]

    operations = [
        migrations.AddField(
            model_name='promptconfig',
            name='rag_top_k_per_category',
            field=models.PositiveIntegerField(default=5),
        ),
    ]
