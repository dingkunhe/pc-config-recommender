from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0019_merge_0018_comment_soft_delete_0018_systemnotification'),
    ]

    operations = [
        migrations.AddField(
            model_name='post',
            name='board',
            field=models.CharField(choices=[('square', '交流广场'), ('qa', 'Q&A'), ('system', '系统通知')], default='square', max_length=20),
        ),
    ]
