# Migration for IM UI enhancements
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0011_chat_enhancement'),
    ]

    operations = [
        migrations.AddField(
            model_name='privatechat',
            name='typing_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='typing_chats', to='auth.user', verbose_name='正在输入的用户'),
        ),
        migrations.AddField(
            model_name='privatechat',
            name='typing_expires',
            field=models.DateTimeField(blank=True, null=True, verbose_name='输入状态过期时间'),
        ),
        migrations.AddField(
            model_name='groupmember',
            name='last_read_message_id',
            field=models.IntegerField(default=0, verbose_name='最后已读消息ID'),
        ),
    ]
