from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from chat.models import UserProfile


class Command(BaseCommand):
    help = '清理未验证邮箱的超时账号：注册超过10分钟停用、超过1小时删除。超级管理员/普通管理员不受限制。'

    def handle(self, *args, **options):
        now = timezone.now()
        deleted = 0
        disabled = 0
        ok = 0
        # 只处理注册时填写了邮箱的未验证账号；存量无邮箱账号不受策略影响
        # 超级管理员 / 普通管理员（AdminUser 中启用状态的账号）由
        # profile.email_verification_status() 判定为 'ok'，绝不会被删除/停用
        for user in User.objects.exclude(email__isnull=True).exclude(email='').select_related('profile').all():
            profile, _ = UserProfile.objects.get_or_create(user=user)
            status = profile.email_verification_status()
            if status == 'deleted':
                username = user.username
                user.delete()
                deleted += 1
                self.stdout.write(f'[DELETED] {username}')
            elif status == 'disabled':
                disabled += 1
                self.stdout.write(f'[DISABLED] {user.username}')
            else:
                ok += 1
        self.stdout.write(self.style.SUCCESS(
            f'完成：删除 {deleted} 个，停用 {disabled} 个，正常 {ok} 个'
        ))
