# Generated manually for chat enhancement features
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0010_userprofile_custom_id_userprofile_is_admin_panel_and_more'),
    ]

    operations = [
        # UserProfile: add status field
        migrations.AddField(
            model_name='userprofile',
            name='status',
            field=models.CharField(
                choices=[('online', '在线'), ('away', '离开'), ('busy', '忙碌'), ('offline', '离线')],
                default='offline',
                max_length=10,
                verbose_name='在线状态',
            ),
        ),
        # PrivateChat: add is_pinned and is_muted
        migrations.AddField(
            model_name='privatechat',
            name='is_pinned',
            field=models.BooleanField(default=False, verbose_name='是否置顶'),
        ),
        migrations.AddField(
            model_name='privatechat',
            name='is_muted',
            field=models.BooleanField(default=False, verbose_name='是否免打扰'),
        ),
        # GroupMember: add is_muted and muted_until
        migrations.AddField(
            model_name='groupmember',
            name='is_muted',
            field=models.BooleanField(default=False, verbose_name='是否被群禁言'),
        ),
        migrations.AddField(
            model_name='groupmember',
            name='muted_until',
            field=models.DateTimeField(blank=True, null=True, verbose_name='群禁言到期时间'),
        ),
        # Favorite model
        migrations.CreateModel(
            name='Favorite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message_type', models.CharField(
                    choices=[('private', '私聊消息'), ('group', '群聊消息'), ('global', '公共消息')],
                    max_length=10,
                    verbose_name='消息类型',
                )),
                ('message_content', models.TextField(blank=True, verbose_name='消息内容')),
                ('sender_username', models.CharField(blank=True, max_length=150, verbose_name='发送者用户名（冗余）')),
                ('attachment_url', models.URLField(blank=True, max_length=500, verbose_name='附件链接')),
                ('attachment_name', models.CharField(blank=True, max_length=255, verbose_name='附件名称')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='收藏时间')),
                ('sender', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='favorited_by', to='auth.user', verbose_name='发送者',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='favorites', to='auth.user', verbose_name='收藏者',
                )),
            ],
            options={
                'verbose_name': '消息收藏',
                'verbose_name_plural': '消息收藏',
                'ordering': ['-created_at'],
            },
        ),
        # Blacklist model
        migrations.CreateModel(
            name='Blacklist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='拉黑时间')),
                ('blocked_user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='blocked_by', to='auth.user', verbose_name='被拉黑用户',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='blacklisted', to='auth.user', verbose_name='用户',
                )),
            ],
            options={
                'verbose_name': '黑名单',
                'verbose_name_plural': '黑名单',
                'unique_together': {('user', 'blocked_user')},
                'ordering': ['-created_at'],
            },
        ),
    ]
