from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_comment_parent_comment'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReplyNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_type', models.CharField(choices=[('post', 'Post'), ('comment', 'Comment')], max_length=20)),
                ('target_id', models.IntegerField()),
                ('source_post_id', models.IntegerField(blank=True, null=True)),
                ('reply_comment_id', models.IntegerField(blank=True, null=True)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sent_reply_notifications', to='auth.user')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reply_notifications', to='auth.user')),
            ],
        ),
    ]
