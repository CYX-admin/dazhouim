from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    is_banned = models.BooleanField(default=False, verbose_name='是否封禁')
    is_muted = models.BooleanField(default=False, verbose_name='是否禁言')
    mute_until = models.DateTimeField(null=True, blank=True, verbose_name='禁言到期时间')
    last_login_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='最近登录IP')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    last_active = models.DateTimeField(auto_now=True, verbose_name='最后活跃时间')
    # 在线状态
    STATUS_CHOICES = [
        ('online', '在线'),
        ('away', '离开'),
        ('busy', '忙碌'),
        ('offline', '离线'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='offline', verbose_name='在线状态')
    # 邮箱验证
    email_verified = models.BooleanField(default=False, verbose_name='邮箱是否已验证')
    email_verify_token = models.CharField(max_length=64, null=True, blank=True, verbose_name='邮箱验证令牌')
    email_verify_expires = models.DateTimeField(null=True, blank=True, verbose_name='验证令牌过期时间')
    email_verify_exempt = models.BooleanField(default=False, verbose_name='是否豁免邮箱验证（管理员后台设置）')
    # 邮箱验证码（6位数字）
    email_verify_code = models.CharField(max_length=6, null=True, blank=True, verbose_name='邮箱验证码')
    email_verify_code_expires = models.DateTimeField(null=True, blank=True, verbose_name='验证码过期时间')
    # 个人资料
    nickname = models.CharField(max_length=30, blank=True, verbose_name='昵称')
    avatar_color = models.CharField(max_length=20, blank=True, verbose_name='头像颜色')
    signature = models.CharField(max_length=80, blank=True, verbose_name='个性签名')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name='头像')
    # 头衔与权限
    user_title = models.CharField(max_length=30, blank=True, null=True, verbose_name='用户头衔')
    custom_id = models.CharField(max_length=20, blank=True, null=True, unique=True, verbose_name='自定义ID')
    is_admin_panel = models.BooleanField(default=False, verbose_name='后台管理权限')

    class Meta:
        verbose_name = '用户资料'
        verbose_name_plural = '用户资料'

    def is_currently_muted(self):
        if self.is_muted and self.mute_until is None:
            return True
        if self.mute_until and self.mute_until > timezone.now():
            return True
        if self.mute_until and self.mute_until <= timezone.now():
            self.is_muted = False
            self.mute_until = None
            self.save(update_fields=['is_muted', 'mute_until'])
        return False

    def __str__(self):
        return self.user.username

    def email_verification_status(self):
        """返回邮箱验证策略状态: 'ok' | 'disabled' | 'deleted'"""
        if self.email_verify_exempt:
            return 'ok'
        if self.email_verified:
            return 'ok'
        if not self.user.email or not self.user.email.strip():
            return 'ok'
        now = timezone.now()
        joined = self.user.date_joined
        if joined is None:
            return 'ok'
        elapsed = (now - joined).total_seconds()
        if elapsed >= 3600:
            return 'deleted'
        if elapsed >= 600:
            return 'disabled'
        return 'ok'


class ChatMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='发送用户')
    content = models.TextField(max_length=2000, blank=True, verbose_name='消息内容')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='发送时间')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='发送者IP')
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies', verbose_name='回复的消息')
    attachment = models.FileField(upload_to='attachments/%Y/%m/%d/', null=True, blank=True, verbose_name='附件文件')
    attachment_name = models.CharField(max_length=255, blank=True, verbose_name='附件原始文件名')
    attachment_type = models.CharField(max_length=20, blank=True, verbose_name='附件类型(image/file)')
    is_deleted = models.BooleanField(default=False, verbose_name='是否撤回')

    class Meta:
        ordering = ['-timestamp']
        verbose_name = '聊天消息'
        verbose_name_plural = '聊天消息'

    def __str__(self):
        return f'{self.user.username}: {self.content[:50]}'


