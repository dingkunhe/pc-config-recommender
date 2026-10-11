from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0023_hardware_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='PromptConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recommend_prompt', models.TextField(blank=True, default='')),
                ('audit_prompt', models.TextField(blank=True, default='')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
