from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0013_ip_blacklist'),
    ]

    operations = [
        migrations.AddField(
            model_name='privatemessage',
            name='forwarded_from',
            field=models.CharField(blank=True, max_length=50, verbose_name='转发来源'),
        ),
        migrations.AddField(
            model_name='groupmessage',
            name='forwarded_from',
            field=models.CharField(blank=True, max_length=50, verbose_name='转发来源'),
        ),
        migrations.AddField(
            model_name='groupmessage',
            name='mentions',
            field=models.TextField(blank=True, verbose_name='@提及用户（逗号分隔）'),
        ),
    ]