class PrivateChat(models.Model):
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chats_as_user1', verbose_name='用户1')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chats_as_user2', verbose_name='用户2')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    is_pinned = models.BooleanField(default=False, verbose_name='是否置顶(兼容旧数据)')
    is_muted = models.BooleanField(default=False, verbose_name='是否免打扰(兼容旧数据)')
    user1_pinned = models.BooleanField(default=False, verbose_name='用户1是否置顶')
    user2_pinned = models.BooleanField(default=False, verbose_name='用户2是否置顶')
    user1_muted = models.BooleanField(default=False, verbose_name='用户1是否免打扰')
    user2_muted = models.BooleanField(default=False, verbose_name='用户2是否免打扰')
    user1_hidden = models.BooleanField(default=False, verbose_name='用户1是否已删除会话(单方隐藏)')
    user2_hidden = models.BooleanField(default=False, verbose_name='用户2是否已删除会话(单方隐藏)')
    typing_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='typing_chats', verbose_name='正在输入的用户')
    typing_expires = models.DateTimeField(null=True, blank=True, verbose_name='输入状态过期时间')

    class Meta:
        unique_together = ('user1', 'user2')
        verbose_name = '私聊会话'
        verbose_name_plural = '私聊会话'

    def __str__(self):
        return f'{self.user1.username} <-> {self.user2.username}'

    def is_pinned_for(self, user):
        """按视角返回置顶状态（兼容旧数据）"""
        if user == self.user1:
            return self.user1_pinned or (self.is_pinned and self.user1.id < self.user2.id)
        if user == self.user2:
            return self.user2_pinned or (self.is_pinned and self.user2.id < self.user1.id)
        return False

    def set_pinned_for(self, user, pinned):
        if user == self.user1:
            self.user1_pinned = pinned
            self.is_pinned = False
        elif user == self.user2:
            self.user2_pinned = pinned
            self.is_pinned = False
        else:
            return
        self.save(update_fields=['user1_pinned', 'user2_pinned', 'is_pinned'])

    def is_muted_for(self, user):
        """按视角返回免打扰状态（兼容旧数据）"""
        if user == self.user1:
            return self.user1_muted or (self.is_muted and self.user1.id < self.user2.id)
        if user == self.user2:
            return self.user2_muted or (self.is_muted and self.user2.id < self.user1.id)
        return False

    def set_muted_for(self, user, muted):
        if user == self.user1:
            self.user1_muted = muted
            self.is_muted = False
        elif user == self.user2:
            self.user2_muted = muted
            self.is_muted = False
        else:
            return
        self.save(update_fields=['user1_muted', 'user2_muted', 'is_muted'])

    def is_hidden_for(self, user):
        if user == self.user1:
            return self.user1_hidden
        if user == self.user2:
            return self.user2_hidden
        return False

    def set_hidden_for(self, user, hidden):
        if user == self.user1:
            self.user1_hidden = hidden
        elif user == self.user2:
            self.user2_hidden = hidden
        else:
            return
        self.save(update_fields=['user1_hidden', 'user2_hidden'])

    @staticmethod
    def get_or_create_chat(user_a, user_b):
        if user_a.id < user_b.id:
            u1, u2 = user_a, user_b
        else:
            u1, u2 = user_b, user_a
        chat, created = PrivateChat.objects.get_or_create(user1=u1, user2=u2)
        return chat


class PrivateMessage(models.Model):
    chat = models.ForeignKey(PrivateChat, on_delete=models.CASCADE, related_name='messages', verbose_name='所属会话')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='发送者')
    content = models.TextField(max_length=2000, blank=True, verbose_name='消息内容')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='发送时间')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='发送者IP')
    is_read = models.BooleanField(default=False, verbose_name='是否已读')
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies', verbose_name='回复的消息')
    attachment = models.FileField(upload_to='attachments/%Y/%m/%d/', null=True, blank=True, verbose_name='附件文件')
    attachment_name = models.CharField(max_length=255, blank=True, verbose_name='附件原始文件名')
    attachment_type = models.CharField(max_length=20, blank=True, verbose_name='附件类型(image/file)')
    is_deleted = models.BooleanField(default=False, verbose_name='是否撤回')
    deleted_by_sender = models.BooleanField(default=False, verbose_name='发送者已单方删除')
    forwarded_from = models.CharField(max_length=50, blank=True, verbose_name='转发来源')

    class Meta:
        ordering = ['timestamp']
        verbose_name = '私聊消息'
        verbose_name_plural = '私聊消息'

    def __str__(self):
        return f'{self.sender.username}: {self.content[:50]}'


class UserLoginLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, verbose_name='用户')
    username_attempted = models.CharField(max_length=50, verbose_name='尝试用户名')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='登录IP')
    success = models.BooleanField(default=False, verbose_name='是否成功')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='登录时间')

    class Meta:
        ordering = ['-timestamp']
        verbose_name = '用户登录日志'
        verbose_name_plural = '用户登录日志'

    def __str__(self):
        return f'{self.username_attempted} - {"成功" if self.success else "失败"} @ {self.timestamp}'


# ============ 群聊 ============
class GroupChat(models.Model):
    JOIN_MODE_CHOICES = [
        ('open', '自由加入'),
        ('approval', '需审核'),
    ]
    name = models.CharField(max_length=50, verbose_name='群名称')
    description = models.CharField(max_length=200, blank=True, verbose_name='群描述')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_groups', verbose_name='群主')
    avatar = models.ImageField(upload_to='group_avatars/', null=True, blank=True, verbose_name='群头像')
    max_members = models.IntegerField(default=200, verbose_name='最大成员数')
    announcement = models.TextField(blank=True, default='', verbose_name='群公告')
    # 入群方式：open=自由加入；approval=需审核（输入群主PIN可直接入群，否则需群主审批）
    join_mode = models.CharField(max_length=10, choices=JOIN_MODE_CHOICES, default='open', verbose_name='入群方式')
    join_pin = models.CharField(max_length=16, blank=True, null=True, verbose_name='群主PIN码（输入正确PIN可直接入群）')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '群聊'
        verbose_name_plural = '群聊'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def is_owner(self, user):
        return self.owner == user

    def is_admin(self, user):
        if self.is_owner(user):
            return True
        return self.members.filter(user=user, role='admin').exists()

    def is_member(self, user):
        return self.members.filter(user=user).exists()

    def member_count(self):
        return self.members.count()


