from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_post_board'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='avatar',
            field=models.FileField(blank=True, null=True, upload_to='avatars/%Y/%m/'),
        ),
    ]
