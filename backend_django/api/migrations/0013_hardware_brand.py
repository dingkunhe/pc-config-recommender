from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_postattachment_postimage_commentattachment_commentimage'),
    ]

    operations = [
        migrations.AddField(
            model_name='hardware',
            name='brand',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
    ]