class GroupMember(models.Model):
    ROLE_CHOICES = [
        ('owner', '群主'),
        ('admin', '管理员'),
        ('member', '普通成员'),
    ]
    group = models.ForeignKey(GroupChat, on_delete=models.CASCADE, related_name='members', verbose_name='所属群')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_memberships', verbose_name='成员')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member', verbose_name='角色')
    nickname = models.CharField(max_length=30, blank=True, verbose_name='群昵称')
    joined_at = models.DateTimeField(auto_now_add=True, verbose_name='加入时间')
    is_muted = models.BooleanField(default=False, verbose_name='是否被群禁言')
    muted_until = models.DateTimeField(null=True, blank=True, verbose_name='群禁言到期时间')
    last_read_message_id = models.IntegerField(default=0, verbose_name='最后已读消息ID')

    class Meta:
        verbose_name = '群成员'
        verbose_name_plural = '群成员'
        unique_together = ('group', 'user')
        ordering = ['-role', 'joined_at']

    def __str__(self):
        return f'{self.group.name} - {self.user.username}({self.get_role_display()})'

    def is_currently_muted(self):
        if self.is_muted and self.muted_until is None:
            return True
        if self.muted_until and self.muted_until > timezone.now():
            return True
        if self.muted_until and self.muted_until <= timezone.now():
            self.is_muted = False
            self.muted_until = None
            self.save(update_fields=['is_muted', 'muted_until'])
        return False


class GroupMessage(models.Model):
    group = models.ForeignKey(GroupChat, on_delete=models.CASCADE, related_name='messages', verbose_name='所属群')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='发送者')
    content = models.TextField(max_length=2000, blank=True, verbose_name='消息内容')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='发送时间')
    is_deleted = models.BooleanField(default=False, verbose_name='是否撤回')
    attachment = models.FileField(upload_to='group_attachments/%Y/%m/%d/', null=True, blank=True, verbose_name='附件')
    attachment_name = models.CharField(max_length=255, blank=True, verbose_name='附件原始文件名')
    attachment_type = models.CharField(max_length=20, blank=True, verbose_name='附件类型')
    forwarded_from = models.CharField(max_length=50, blank=True, verbose_name='转发来源')
    mentions = models.TextField(blank=True, verbose_name='@提及用户（逗号分隔）')

    class Meta:
        verbose_name = '群消息'
        verbose_name_plural = '群消息'
        ordering = ['timestamp']

    def __str__(self):
        return f'{self.sender.username}: {self.content[:50]}'


# ============ 入群申请（需审核的群） ============
class GroupJoinRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', '待处理'),
        ('approved', '已通过'),
        ('rejected', '已拒绝'),
    ]
    group = models.ForeignKey(GroupChat, on_delete=models.CASCADE, related_name='join_requests', verbose_name='所属群')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_join_requests', verbose_name='申请人')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    message = models.CharField(max_length=200, blank=True, verbose_name='申请留言')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='申请时间')
    handled_at = models.DateTimeField(null=True, blank=True, verbose_name='处理时间')

    class Meta:
        verbose_name = '入群申请'
        verbose_name_plural = '入群申请'
        unique_together = ('group', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} 申请加入 {self.group.name}（{self.get_status_display()}）'


# ============ 收藏 ============
class Favorite(models.Model):
    MESSAGE_TYPE_CHOICES = [
        ('private', '私聊消息'),
        ('group', '群聊消息'),
        ('global', '公共消息'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites', verbose_name='收藏者')
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES, verbose_name='消息类型')
    message_content = models.TextField(blank=True, verbose_name='消息内容')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='favorited_by', verbose_name='发送者')
    sender_username = models.CharField(max_length=150, blank=True, verbose_name='发送者用户名（冗余）')
    attachment_url = models.URLField(max_length=500, blank=True, verbose_name='附件链接')
    attachment_name = models.CharField(max_length=255, blank=True, verbose_name='附件名称')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='收藏时间')

    class Meta:
        verbose_name = '消息收藏'
        verbose_name_plural = '消息收藏'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} 收藏了 {self.sender_username} 的消息'


# ============ 黑名单 ============
class Blacklist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blacklisted', verbose_name='用户')
    blocked_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_by', verbose_name='被拉黑用户')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='拉黑时间')

    class Meta:
        verbose_name = '黑名单'
        verbose_name_plural = '黑名单'
        unique_together = ('user', 'blocked_user')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} 拉黑了 {self.blocked_user.username}'


# ============ IP黑名单 ============
class IPBlacklist(models.Model):
    ip_address = models.GenericIPAddressField(unique=True, verbose_name='IP地址')
    reason = models.CharField(max_length=255, blank=True, verbose_name='封禁原因')
    is_active = models.BooleanField(default=True, verbose_name='是否生效')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = 'IP黑名单'
        verbose_name_plural = 'IP黑名单'

    def __str__(self):
        return self.ip_address
