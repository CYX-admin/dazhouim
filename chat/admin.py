from django.contrib import admin
from .models import (
    UserProfile, ChatMessage, PrivateChat, PrivateMessage,
    UserLoginLog, GroupChat, GroupMember, GroupMessage,
    Favorite, Blacklist
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'user_title', 'custom_id', 'is_admin_panel', 'is_banned', 'is_muted', 'status']
    list_filter = ['is_admin_panel', 'is_banned', 'is_muted', 'status']
    search_fields = ['user__username', 'user_title', 'custom_id']
    fieldsets = (
        ('基本信息', {'fields': ['user', 'nickname', 'signature', 'avatar', 'avatar_color', 'status']}),
        ('头衔与权限', {'fields': ['user_title', 'custom_id', 'is_admin_panel']}),
        ('状态管理', {'fields': ['is_banned', 'is_muted', 'mute_until']}),
        ('邮箱验证', {'fields': ['email_verified', 'email_verify_exempt']}),
    )


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'content_short', 'timestamp', 'ip_address', 'is_deleted']
    list_filter = ['timestamp', 'is_deleted']
    search_fields = ['content', 'user__username', 'ip_address']
    readonly_fields = ['timestamp']
    list_per_page = 50

    def content_short(self, obj):
        return obj.content[:60] + ('...' if len(obj.content) > 60 else '')
    content_short.short_description = '消息内容'


@admin.register(PrivateChat)
class PrivateChatAdmin(admin.ModelAdmin):
    list_display = ['id', 'user1', 'user2', 'is_pinned', 'is_muted', 'created_at']
    list_filter = ['is_pinned', 'is_muted', 'created_at']
    search_fields = ['user1__username', 'user2__username']
    readonly_fields = ['created_at']


@admin.register(PrivateMessage)
class PrivateMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'chat', 'sender', 'content_short', 'timestamp', 'is_read', 'is_deleted', 'forwarded_from']
    list_filter = ['timestamp', 'is_read', 'is_deleted']
    search_fields = ['content', 'sender__username', 'forwarded_from']
    readonly_fields = ['timestamp']
    list_per_page = 50

    def content_short(self, obj):
        return obj.content[:60] + ('...' if len(obj.content) > 60 else '')
    content_short.short_description = '消息内容'


@admin.register(UserLoginLog)
class UserLoginLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'username_attempted', 'ip_address', 'success', 'timestamp']
    list_filter = ['success', 'timestamp']
    search_fields = ['username_attempted', 'ip_address']
    readonly_fields = ['timestamp']
    list_per_page = 50


@admin.register(GroupChat)
class GroupChatAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'owner', 'max_members', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'owner__username']


@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
    list_display = ['id', 'group', 'user', 'role', 'is_muted', 'muted_until', 'joined_at']
    list_filter = ['role', 'is_muted']
    search_fields = ['group__name', 'user__username']


@admin.register(GroupMessage)
class GroupMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'group', 'sender', 'content_short', 'timestamp', 'is_deleted', 'forwarded_from', 'mentions']
    list_filter = ['timestamp', 'is_deleted']
    search_fields = ['content', 'sender__username', 'group__name', 'mentions']
    readonly_fields = ['timestamp']
    list_per_page = 50

    def content_short(self, obj):
        return obj.content[:60] + ('...' if len(obj.content) > 60 else '')
    content_short.short_description = '消息内容'


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'message_type', 'sender_username', 'content_short', 'created_at']
    list_filter = ['message_type', 'created_at']
    search_fields = ['user__username', 'sender_username', 'message_content']
    readonly_fields = ['created_at']
    list_per_page = 50

    def content_short(self, obj):
        return obj.message_content[:60] + ('...' if len(obj.message_content) > 60 else '')
    content_short.short_description = '消息内容'


@admin.register(Blacklist)
class BlacklistAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'blocked_user', 'created_at']
    search_fields = ['user__username', 'blocked_user__username']
    readonly_fields = ['created_at']
