from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_recommendedscheme'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommentAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='comments/attachments/%Y/%m/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='CommentImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='comments/images/%Y/%m/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='PostAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='posts/attachments/%Y/%m/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='PostImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='posts/images/%Y/%m/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddField(
            model_name='commentimage',
            name='comment',
            field=models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='images', to='api.comment'),
        ),
        migrations.AddField(
            model_name='commentattachment',
            name='comment',
            field=models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='attachments', to='api.comment'),
        ),
        migrations.AddField(
            model_name='postimage',
            name='post',
            field=models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='images', to='api.post'),
        ),
        migrations.AddField(
            model_name='postattachment',
            name='post',
            field=models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='attachments', to='api.post'),
        ),
    ]
