from django.contrib import admin
from .models import AdminUser, IPBlacklist, AdminLoginLog


@admin.register(IPBlacklist)
class IPBlacklistAdmin(admin.ModelAdmin):
    list_display = ('id', 'ip_address', 'reason', 'is_active', 'created_at', 'created_by')
    list_filter = ('is_active', 'created_at')
    search_fields = ('ip_address', 'reason')
    readonly_fields = ('created_at',)
    actions = ['activate_ips', 'deactivate_ips']

    @admin.action(description='启用选中IP封禁')
    def activate_ips(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description='解除选中IP封禁')
    def deactivate_ips(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(AdminUser)
class AdminUserAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('username',)
    readonly_fields = ('created_at',)
    exclude = ('password_hash',)

    def save_model(self, request, obj, form, change):
        if not change or 'password' in form.changed_data:
            if form.cleaned_data.get('password'):
                obj.set_password(form.cleaned_data['password'])
        super().save_model(request, obj, form, change)


@admin.register(AdminLoginLog)
class AdminLoginLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'username_attempted', 'ip_address', 'success', 'timestamp')
    list_filter = ('success', 'timestamp')
    search_fields = ('username_attempted', 'ip_address')
    readonly_fields = ('timestamp',)
