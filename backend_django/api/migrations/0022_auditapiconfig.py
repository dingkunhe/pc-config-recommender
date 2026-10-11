from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_profile_avatar'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditApiConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('api_key', models.CharField(max_length=255)),
                ('model_name', models.CharField(max_length=100)),
                ('base_url', models.CharField(default='https://api.siliconflow.cn/v1/chat/completions', max_length=255)),
                ('is_primary', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
            ],
        ),
    ]
