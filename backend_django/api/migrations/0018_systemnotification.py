from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_replynotification'),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_type', models.CharField(choices=[('post', 'Post'), ('comment', 'Comment')], max_length=20)),
                ('target_id', models.IntegerField()),
                ('source_post_id', models.IntegerField(blank=True, null=True)),
                ('title', models.CharField(default='系统通知', max_length=255)),
                ('content', models.TextField(blank=True, default='')),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='system_notifications', to='auth.user')),
            ],
        ),
    ]
