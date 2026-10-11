from django.db import migrations, models


def mark_existing_safe(apps, schema_editor):
    Post = apps.get_model('api', 'Post')
    Comment = apps.get_model('api', 'Comment')
    Post.objects.all().update(ai_moderation_status='safe')
    Comment.objects.all().update(ai_moderation_status='safe')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0024_promptconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='post',
            name='ai_moderation_status',
            field=models.CharField(db_index=True, default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='post',
            name='ai_moderation_reason',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='post',
            name='ai_moderation_checked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='post',
            name='ai_moderation_flagged_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='comment',
            name='ai_moderation_status',
            field=models.CharField(db_index=True, default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='comment',
            name='ai_moderation_reason',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='comment',
            name='ai_moderation_checked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='comment',
            name='ai_moderation_flagged_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(mark_existing_safe, migrations.RunPython.noop),
    ]
