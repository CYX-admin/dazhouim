from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0012_im_ui'),
    ]

    operations = [
        migrations.CreateModel(
            name='IPBlacklist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(unique=True, verbose_name='IP地址')),
                ('reason', models.CharField(blank=True, max_length=255, verbose_name='封禁原因')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否生效')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
            ],
            options={
                'verbose_name': 'IP黑名单',
                'verbose_name_plural': 'IP黑名单',
            },
        ),
    ]
