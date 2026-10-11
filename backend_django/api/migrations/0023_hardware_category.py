from django.db import migrations, models


def infer_category(name, desc):
    text = f"{name or ''} {desc or ''}".lower()

    rules = [
        ('cpu', ['cpu', '处理器', '酷睿', '锐龙', 'ryzen', 'i3', 'i5', 'i7', 'i9']),
        ('gpu', ['显卡', 'gpu', 'geforce', 'radeon', 'rtx', 'gtx']),
        ('motherboard', ['主板', 'motherboard', '芯片组', 'b760', 'x670', 'z790']),
        ('memory', ['内存', 'ddr4', 'ddr5', 'memory']),
        ('storage', ['硬盘', 'ssd', '固态', 'nvme', 'hdd', '机械盘', 'storage']),
        ('psu', ['电源', '80plus', '额定功率', 'power supply', 'psu']),
        ('case', ['机箱', '中塔', 'itx', 'matx', 'atx case']),
        ('cooler', ['散热', '风冷', '水冷', '热管', 'cooler']),
        ('laptop', ['笔记本', 'notebook', 'matebook', 'magicbook', 'laptop']),
        ('monitor', ['显示器', 'monitor', 'lcd', 'ips', 'oled']),
        ('keyboard', ['键盘', 'keyboard', '轴体']),
        ('mouse', ['鼠标', 'mouse', 'dpi']),
        ('headphone', ['耳机', 'headphone', 'headset']),
        ('speaker', ['音箱', 'speaker', '声道']),
    ]

    for cat, keywords in rules:
        if any(k in text for k in keywords):
            return cat
    return 'other'


def forwards(apps, schema_editor):
    Hardware = apps.get_model('api', 'Hardware')
    for hw in Hardware.objects.all().iterator():
        hw.category = infer_category(hw.name, hw.description)
        hw.save(update_fields=['category'])


def backwards(apps, schema_editor):
    Hardware = apps.get_model('api', 'Hardware')
    Hardware.objects.all().update(category='other')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_auditapiconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='hardware',
            name='category',
            field=models.CharField(
                choices=[
                    ('cpu', 'CPU'),
                    ('gpu', '显卡'),
                    ('motherboard', '主板'),
                    ('memory', '内存'),
                    ('storage', '硬盘'),
                    ('psu', '电源'),
                    ('case', '机箱'),
                    ('cooler', '散热器'),
                    ('laptop', '笔记本电脑'),
                    ('monitor', '显示器'),
                    ('keyboard', '键盘'),
                    ('mouse', '鼠标'),
                    ('headphone', '耳机'),
                    ('speaker', '音箱'),
                    ('other', '其他'),
                ],
                default='other',
                db_index=True,
                max_length=30,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
