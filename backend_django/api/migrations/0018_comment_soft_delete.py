from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_replynotification'),
    ]

    operations = [
        migrations.AddField(
            model_name='comment',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='comment',
            name='is_deleted',
            field=models.BooleanField(default=False),
        ),
    ]
