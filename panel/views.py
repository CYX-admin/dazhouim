from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from django.utils import timezone
from functools import wraps
from .models import AdminUser, IPBlacklist, AdminLoginLog
from chat.models import UserProfile, ChatMessage

def get_admin(request):
    admin_id = request.session.get('admin_id')
    if admin_id:
        try:
            return AdminUser.objects.get(id=admin_id, is_active=True)
        except AdminUser.DoesNotExist:
            pass
    return None

def admin_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        admin = get_admin(request)
        if not admin:
            return redirect('/admin/login/')
        request.admin = admin
        return view_func(request, *args, **kwargs)
    return wrapper

def super_admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        admin = get_admin(request)
        if not admin:
            return redirect('/admin/login/')
        if admin.role != 'super':
            return HttpResponseForbidden('需要超级管理员权限')
        request.admin = admin
        return view_func(request, *args, **kwargs)
    return wrapper

def admin_index(request):
    """管理后台根路径：已登录跳仪表盘，未登录跳登录页"""
    if get_admin(request):
        return redirect('/admin/dashboard/')
    return redirect('/admin/login/')

def admin_login(request):
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        ip = request.META.get('REMOTE_ADDR', '')
        admin = None
        try:
            admin = AdminUser.objects.get(username=username, is_active=True)
        except AdminUser.DoesNotExist:
            pass
        success = False
        if admin and admin.check_password(password):
            success = True
            request.session['admin_id'] = admin.id
            request.session.set_expiry(3600)
            AdminLoginLog.objects.create(admin=admin, username_attempted=username, ip_address=ip, success=True)
            return redirect('/admin/dashboard/')
        else:
            AdminLoginLog.objects.create(admin=admin, username_attempted=username, ip_address=ip, success=False)
            error = '用户名或密码错误'
    return render(request, 'panel/login.html', {'error': error})

def admin_logout(request):
    request.session.flush()
    return redirect('/admin/login/')

@admin_login_required
def dashboard(request):
    stats = {
        'total_users': User.objects.count(),
        'banned_users': UserProfile.objects.filter(is_banned=True).count(),
        'muted_users': UserProfile.objects.filter(is_muted=True).count(),
        'total_messages': ChatMessage.objects.count(),
        'blacklisted_ips': IPBlacklist.objects.filter(is_active=True).count(),
    }
    return render(request, 'panel/dashboard.html', {'admin': request.admin, 'stats': stats})

@admin_login_required
def user_list(request):
    users = User.objects.select_related('profile').all().order_by('-date_joined')
    return render(request, 'panel/users.html', {'admin': request.admin, 'users': users})

@admin_login_required
@require_POST
def user_ban(request, user_id):
    try:
        user = User.objects.get(id=user_id)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.is_banned = not profile.is_banned
        profile.save()
        return JsonResponse({'status': 'ok', 'is_banned': profile.is_banned})
    except User.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)

@admin_login_required
@require_POST
def user_mute(request, user_id):
    try:
        user = User.objects.get(id=user_id)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.is_muted = not profile.is_muted
        profile.save()
        return JsonResponse({'status': 'ok', 'is_muted': profile.is_muted})
    except User.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)

@admin_login_required
@require_POST
def user_delete(request, user_id):
    try:
        user = User.objects.get(id=user_id)
        user.delete()
        return JsonResponse({'status': 'ok'})
    except User.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)

@admin_login_required
@require_POST
def user_email_exempt(request, user_id):
    """管理员后台：切换某用户是否豁免邮箱验证"""
    try:
        user = User.objects.get(id=user_id)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.email_verify_exempt = not profile.email_verify_exempt
        profile.save(update_fields=['email_verify_exempt'])
        return JsonResponse({'status': 'ok', 'email_verify_exempt': profile.email_verify_exempt})
    except User.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)

@admin_login_required
def ip_blacklist(request):
    ips = IPBlacklist.objects.all().order_by('-created_at')
    return render(request, 'panel/ip_blacklist.html', {'admin': request.admin, 'ips': ips})

@admin_login_required
@require_POST
def ip_add(request):
    ip = request.POST.get('ip_address', '').strip()
    reason = request.POST.get('reason', '').strip()
    if ip:
        obj, created = IPBlacklist.objects.get_or_create(
            ip_address=ip,
            defaults={'reason': reason, 'created_by': request.admin}
        )
        if not created:
            obj.is_active = True
            obj.reason = reason
            obj.save()
    return redirect('/admin/ip-blacklist/')

@admin_login_required
@require_POST
def ip_toggle(request, ip_id):
    try:
        ip = IPBlacklist.objects.get(id=ip_id)
        ip.is_active = not ip.is_active
        ip.save()
        return JsonResponse({'status': 'ok', 'is_active': ip.is_active})
    except IPBlacklist.DoesNotExist:
        return JsonResponse({'error': 'IP不存在'}, status=404)

@admin_login_required
def login_logs(request):
    logs = AdminLoginLog.objects.all()[:200]
    return render(request, 'panel/login_logs.html', {'admin': request.admin, 'logs': logs})

@super_admin_required
def admin_manage(request):
    admins = AdminUser.objects.all().order_by('-created_at')
    return render(request, 'panel/admin_manage.html', {'admin': request.admin, 'admins': admins})

@super_admin_required
@require_POST
def admin_add(request):
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')
    role = request.POST.get('role', 'normal')
    if username and len(password) >= 4:
        if not AdminUser.objects.filter(username=username).exists():
            admin = AdminUser(username=username, role=role)
            admin.set_password(password)
            admin.save()
    return redirect('/admin/admins/')

@super_admin_required
@require_POST
def admin_delete(request, admin_id):
    try:
        admin = AdminUser.objects.get(id=admin_id)
        if admin.id == request.admin.id:
            return JsonResponse({'error': '不能删除自己'}, status=400)
        admin.delete()
        return JsonResponse({'status': 'ok'})
    except AdminUser.DoesNotExist:
        return JsonResponse({'error': '管理员不存在'}, status=404)

@admin_login_required
def change_password(request):
    error = None
    success = None
    if request.method == 'POST':
        old_pwd = request.POST.get('old_password', '')
        new_pwd = request.POST.get('new_password', '')
        if not request.admin.check_password(old_pwd):
            error = '旧密码错误'
        elif len(new_pwd) < 4:
            error = '新密码至少4位'
        else:
            request.admin.set_password(new_pwd)
            request.admin.save()
            success = '密码修改成功'
    return render(request, 'panel/change_password.html', {'admin': request.admin, 'error': error, 'success': success})
