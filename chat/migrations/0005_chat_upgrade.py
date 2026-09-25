# Generated manually for chat feature upgrades

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("chat", "0004_userprofile_email_verify_exempt"),
    ]

    operations = [
        # 邮箱验证码（6位数字）
        migrations.AddField(
            model_name="userprofile",
            name="email_verify_code",
            field=models.CharField(
                blank=True, max_length=6, null=True, verbose_name="邮箱验证码"
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="email_verify_code_expires",
            field=models.DateTimeField(blank=True, null=True, verbose_name="验证码过期时间"),
        ),
        # 昵称与头像颜色
        migrations.AddField(
            model_name="userprofile",
            name="nickname",
            field=models.CharField(blank=True, max_length=30, verbose_name="昵称"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="avatar_color",
            field=models.CharField(blank=True, max_length=20, verbose_name="头像颜色"),
        ),
        # 公共消息附件
        migrations.AddField(
            model_name="chatmessage",
            name="attachment",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="attachments/%Y/%m/%d/",
                verbose_name="附件文件",
            ),
        ),
        migrations.AddField(
            model_name="chatmessage",
            name="attachment_name",
            field=models.CharField(blank=True, max_length=255, verbose_name="附件原始文件名"),
        ),
        migrations.AddField(
            model_name="chatmessage",
            name="attachment_type",
            field=models.CharField(blank=True, max_length=20, verbose_name="附件类型(image/file)"),
        ),
        # 私聊消息附件
        migrations.AddField(
            model_name="privatemessage",
            name="attachment",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="attachments/%Y/%m/%d/",
                verbose_name="附件文件",
            ),
        ),
        migrations.AddField(
            model_name="privatemessage",
            name="attachment_name",
            field=models.CharField(blank=True, max_length=255, verbose_name="附件原始文件名"),
        ),
        migrations.AddField(
            model_name="privatemessage",
            name="attachment_type",
            field=models.CharField(blank=True, max_length=20, verbose_name="附件类型(image/file)"),
        ),
    ]
