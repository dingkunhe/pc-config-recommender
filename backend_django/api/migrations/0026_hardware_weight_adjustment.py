from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0025_post_comment_ai_moderation_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='hardware',
            name='recommend_weight',
            field=models.FloatField(db_index=True, default=1.0),
        ),
        migrations.AddField(
            model_name='hardware',
            name='weight_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='HardwareWeightAdjustmentLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_type', models.CharField(choices=[('post', 'post'), ('comment', 'comment')], max_length=10)),
                ('source_id', models.IntegerField(db_index=True)),
                ('source_excerpt', models.TextField(blank=True, default='')),
                ('mention_text', models.CharField(blank=True, default='', max_length=255)),
                ('sentiment', models.CharField(choices=[('positive', 'positive'), ('negative', 'negative'), ('neutral', 'neutral')], default='neutral', max_length=20)),
                ('confidence', models.FloatField(default=0.5)),
                ('delta', models.FloatField(default=0.0)),
                ('weight_before', models.FloatField(default=1.0)),
                ('weight_after', models.FloatField(default=1.0)),
                ('reason', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('hardware', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='weight_adjust_logs', to='api.hardware')),
            ],
        ),
    ]
