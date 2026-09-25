from django.db import models
from django.contrib.auth.hashers import make_password, check_password

class AdminUser(models.Model):
    ROLE_CHOICES = [
        ('super', '超级管理员'),
        ('normal', '普通管理员'),
    ]
    username = models.CharField(max_length=50, unique=True, verbose_name='用户名')
    password_hash = models.CharField(max_length=255, verbose_name='密码哈希')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='normal', verbose_name='角色')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '管理员账号'
        verbose_name_plural = '管理员账号'

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password_hash)

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'

class IPBlacklist(models.Model):
    ip_address = models.GenericIPAddressField(unique=True, verbose_name='IP地址')
    reason = models.CharField(max_length=255, blank=True, verbose_name='封禁原因')
    is_active = models.BooleanField(default=True, verbose_name='是否生效')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    created_by = models.ForeignKey(AdminUser, on_delete=models.SET_NULL, null=True, verbose_name='创建者')

    class Meta:
        verbose_name = 'IP黑名单'
        verbose_name_plural = 'IP黑名单'

    def __str__(self):
        return self.ip_address

class AdminLoginLog(models.Model):
    admin = models.ForeignKey(AdminUser, on_delete=models.CASCADE, null=True, verbose_name='管理员')
    username_attempted = models.CharField(max_length=50, verbose_name='尝试用户名')
    ip_address = models.GenericIPAddressField(verbose_name='登录IP')
    success = models.BooleanField(default=False, verbose_name='是否成功')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='登录时间')

    class Meta:
        ordering = ['-timestamp']
        verbose_name = '管理员登录日志'
        verbose_name_plural = '管理员登录日志'

    def __str__(self):
        return f'{self.username_attempted} - {"成功" if self.success else "失败"} @ {self.timestamp}'
