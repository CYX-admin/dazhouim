import re
import secrets
import random
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone
from django.db.models import Q
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from .models import (
    UserProfile, ChatMessage, PrivateChat, PrivateMessage, UserLoginLog,
    GroupChat, GroupMember, GroupMessage, GroupJoinRequest, Favorite, Blacklist
)
from .forms import RegisterForm, LoginForm, EMAIL_RE, GroupCreateForm

RECALL_WINDOW_MINUTES = 2


def get_client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def sanitize_content(text):
    text = text.strip()
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\son\w+\s*=\s*"[^"]*"', '', text, flags=re.IGNORECASE)
    text = re.sub(r"\son\w+\s*=\s*'[^']*'", '', text, flags=re.IGNORECASE)
    # 未加引号的事件属性（如 onclick=alert(1)）
    text = re.sub(r'\son\w+\s*=\s*[^\s>]+', '', text, flags=re.IGNORECASE)
    # 屏蔽 javascript: 伪协议，防止链接类 XSS
    text = re.sub(r'\s*javascript\s*:', ' ', text, flags=re.IGNORECASE)
    if len(text) > 2000:
        text = text[:2000]
    return text


# ============ 附件上传 ============
IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'}
AUDIO_EXTS = {'mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac', 'wma', 'opus'}
VIDEO_EXTS = {'mp4', 'webm', 'mov', 'm4v', 'avi', 'mkv', 'flv'}
TEXT_EXTS = {'txt', 'md', 'csv', 'json', 'log', 'xml', 'yaml', 'yml', 'ini', 'conf'}
OFFICE_EXTS = {'pptx', 'ppt', 'doc', 'xls', 'xlsm', 'docm', 'odt', 'ods', 'rtf'}
FILE_EXTS = {'zip', 'rar', '7z', 'gz', 'tar'}
BLOCKED_EXTS = {'exe', 'bat', 'cmd', 'com', 'sh', 'bash', 'py', 'js', 'mjs',
                'html', 'htm', 'php', 'jar', 'dll', 'apk', 'msi', 'vbs', 'ps1',
                'scr', 'svg', 'phtml', 'shtml', 'cgi', 'pl', 'rb'}


def _to_utf8(f):
    """文本附件统一转为 UTF-8 存储，避免中文乱码（GBK/Big5 自动识别转换）"""
    try:
        raw = f.read()
        f.seek(0)
        try:
            raw.decode('utf-8')
            return f  # 已是 UTF-8，无需转换
        except UnicodeDecodeError:
            pass
        # 在 gb18030 与 big5 之间择优：选择汉字比例更高（假名/生僻字更少）的解码
        def _cjk_score(t):
            han = sum(1 for ch in t if '\u4e00' <= ch <= '\u9fff')
            kana = sum(1 for ch in t if '\u3040' <= ch <= '\u30ff')
            return (han - kana * 2) / max(1, len(t))
        candidates = []
        for enc in ('gb18030', 'big5'):
            try:
                candidates.append((_cjk_score(raw.decode(enc)), enc))
            except UnicodeDecodeError:
                continue
        if candidates:
            score, enc = max(candidates, key=lambda x: x[0])
            if score > 0.3:
                from django.core.files.base import ContentFile
                cf = ContentFile(raw.decode(enc).encode('utf-8'))
                cf.name = f.name
                return cf
        return f  # 无法可靠识别，保持原样
    except Exception:
        return f


def handle_attachment(request):
    """处理上传的附件。返回 (file_obj, original_name, attach_type, error)"""
    f = request.FILES.get('attachment')
    if not f:
        return None, '', '', None
    if f.size > settings.MAX_UPLOAD_SIZE:
        return None, '', '', f'文件过大，最大允许 {settings.MAX_UPLOAD_SIZE // 1024 // 1024}MB'
    name = f.name or 'file'
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    # 注意：应站长要求“从不限制上传任何文件类型”，已关闭扩展名拦截。
    # 放开后 exe/bat/html/apk 等文件可被上传并分发，存在传播病毒/钓鱼网页风险，
    # 如需恢复拦截，取消下行注释即可：
    # if ext in BLOCKED_EXTS:
    #     return None, '', '', f'不允许上传 {ext} 类型的文件'
    if ext in IMAGE_EXTS:
        return f, name, 'image', None
    if ext in AUDIO_EXTS:
        return f, name, 'audio', None
    if ext in VIDEO_EXTS:
        return f, name, 'video', None
    if ext in TEXT_EXTS:
        return _to_utf8(f), name, 'text', None
    if ext == 'pdf':
        return f, name, 'pdf', None
    if ext == 'docx':
        return f, name, 'docx', None
    if ext == 'xlsx':
        return f, name, 'xlsx', None
    if ext in OFFICE_EXTS:
        return f, name, 'office', None
    return f, name, 'file', None


def _get_user_title(user):
    try:
        return user.profile.user_title if user.profile.user_title else None
    except Exception:
        return None


def _get_user_profile(user):
    """安全获取用户资料"""
    try:
        return user.profile
    except Exception:
        return None


def attachment_dict(msg):
    """从消息对象提取附件信息"""
    if not msg.attachment:
        return None
    return {
        'url': msg.attachment.url,
        'name': msg.attachment_name or '附件',
        'type': msg.attachment_type or 'file',
    }


def _check_recall_time(msg):
    """检查消息是否在撤回时间窗口内"""
    if msg.timestamp and timezone.now() - msg.timestamp > timedelta(minutes=RECALL_WINDOW_MINUTES):
        return False, '超过撤回时间限制（2分钟）'
    return True, None


def _parse_mentions(content):
    """从消息内容中解析 @提及 的用户名，返回逗号分隔字符串"""
    import re
    if not content:
        return ''
    usernames = set()
    # 匹配 @用户名（直到空白或标点）
    for match in re.finditer(r'@([^\s，。！？、,.!?]+)', content):
        name = match.group(1)
        if name == '全体成员' or name == 'all':
            usernames.add('__all__')
        else:
            usernames.add(name)
    return ','.join(sorted(usernames))


# ============ 邮箱验证 ============
def generate_verify_code():
    return f'{random.randint(0, 999999):06d}'


def enforce_email_verification(user):
    if not settings.EMAIL_VERIFICATION_REQUIRED:
        return ('ok', None)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    status = profile.email_verification_status()
    if status == 'deleted':
        username = user.username
        email = user.email
        user.delete()
        return ('deleted', f'账号 {username}（{email}）因超过1小时未验证邮箱已被删除')
    if status == 'disabled':
        return ('disabled', '您的邮箱尚未验证，账号已停用，请尽快完成邮箱验证，否则账号将在1小时后被删除')
    return ('ok', None)


def send_verification_email(user, request=None):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    code = generate_verify_code()
    profile.email_verify_code = code
    profile.email_verify_code_expires = timezone.now() + timedelta(minutes=10)
    profile.save(update_fields=['email_verify_code', 'email_verify_code_expires'])
    try:
        send_mail(
            subject='【聊天室】邮箱验证码',
            message=(
                f'你好，{user.username}！\n\n'
                f'你的邮箱验证码是：{code}\n'
                f'验证码 10 分钟内有效，请登录后输入完成验证。\n\n'
                f'如果不是你本人操作，请忽略此邮件。'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return True, '验证码已发送至你的邮箱，请查收。'
    except Exception:
        return False, '验证邮件发送失败，请稍后重试或联系管理员'


@ensure_csrf_cookie
def register_view(request):
    if request.user.is_authenticated:
        return redirect('/chat/')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            email = form.cleaned_data.get('email', '') or ''
            user = User.objects.create_user(username=username, email=email, password=password)
            ip = get_client_ip(request)
            UserProfile.objects.create(user=user, last_login_ip=ip)
            UserLoginLog.objects.create(user=user, username_attempted=username, ip_address=ip, success=True)
            login(request, user)
            if settings.EMAIL_VERIFICATION_REQUIRED:
                success, _ = send_verification_email(user, request)
                if not success:
                    request.session['verify_error'] = '注册成功，但验证邮件发送失败，请点击下方"重新发送验证码"。'
                return redirect('/verify-email/')
            return redirect('/chat/')
    else:
        form = RegisterForm()
    return render(request, 'chat/register.html', {'form': form})


@ensure_csrf_cookie
def login_view(request):
    if request.user.is_authenticated:
        return redirect('/chat/')
    error = None
    deleted_msg = None
    if request.GET.get('deleted') == '1':
        deleted_msg = '账号已注销，如需使用请重新注册'
    ip = get_client_ip(request)
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                profile, _ = UserProfile.objects.get_or_create(user=user)
                if profile.is_banned:
                    UserLoginLog.objects.create(user=user, username_attempted=username, ip_address=ip, success=False)
                    error = '用户名或密码错误'
                else:
                    status, msg = enforce_email_verification(user)
                    if status == 'deleted':
                        UserLoginLog.objects.create(username_attempted=username, ip_address=ip, success=False)
                        error = '该账号因未验证邮箱已被删除，请重新注册'
                    elif status == 'disabled':
                        login(request, user)
                        profile.last_login_ip = ip
                        profile.last_active = timezone.now()
                        profile.save()
                        UserLoginLog.objects.create(user=user, username_attempted=username, ip_address=ip, success=True)
                        return redirect('/verify-email/')
                    else:
                        login(request, user)
                        profile.last_login_ip = ip
                        profile.last_active = timezone.now()
                        profile.status = 'online'
                        profile.save()
                        UserLoginLog.objects.create(user=user, username_attempted=username, ip_address=ip, success=True)
                        return redirect('/chat/')
            else:
                UserLoginLog.objects.create(username_attempted=username, ip_address=ip, success=False)
                error = '用户名或密码错误'
    else:
        form = LoginForm()
    return render(request, 'chat/login.html', {'form': form, 'error': error, 'deleted_msg': deleted_msg})


def logout_view(request):
    profile = _get_user_profile(request.user)
    if profile:
        profile.status = 'offline'
        profile.save(update_fields=['status'])
    logout(request)
    return redirect('/login/')


@login_required
@ensure_csrf_cookie
def verify_code_view(request):
    if not settings.EMAIL_VERIFICATION_REQUIRED:
        return redirect('/chat/')
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    error = request.session.pop('verify_error', None)
    success = None
    if request.method == 'POST':
        action = request.POST.get('action', 'verify')
        if action == 'resend':
            if not request.user.email:
                error = '当前账号未绑定邮箱，无法发送验证码'
            else:
                ok, msg = send_verification_email(request.user, request)
                if ok:
                    success = '验证码已重新发送，请查收邮箱。'
                else:
                    error = msg
        else:
            code = request.POST.get('code', '').strip()
            expired = (profile.email_verify_code_expires
                       and profile.email_verify_code_expires <= timezone.now())
            if not code:
                error = '请输入验证码'
            elif profile.email_verified:
                return redirect('/chat/')
            elif (profile.email_verify_code and profile.email_verify_code == code and not expired):
                profile.email_verified = True
                profile.email_verify_code = None
                profile.email_verify_code_expires = None
                profile.email_verify_token = None
                profile.email_verify_expires = None
                profile.save(update_fields=['email_verified', 'email_verify_code',
                                            'email_verify_code_expires', 'email_verify_token',
                                            'email_verify_expires'])
                return redirect('/chat/')
            elif expired:
                error = '验证码已过期，请点击"重新发送验证码"'
            else:
                error = '验证码错误，请重新输入'
    return render(request, 'chat/verify_code.html', {
        'email': request.user.email,
        'email_verified': profile.email_verified,
        'error': error,
        'success': success,
    })


@login_required
def verify_email_view(request, token):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if (profile.email_verify_token == token
            and profile.email_verify_expires
            and profile.email_verify_expires > timezone.now()):
        profile.email_verified = True
        profile.email_verify_token = None
        profile.email_verify_expires = None
        profile.save(update_fields=['email_verified', 'email_verify_token', 'email_verify_expires'])
        return render(request, 'chat/verify_result.html', {'success': True})
    return render(request, 'chat/verify_result.html', {'success': False})


@login_required
@require_POST
def resend_verify_email(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if not request.user.email:
        return JsonResponse({'error': '请先在个人资料中设置邮箱'}, status=400)
    ok, msg = send_verification_email(request.user, request)
    if ok:
        return JsonResponse({'status': 'ok', 'message': msg})
    return JsonResponse({'error': msg}, status=500)


def privacy_view(request):
    return render(request, 'chat/privacy.html')


@login_required
@ensure_csrf_cookie
def account_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    error = None
    success = None
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'change_email':
            new_email = request.POST.get('email', '').strip().lower()
            if not EMAIL_RE.match(new_email):
                error = '邮箱格式不正确（例如 abc@example.com）'
            elif User.objects.filter(email=new_email).exclude(id=request.user.id).exists():
                error = '该邮箱已被其他账号使用'
            else:
                request.user.email = new_email
                request.user.save(update_fields=['email'])
                profile.email_verified = False
                profile.save(update_fields=['email_verified'])
                ok, msg = send_verification_email(request.user, request)
                if ok:
                    success = '邮箱已更新，验证码已发送至新邮箱，请完成验证'
                else:
                    error = '邮箱已更新，但验证邮件发送失败，请稍后重新发送'
        elif action == 'resend':
            if not request.user.email:
                error = '当前账号未绑定邮箱'
            else:
                ok, msg = send_verification_email(request.user, request)
                if ok:
                    success = '验证码已重新发送，请查收邮箱'
                else:
                    error = msg
        elif action == 'verify':
            code = request.POST.get('code', '').strip()
            expired = (profile.email_verify_code_expires
                       and profile.email_verify_code_expires <= timezone.now())
            if not code:
                error = '请输入验证码'
            elif profile.email_verify_code and profile.email_verify_code == code and not expired:
                profile.email_verified = True
                profile.email_verify_code = None
                profile.email_verify_code_expires = None
                profile.save(update_fields=['email_verified', 'email_verify_code',
                                            'email_verify_code_expires'])
                success = '邮箱验证成功！'
            elif expired:
                error = '验证码已过期，请重新发送'
            else:
                error = '验证码错误'
        elif action == 'upload_avatar':
            avatar_file = request.FILES.get('avatar')
            if avatar_file:
                if avatar_file.size > 5 * 1024 * 1024:
                    error = '头像大小不能超过 5MB'
                else:
                    avatar_ext = (avatar_file.name or '').rsplit('.', 1)[-1].lower() if '.' in (avatar_file.name or '') else ''
                    if avatar_ext not in ('jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'):
                        error = '头像仅支持 jpg / png / gif / webp / bmp 图片格式'
                    else:
                        profile.avatar = avatar_file
                        profile.save(update_fields=['avatar'])
                        success = '头像已更新'
            else:
                error = '请选择要上传的头像文件'
        elif action == 'set_nickname':
            nickname = request.POST.get('nickname', '').strip()[:30]
            profile.nickname = nickname
            profile.save(update_fields=['nickname'])
            success = '昵称已更新'
        elif action == 'set_signature':
            signature = request.POST.get('signature', '').strip()[:80]
            profile.signature = signature
            profile.save(update_fields=['signature'])
            success = '个性签名已更新'
        elif action == 'set_status':
            status = request.POST.get('status', 'offline')
            if status in dict(UserProfile.STATUS_CHOICES):
                profile.status = status
                profile.save(update_fields=['status'])
                success = '状态已更新'
        elif action == 'change_password':
            old_pwd = request.POST.get('old_password', '')
            new_pwd = request.POST.get('new_password', '')
            confirm_pwd = request.POST.get('confirm_password', '')
            if not old_pwd or not new_pwd or not confirm_pwd:
                error = '请填写完整的密码信息'
            elif not request.user.check_password(old_pwd):
                error = '原密码不正确'
            elif len(new_pwd) < 4:
                error = '新密码至少4位'
            elif new_pwd != confirm_pwd:
                error = '两次输入的新密码不一致'
            elif new_pwd == old_pwd:
                error = '新密码不能与原密码相同'
            else:
                request.user.set_password(new_pwd)
                request.user.save()
                login(request, request.user)
                success = '密码修改成功'
        elif action == 'delete_account':
            confirm_pwd = request.POST.get('confirm_password', '')
            if not confirm_pwd:
                error = '请输入密码确认注销'
            elif not request.user.check_password(confirm_pwd):
                error = '密码不正确，无法注销'
            else:
                request.user.is_active = False
                request.user.save()
                logout(request)
                return redirect('/login/?deleted=1')
    return render(request, 'chat/account.html', {
        'email': request.user.email,
        'email_verified': profile.email_verified,
        'nickname': profile.nickname,
        'signature': profile.signature,
        'status': profile.status,
        'status_choices': UserProfile.STATUS_CHOICES,
        'email_verification_required': settings.EMAIL_VERIFICATION_REQUIRED,
        'error': error,
        'success': success,
    })


@login_required
def verify_required_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return render(request, 'chat/verify_required.html', {
        'email': request.user.email,
        'email_verified': profile.email_verified,
    })


@login_required
def chat_room(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    status, _ = enforce_email_verification(request.user)
    if status == 'deleted':
        logout(request)
        return redirect('/login/')
    if status == 'disabled':
        return redirect('/verify-email/')
    if profile.is_banned:
        logout(request)
        return HttpResponseForbidden('账号已被封禁')
    profile.last_active = timezone.now()
    profile.status = 'online'
    profile.save(update_fields=['last_active', 'status'])
    messages = ChatMessage.objects.select_related('user', 'reply_to__user').all()[:100]
    messages = reversed(list(messages))
    private_chats_qs = PrivateChat.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).select_related('user1', 'user2')
    private_chats = []
    for c in private_chats_qs:
        if c.is_hidden_for(request.user):
            continue
        other = c.user2 if c.user1 == request.user else c.user1
        last_msg = c.messages.last()
        unread = c.messages.filter(sender=other, is_read=False).count()
        private_chats.append({
            'id': c.id,
            'other_username': other.username,
            'other_id': other.id,
            'last_message': (last_msg.content[:50] if last_msg and last_msg.content
                             else ('[附件]' if last_msg and last_msg.attachment else '')),
            'last_time': timezone.localtime(last_msg.timestamp).strftime('%Y-%m-%d %H:%M') if last_msg else '',
            'unread': unread,
            'is_pinned': c.is_pinned_for(request.user),
            'is_muted': c.is_muted_for(request.user),
        })
    private_chats.sort(key=lambda x: (0 if x['is_pinned'] else 1, -1 if x.get('last_time') else 0))
    # 群聊列表（含最后消息预览）
    my_groups = GroupChat.objects.filter(members__user=request.user).distinct()
    group_list = []
    for g in my_groups:
        last_msg = g.messages.last()
        my_member = g.members.filter(user=request.user).first()
        unread = 0
        if my_member:
            unread = g.messages.filter(id__gt=my_member.last_read_message_id).exclude(sender=request.user).count()
        group_list.append({
            'id': g.id,
            'name': g.name,
            'last_message': (last_msg.content[:50] if last_msg and last_msg.content
                             else ('[附件]' if last_msg and last_msg.attachment else '')),
            'last_time': timezone.localtime(last_msg.timestamp).strftime('%Y-%m-%d %H:%M') if last_msg else '',
            'unread': unread,
            'member_count': g.member_count(),
        })
    return render(request, 'chat/room.html', {
        'messages': messages,
        'is_muted': profile.is_currently_muted(),
        'email_verified': profile.email_verified,
        'email_verification_required': settings.EMAIL_VERIFICATION_REQUIRED,
        'email': request.user.email,
        'nickname': profile.nickname,
        'private_chats': private_chats,
        'group_list': group_list,
        'current_status': profile.status,
    })


@login_required
def public_room(request):
    """公共聊天室页面"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    messages = ChatMessage.objects.select_related('user').all()[:100]
    messages = reversed(list(messages))
    return render(request, 'chat/public_room.html', {
        'messages': messages,
        'is_muted': profile.is_currently_muted(),
        'email_verified': profile.email_verified,
    })


@login_required
@require_POST
def send_message(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    status, _ = enforce_email_verification(request.user)
    if status == 'deleted':
        logout(request)
        return JsonResponse({'error': '账号因未验证邮箱已被删除'}, status=403)
    if status == 'disabled':
        return JsonResponse({'error': '账号已停用，请先完成邮箱验证'}, status=403)
    if profile.is_banned:
        return JsonResponse({'error': '账号已被封禁'}, status=403)
    if profile.is_currently_muted():
        return JsonResponse({'error': '您已被禁言'}, status=403)
    content = request.POST.get('content', '')
    content = sanitize_content(content)
    attach_file, attach_name, attach_type, attach_err = handle_attachment(request)
    if attach_err:
        return JsonResponse({'error': attach_err}, status=400)
    if not content and not attach_file:
        return JsonResponse({'error': '消息或附件不能为空'}, status=400)
    ip = get_client_ip(request)
    reply_to_id = request.POST.get('reply_to_id', '')
    reply_to = None
    if reply_to_id:
        try:
            reply_to = ChatMessage.objects.select_related('user').get(id=int(reply_to_id))
        except (ValueError, ChatMessage.DoesNotExist):
            reply_to = None
    msg = ChatMessage.objects.create(
        user=request.user, content=content, ip_address=ip, reply_to=reply_to,
        attachment=attach_file, attachment_name=attach_name, attachment_type=attach_type,
    )
    return JsonResponse({
        'id': msg.id,
        'user_id': msg.user.id,
        'username': msg.user.username,
        'user_title': _get_user_title(msg.user),
        'content': msg.content,
        'timestamp': timezone.localtime(msg.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
        'attachment': attachment_dict(msg),
        'reply_to': {
            'id': msg.reply_to.id,
            'username': msg.reply_to.user.username,
            'user_title': _get_user_title(msg.reply_to.user),
            'content': msg.reply_to.content[:100],
        } if msg.reply_to else None,
    })


@login_required
@require_GET
def get_messages(request):
    last_id = request.GET.get('last_id', '0')
    try:
        last_id = int(last_id)
    except ValueError:
        last_id = 0
    messages = ChatMessage.objects.filter(id__gt=last_id).select_related('user', 'reply_to__user').order_by('timestamp')[:50]
    data = [{
        'id': m.id,
        'user_id': m.user.id,
        'username': m.user.username,
        'user_title': _get_user_title(m.user),
        'content': m.content,
        'timestamp': timezone.localtime(m.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
        'is_deleted': m.is_deleted,
        'attachment': attachment_dict(m),
        'reply_to': {
            'id': m.reply_to.id,
            'username': m.reply_to.user.username,
            'user_title': _get_user_title(m.reply_to.user),
            'content': m.reply_to.content[:100],
        } if m.reply_to else None,
    } for m in messages]
    return JsonResponse({'messages': data})


@login_required
@require_GET
def online_users(request):
    cutoff = timezone.now() - timezone.timedelta(minutes=5)
    profiles = UserProfile.objects.filter(last_active__gte=cutoff, is_banned=False).select_related('user')
    users = [{'id': p.user.id, 'username': p.user.username, 'status': p.status} for p in profiles if p.user.id != request.user.id]
    return JsonResponse({'users': users})


@login_required
@require_GET
def all_users(request):
    """返回全部用户（含在线状态、最后活跃时间、私聊未读数），供左侧用户列表使用"""
    cutoff = timezone.now() - timezone.timedelta(minutes=5)
    users = User.objects.filter(is_active=True).select_related('profile').exclude(id=request.user.id).order_by('username')
    unread_map = {}
    chats = PrivateChat.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).select_related('user1', 'user2')
    for c in chats:
        other = c.user2 if c.user1 == request.user else c.user1
        cnt = c.messages.filter(sender=other, is_read=False).count()
        if cnt:
            unread_map[other.id] = cnt
    blocked_ids = set(Blacklist.objects.filter(user=request.user).values_list('blocked_user_id', flat=True))
    data = []
    for u in users:
        p = getattr(u, 'profile', None)
        online = bool(p and p.last_active and p.last_active >= cutoff)
        last_active = ''
        if p and p.last_active:
            last_active = timezone.localtime(p.last_active).strftime('%Y-%m-%d %H:%M')
        data.append({
            'id': u.id,
            'username': u.username,
            'user_title': _get_user_title(u),
            'nickname': p.nickname if p else '',
            'online': online,
            'status': p.status if p else 'offline',
            'last_active': last_active,
            'unread': unread_map.get(u.id, 0),
            'signature': p.signature if p else '',
            'is_blocked': u.id in blocked_ids,
        })
    return JsonResponse({'users': data})


@login_required
def heartbeat(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    status, _ = enforce_email_verification(request.user)
    if status == 'deleted':
        logout(request)
        return JsonResponse({'status': 'deleted', 'error': '账号因未验证邮箱已被删除'})
    if status == 'disabled':
        return JsonResponse({'status': 'disabled', 'error': '账号已停用，请先完成邮箱验证', 'is_muted': profile.is_currently_muted(), 'is_banned': profile.is_banned})
    profile.last_active = timezone.now()
    if profile.status == 'offline':
        profile.status = 'online'
        profile.save(update_fields=['last_active', 'status'])
    else:
        profile.save(update_fields=['last_active'])
    return JsonResponse({'status': 'ok', 'is_muted': profile.is_currently_muted(), 'is_banned': profile.is_banned})


@login_required
@require_POST
def set_status(request):
    """设置用户在线状态"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    status = request.POST.get('status', 'offline')
    if status not in dict(UserProfile.STATUS_CHOICES):
        return JsonResponse({'error': '无效的状态值'}, status=400)
    profile.status = status
    profile.save(update_fields=['status'])
    return JsonResponse({'status': 'ok', 'current_status': status})


@login_required
def private_typing(request, chat_id):
    """打字指示器：POST 设置正在输入，GET 检查对方是否在输入"""
    chat = get_object_or_404(PrivateChat, id=chat_id)
    if chat.user1 != request.user and chat.user2 != request.user:
        return JsonResponse({'error': '无权访问'}, status=403)
    if request.method == 'POST':
        chat.typing_user = request.user
        chat.typing_expires = timezone.now() + timedelta(seconds=5)
        chat.save(update_fields=['typing_user', 'typing_expires'])
        return JsonResponse({'status': 'ok'})
    else:
        other = chat.user2 if chat.user1 == request.user else chat.user1
        is_typing = (chat.typing_user_id == other.id and
                     chat.typing_expires and chat.typing_expires > timezone.now())
        return JsonResponse({'is_typing': is_typing})


# ============ Private Chat ============
@login_required
def private_chat_list(request):
    chats = PrivateChat.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).select_related('user1', 'user2')
    # 过滤掉当前用户已单方删除的会话
    chats = [c for c in chats if not c.is_hidden_for(request.user)]
    chats.sort(key=lambda c: (-1 if c.is_pinned_for(request.user) else 0, -c.created_at.timestamp()))
    chat_list = []
    for c in chats:
        other = c.user2 if c.user1 == request.user else c.user1
        last_msg = c.messages.last()
        unread = c.messages.filter(sender=other, is_read=False).count()
        chat_list.append({
            'id': c.id,
            'other_username': other.username,
            'other_id': other.id,
            'last_message': (last_msg.content[:50] if last_msg and last_msg.content
                             else ('[附件]' if last_msg and last_msg.attachment else '')),
            'last_time': timezone.localtime(last_msg.timestamp).strftime('%Y-%m-%d %H:%M') if last_msg else '',
            'unread': unread,
            'is_pinned': c.is_pinned_for(request.user),
            'is_muted': c.is_muted_for(request.user),
        })
    return render(request, 'chat/private_list.html', {'chats': chat_list})


@login_required
@require_GET
def api_private_list(request):
    """返回私聊会话列表（JSON），供主界面侧边栏使用"""
    chats = PrivateChat.objects.filter(
        Q(user1=request.user) | Q(user2=request.user)
    ).select_related('user1', 'user2')
    # 过滤掉当前用户已单方删除的会话
    chats = [c for c in chats if not c.is_hidden_for(request.user)]
    chats.sort(key=lambda c: (-1 if c.is_pinned_for(request.user) else 0, -c.created_at.timestamp()))
    chat_list = []
    for c in chats:
        other = c.user2 if c.user1 == request.user else c.user1
        last_msg = c.messages.last()
        unread = c.messages.filter(sender=other, is_read=False).count()
        chat_list.append({
            'id': c.id,
            'other_username': other.username,
            'other_id': other.id,
            'last_message': (last_msg.content[:50] if last_msg and last_msg.content
                             else ('[附件]' if last_msg and last_msg.attachment else '')),
            'last_time': timezone.localtime(last_msg.timestamp).strftime('%Y-%m-%d %H:%M') if last_msg else '',
            'unread': unread,
            'is_pinned': c.is_pinned_for(request.user),
            'is_muted': c.is_muted_for(request.user),
        })
    return JsonResponse({'chats': chat_list})


@login_required
def private_chat_detail(request, chat_id):
    chat = get_object_or_404(PrivateChat, id=chat_id)
    status, _ = enforce_email_verification(request.user)
    if status == 'deleted':
        logout(request)
        return redirect('/login/')
    if status == 'disabled':
        return redirect('/verify-email/')
    if chat.user1 != request.user and chat.user2 != request.user:
        return HttpResponseForbidden('无权访问此私聊')
    other = chat.user2 if chat.user1 == request.user else chat.user1
    # 重新打开会话时自动恢复显示（单方删除仅隐藏，不销毁数据）
    if chat.is_hidden_for(request.user):
        chat.set_hidden_for(request.user, False)
    messages = chat.messages.select_related('sender', 'reply_to__sender').all()[:100]
    messages = list(messages)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    chat.messages.filter(sender=other, is_read=False).update(is_read=True)
    return render(request, 'chat/private_chat.html', {
        'chat': chat,
        'other': other,
        'messages': messages,
        'is_muted': profile.is_currently_muted(),
        'is_banned': profile.is_banned,
        'is_pinned': chat.is_pinned_for(request.user),
        'is_chat_muted': chat.is_muted_for(request.user),
        'last_msg_id': messages[-1].id if messages else 0,
    })


@login_required
@require_POST
def private_start(request):
    other_id = request.POST.get('user_id')
    try:
        other = User.objects.get(id=other_id)
    except User.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)
    if other == request.user:
        return JsonResponse({'error': '不能与自己私聊'}, status=400)
    # 检查是否被对方拉黑
    if Blacklist.objects.filter(user=other, blocked_user=request.user).exists():
        return JsonResponse({'error': '对方已将你拉黑，无法发起私聊'}, status=403)
    # 检查是否已拉黑对方
    if Blacklist.objects.filter(user=request.user, blocked_user=other).exists():
        return JsonResponse({'error': '你已拉黑该用户，无法发起私聊'}, status=403)
    chat = PrivateChat.get_or_create_chat(request.user, other)
    return JsonResponse({'chat_id': chat.id, 'redirect': f'/private/{chat.id}/'})


@login_required
@require_POST
def private_send(request, chat_id):
    chat = get_object_or_404(PrivateChat, id=chat_id)
    if chat.user1 != request.user and chat.user2 != request.user:
        return JsonResponse({'error': '无权访问'}, status=403)
    other = chat.user2 if chat.user1 == request.user else chat.user1
    # 检查黑名单
    if Blacklist.objects.filter(user=other, blocked_user=request.user).exists():
        return JsonResponse({'error': '对方已将你拉黑，无法发送消息'}, status=403)
    # 检查是否已拉黑对方
    if Blacklist.objects.filter(user=request.user, blocked_user=other).exists():
        return JsonResponse({'error': '你已拉黑对方，无法发送消息'}, status=403)
    # 会话被对方单方删除时自动恢复对方视角？不：仅本端发送时若本端曾隐藏，恢复显示
    if chat.is_hidden_for(request.user):
        chat.set_hidden_for(request.user, False)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    status, _ = enforce_email_verification(request.user)
    if status == 'deleted':
        logout(request)
        return JsonResponse({'error': '账号因未验证邮箱已被删除'}, status=403)
    if status == 'disabled':
        return JsonResponse({'error': '账号已停用，请先完成邮箱验证'}, status=403)
    if profile.is_banned:
        return JsonResponse({'error': '账号已被封禁'}, status=403)
    if profile.is_currently_muted():
        return JsonResponse({'error': '您已被禁言'}, status=403)
    content = request.POST.get('content', '')
    content = sanitize_content(content)
    attach_file, attach_name, attach_type, attach_err = handle_attachment(request)
    if attach_err:
        return JsonResponse({'error': attach_err}, status=400)
    if not content and not attach_file:
        return JsonResponse({'error': '消息或附件不能为空'}, status=400)
    ip = get_client_ip(request)
    reply_to_id = request.POST.get('reply_to_id', '')
    reply_to = None
    if reply_to_id:
        try:
            reply_to = chat.messages.select_related('sender').get(id=int(reply_to_id))
        except (ValueError, PrivateMessage.DoesNotExist):
            reply_to = None
    msg = PrivateMessage.objects.create(
        chat=chat, sender=request.user, content=content, ip_address=ip, reply_to=reply_to,
        attachment=attach_file, attachment_name=attach_name, attachment_type=attach_type,
    )
    return JsonResponse({
        'id': msg.id,
        'sender_id': msg.sender.id,
        'username': msg.sender.username,
        'user_title': _get_user_title(msg.sender),
        'content': msg.content,
        'timestamp': timezone.localtime(msg.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
        'attachment': attachment_dict(msg),
        'reply_to': {
            'id': msg.reply_to.id,
            'username': msg.reply_to.sender.username,
            'user_title': _get_user_title(msg.reply_to.sender),
            'content': msg.reply_to.content[:100],
        } if msg.reply_to else None,
    })


@login_required
@require_GET
def private_messages(request, chat_id):
    chat = get_object_or_404(PrivateChat, id=chat_id)
    if chat.user1 != request.user and chat.user2 != request.user:
        return JsonResponse({'error': '无权访问'}, status=403)
    last_id = request.GET.get('last_id', '0')
    try:
        last_id = int(last_id)
    except ValueError:
        last_id = 0
    messages = chat.messages.filter(id__gt=last_id).select_related('sender', 'reply_to__sender').order_by('timestamp')[:50]
    # 打开会话时恢复显示（单方删除仅隐藏自己的会话列表项）
    if chat.is_hidden_for(request.user):
        chat.set_hidden_for(request.user, False)
    chat.messages.exclude(sender=request.user).filter(is_read=False).update(is_read=True)
    data = [{
        'id': m.id,
        'sender_id': m.sender.id,
        'username': m.sender.username,
        'user_title': _get_user_title(m.sender),
        'content': m.content,
        'timestamp': timezone.localtime(m.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
        'is_own': m.sender == request.user,
        'is_read': m.is_read,
        'is_deleted': m.is_deleted,
        'deleted_by_sender': m.deleted_by_sender,
        'attachment': attachment_dict(m),
        'reply_to': {
            'id': m.reply_to.id,
            'username': m.reply_to.sender.username,
            'user_title': _get_user_title(m.reply_to.sender),
            'content': m.reply_to.content[:100],
        } if m.reply_to else None,
    } for m in messages]
    return JsonResponse({'messages': data})


@login_required
@require_POST
def private_delete_message(request, chat_id, msg_id):
    """单方删除自己发送的私聊消息（仅自己视角隐藏，对方仍可见）"""
    chat = get_object_or_404(PrivateChat, id=chat_id)
    if chat.user1 != request.user and chat.user2 != request.user:
        return JsonResponse({'error': '无权访问'}, status=403)
    msg = get_object_or_404(PrivateMessage, id=msg_id, chat=chat)
    if msg.sender != request.user:
        return JsonResponse({'error': '只能删除自己发送的消息'}, status=403)
    if msg.is_deleted:
        return JsonResponse({'error': '消息已撤回'}, status=400)
    msg.deleted_by_sender = True
    msg.save(update_fields=['deleted_by_sender'])
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def recall_message(request, msg_id):
    msg = get_object_or_404(ChatMessage, id=msg_id)
    if msg.user != request.user:
        return JsonResponse({'error': '只能撤回自己发送的消息'}, status=403)
    if msg.is_deleted:
        return JsonResponse({'error': '消息已撤回'}, status=400)
    ok, err = _check_recall_time(msg)
    if not ok:
        return JsonResponse({'error': err}, status=400)
    msg.is_deleted = True
    msg.content = ''
    if msg.attachment:
        try:
            msg.attachment.delete(save=False)
        except Exception:
            pass
        msg.attachment = None
        msg.attachment_name = ''
        msg.attachment_type = ''
    msg.save(update_fields=['is_deleted', 'content', 'attachment', 'attachment_name', 'attachment_type'])
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def private_recall_message(request, chat_id, msg_id):
    chat = get_object_or_404(PrivateChat, id=chat_id)
    if chat.user1 != request.user and chat.user2 != request.user:
        return JsonResponse({'error': '无权访问'}, status=403)
    msg = get_object_or_404(PrivateMessage, id=msg_id, chat=chat)
    if msg.sender != request.user:
        return JsonResponse({'error': '只能撤回自己发送的消息'}, status=403)
    if msg.is_deleted:
        return JsonResponse({'error': '消息已撤回'}, status=400)
    ok, err = _check_recall_time(msg)
    if not ok:
        return JsonResponse({'error': err}, status=400)
    msg.is_deleted = True
    msg.content = ''
    if msg.attachment:
        try:
            msg.attachment.delete(save=False)
        except Exception:
            pass
        msg.attachment = None
        msg.attachment_name = ''
        msg.attachment_type = ''
    msg.save(update_fields=['is_deleted', 'content', 'attachment', 'attachment_name', 'attachment_type'])
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def private_pin_chat(request, chat_id):
    """置顶/取消置顶私聊会话"""
    chat = get_object_or_404(PrivateChat, id=chat_id)
    if chat.user1 != request.user and chat.user2 != request.user:
        return JsonResponse({'error': '无权访问'}, status=403)
    cur = chat.is_pinned_for(request.user)
    chat.set_pinned_for(request.user, not cur)
    return JsonResponse({'status': 'ok', 'is_pinned': chat.is_pinned_for(request.user)})


@login_required
@require_POST
def private_mute_chat(request, chat_id):
    """免打扰/取消免打扰私聊会话（按用户视角，互不影响）"""
    chat = get_object_or_404(PrivateChat, id=chat_id)
    if chat.user1 != request.user and chat.user2 != request.user:
        return JsonResponse({'error': '无权访问'}, status=403)
    cur = chat.is_muted_for(request.user)
    chat.set_muted_for(request.user, not cur)
    return JsonResponse({'status': 'ok', 'is_muted': chat.is_muted_for(request.user)})


@login_required
@require_GET
def private_search(request, chat_id):
    """私聊内搜索消息"""
    chat = get_object_or_404(PrivateChat, id=chat_id)
    if chat.user1 != request.user and chat.user2 != request.user:
        return JsonResponse({'error': '无权访问'}, status=403)
    keyword = request.GET.get('q', '').strip()
    if not keyword:
        return JsonResponse({'messages': []})
    messages = chat.messages.filter(
        content__icontains=keyword, is_deleted=False
    ).select_related('sender').order_by('-timestamp')[:50]
    data = [{
        'id': m.id,
        'sender_id': m.sender.id,
        'username': m.sender.username,
        'content': m.content,
        'timestamp': timezone.localtime(m.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
        'is_own': m.sender == request.user,
    } for m in messages]
    return JsonResponse({'messages': data})


# ============ 收藏 ============
@login_required
def favorites_view(request):
    """收藏页面"""
    favorites = Favorite.objects.filter(user=request.user).select_related('sender').order_by('-created_at')
    return render(request, 'chat/favorites.html', {'favorites': favorites})


@login_required
@require_POST
def favorite_add(request):
    """收藏消息"""
    msg_type = request.POST.get('message_type', '')
    msg_id = request.POST.get('message_id', '')
    if msg_type not in ('private', 'group', 'global'):
        return JsonResponse({'error': '无效的消息类型'}, status=400)
    try:
        msg_id = int(msg_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': '无效的消息ID'}, status=400)
    content = ''
    sender = None
    sender_username = ''
    attachment_url = ''
    attachment_name = ''
    if msg_type == 'private':
        msg = PrivateMessage.objects.filter(id=msg_id).select_related('sender', 'chat').first()
        if not msg:
            return JsonResponse({'error': '消息不存在'}, status=404)
        if msg.chat.user1 != request.user and msg.chat.user2 != request.user:
            return JsonResponse({'error': '无权收藏此消息'}, status=403)
        if msg.is_deleted or msg.deleted_by_sender:
            return JsonResponse({'error': '已撤回或已删除的消息不能收藏'}, status=400)
        content = msg.content
        sender = msg.sender
        sender_username = msg.sender.username
        if msg.attachment:
            attachment_url = msg.attachment.url
            attachment_name = msg.attachment_name or '附件'
    elif msg_type == 'group':
        msg = GroupMessage.objects.filter(id=msg_id).select_related('sender', 'group').first()
        if not msg:
            return JsonResponse({'error': '消息不存在'}, status=404)
        if not msg.group.is_member(request.user):
            return JsonResponse({'error': '无权收藏此消息'}, status=403)
        if msg.is_deleted:
            return JsonResponse({'error': '已撤回的消息不能收藏'}, status=400)
        content = msg.content
        sender = msg.sender
        sender_username = msg.sender.username
        if msg.attachment:
            attachment_url = msg.attachment.url
            attachment_name = msg.attachment_name or '附件'
    else:
        msg = ChatMessage.objects.filter(id=msg_id).select_related('user').first()
        if not msg:
            return JsonResponse({'error': '消息不存在'}, status=404)
        if msg.is_deleted:
            return JsonResponse({'error': '已撤回的消息不能收藏'}, status=400)
        content = msg.content
        sender = msg.user
        sender_username = msg.user.username
        if msg.attachment:
            attachment_url = msg.attachment.url
            attachment_name = msg.attachment_name or '附件'
    fav = Favorite.objects.create(
        user=request.user,
        message_type=msg_type,
        message_content=content,
        sender=sender,
        sender_username=sender_username,
        attachment_url=attachment_url,
        attachment_name=attachment_name,
    )
    return JsonResponse({'status': 'ok', 'favorite_id': fav.id})


@login_required
@require_POST
def favorite_remove(request, fav_id):
    """取消收藏"""
    fav = get_object_or_404(Favorite, id=fav_id, user=request.user)
    fav.delete()
    return JsonResponse({'status': 'ok'})


# ============ 黑名单 ============
@login_required
@require_POST
def blacklist_add(request):
    """拉黑用户"""
    user_id = request.POST.get('user_id', '')
    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)
    if target == request.user:
        return JsonResponse({'error': '不能拉黑自己'}, status=400)
    _, created = Blacklist.objects.get_or_create(user=request.user, blocked_user=target)
    return JsonResponse({'status': 'ok', 'created': created})


@login_required
@require_POST
def blacklist_remove(request):
    """解除拉黑"""
    user_id = request.POST.get('user_id', '')
    try:
        target = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)
    Blacklist.objects.filter(user=request.user, blocked_user=target).delete()
    return JsonResponse({'status': 'ok'})


@login_required
@require_GET
def blacklist_list(request):
    """获取黑名单列表"""
    blocked = Blacklist.objects.filter(user=request.user).select_related('blocked_user')
    data = [{
        'id': b.id,
        'blocked_user_id': b.blocked_user.id,
        'blocked_username': b.blocked_user.username,
        'created_at': timezone.localtime(b.created_at).strftime('%Y-%m-%d %H:%M'),
    } for b in blocked]
    return JsonResponse({'blacklist': data})


# ============ 群聊视图 ============
@login_required
def group_list(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    my_groups = GroupChat.objects.filter(members__user=request.user).distinct()
    return render(request, 'chat/group_list.html', {
        'groups': my_groups,
        'profile': profile,
    })


@login_required
def group_create(request):
    if request.method == 'POST':
        form = GroupCreateForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            description = form.cleaned_data.get('description', '')
            join_mode = form.cleaned_data.get('join_mode', 'open')
            join_pin = form.cleaned_data.get('join_pin') or None
            if join_mode != 'approval':
                join_pin = None
            group = GroupChat.objects.create(
                name=name,
                description=description,
                owner=request.user,
                join_mode=join_mode,
                join_pin=join_pin,
            )
            GroupMember.objects.create(group=group, user=request.user, role='owner')
            return redirect(f'/group/{group.id}/')
    else:
        form = GroupCreateForm()
    return render(request, 'chat/group_create.html', {'form': form})


@login_required
def group_detail(request, group_id):
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_member(request.user):
        return HttpResponseForbidden('你不是该群成员')
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    messages = group.messages.select_related('sender').all()[:100]
    messages = list(messages)
    members = group.members.select_related('user').all()
    is_owner = group.is_owner(request.user)
    is_admin = group.is_admin(request.user)
    # 检查当前用户是否被群禁言
    my_member = group.members.filter(user=request.user).first()
    group_muted = my_member.is_currently_muted() if my_member else False
    # 更新已读位置
    last_msg = group.messages.order_by('-id').first()
    if my_member and last_msg:
        my_member.last_read_message_id = last_msg.id
        my_member.save(update_fields=['last_read_message_id'])
    return render(request, 'chat/group_chat.html', {
        'group': group,
        'messages': messages,
        'members': members,
        'is_owner': is_owner,
        'is_admin': is_admin,
        'is_muted': profile.is_currently_muted(),
        'is_banned': profile.is_banned,
        'group_muted': group_muted,
        'last_msg_id': messages[-1].id if messages else 0,
    })


@login_required
def group_profile(request, group_id):
    """群资料页"""
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_member(request.user):
        return HttpResponseForbidden('你不是该群成员')
    members = group.members.select_related('user').all()
    is_owner = group.is_owner(request.user)
    is_admin = group.is_admin(request.user)
    return render(request, 'chat/group_profile.html', {
        'group': group,
        'members': members,
        'is_owner': is_owner,
        'is_admin': is_admin,
        'member_count': group.member_count(),
    })


@login_required
@require_POST
def group_update_info(request, group_id):
    """群主修改群名、简介、入群方式与PIN码"""
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_owner(request.user):
        return JsonResponse({'error': '只有群主可以修改群资料'}, status=403)
    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    join_mode = request.POST.get('join_mode', '')
    join_pin = request.POST.get('join_pin', '').strip()
    if join_mode:
        if join_mode not in dict(GroupChat.JOIN_MODE_CHOICES):
            return JsonResponse({'error': '无效的入群方式'}, status=400)
        group.join_mode = join_mode
    if join_pin:
        if not re.match(r'^[A-Za-z0-9]{4,16}$', join_pin):
            return JsonResponse({'error': 'PIN码需为4-16位字母或数字'}, status=400)
        group.join_pin = join_pin
    elif join_mode == 'approval':
        # 需审核模式下允许清空PIN（此时只能通过申请入群）
        group.join_pin = None
    if join_mode == 'open':
        group.join_pin = None
    if name:
        if len(name) > 50:
            return JsonResponse({'error': '群名不能超过50个字符'}, status=400)
        group.name = name
    if description:
        if len(description) > 200:
            return JsonResponse({'error': '群简介不能超过200个字符'}, status=400)
        group.description = description
    group.save(update_fields=['name', 'description', 'join_mode', 'join_pin'])
    return JsonResponse({'status': 'ok', 'name': group.name, 'description': group.description,
                         'join_mode': group.join_mode, 'join_pin': group.join_pin})


@login_required
@require_POST
def group_send(request, group_id):
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_member(request.user):
        return JsonResponse({'error': '你不是该群成员'}, status=403)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if profile.is_banned:
        return JsonResponse({'error': '账号已被封禁'}, status=403)
    if profile.is_currently_muted():
        return JsonResponse({'error': '您已被禁言'}, status=403)
    # 检查群禁言
    member = group.members.filter(user=request.user).first()
    if member and member.is_currently_muted():
        return JsonResponse({'error': '您已被群主禁言'}, status=403)
    content = request.POST.get('content', '')
    content = sanitize_content(content)
    if not content and not request.FILES.get('attachment'):
        return JsonResponse({'error': '消息内容不能为空'}, status=400)
    attach_file, attach_name, attach_type, attach_err = handle_attachment(request)
    # 解析 @提及
    mentions = _parse_mentions(content)
    msg = GroupMessage.objects.create(
        group=group,
        sender=request.user,
        content=content,
        attachment=attach_file,
        attachment_name=attach_name,
        attachment_type=attach_type,
        mentions=mentions,
    )
    return JsonResponse({'status': 'ok', 'msg_id': msg.id})


@login_required
def group_messages(request, group_id):
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_member(request.user):
        return JsonResponse({'error': '无权访问'}, status=403)
    last_id = request.GET.get('last_id', 0)
    try:
        last_id = int(last_id)
    except (ValueError, TypeError):
        last_id = 0
    msgs = group.messages.select_related('sender').filter(id__gt=last_id)[:50]
    total_members = group.members.count()
    # 预计算已读人数：统计每个成员 last_read_message_id，按消息 id 排序后一次求值（避免 N+1 查询）
    member_last_reads = sorted(group.members.values_list('last_read_message_id', flat=True))
    import bisect
    def read_count_for(msg_id):
        # 已读人数 = last_read >= msg_id 的成员数
        return len(member_last_reads) - bisect.bisect_left(member_last_reads, msg_id)
    result = []
    for m in msgs:
        read_count = read_count_for(m.id)
        result.append({
            'id': m.id,
            'username': m.sender.username,
            'user_title': _get_user_title(m.sender),
            'user_id': m.sender.id,
            'content': m.content,
            'time': m.timestamp.strftime('%Y-%m-%d %H:%M'),
            'created_at': int(m.timestamp.timestamp()),
            'is_deleted': m.is_deleted,
            'attachment': attachment_dict(m),
            'read_count': read_count,
            'total_members': total_members,
            'forwarded_from': m.forwarded_from,
            'mentions': m.mentions,
        })
    # 更新当前用户已读位置
    my_member = group.members.filter(user=request.user).first()
    if my_member and result:
        my_member.last_read_message_id = result[-1]['id']
        my_member.save(update_fields=['last_read_message_id'])
    return JsonResponse({'messages': result})


@login_required
@require_POST
def group_recall(request, group_id, msg_id):
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_member(request.user):
        return JsonResponse({'error': '无权访问'}, status=403)
    msg = get_object_or_404(GroupMessage, id=msg_id, group=group)
    can_recall = (msg.sender == request.user)
    if not can_recall:
        return JsonResponse({'error': '只能撤回自己发送的消息'}, status=403)
    if msg.is_deleted:
        return JsonResponse({'error': '消息已撤回'}, status=400)
    # 普通用户有2分钟限制，管理员无限制
    if msg.sender == request.user and not group.is_admin(request.user):
        ok, err = _check_recall_time(msg)
        if not ok:
            return JsonResponse({'error': err}, status=400)
    msg.is_deleted = True
    msg.content = ''
    if msg.attachment:
        try:
            msg.attachment.delete(save=False)
        except Exception:
            pass
        msg.attachment = None
        msg.attachment_name = ''
        msg.attachment_type = ''
    msg.save(update_fields=['is_deleted', 'content', 'attachment', 'attachment_name', 'attachment_type'])
    return JsonResponse({'status': 'ok'})


@login_required
def group_members(request, group_id):
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_member(request.user):
        return HttpResponseForbidden('无权访问')
    members = group.members.select_related('user').all()
    is_owner = group.is_owner(request.user)
    is_admin = group.is_admin(request.user)
    return render(request, 'chat/group_members.html', {
        'group': group,
        'members': members,
        'is_owner': is_owner,
        'is_admin': is_admin,
    })


@login_required
@require_POST
def group_add_member(request, group_id):
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_admin(request.user):
        return JsonResponse({'error': '只有群主或管理员可以添加成员'}, status=403)
    username = request.POST.get('username', '').strip()
    if not username:
        return JsonResponse({'error': '请输入用户名'}, status=400)
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)
    if group.is_member(user):
        return JsonResponse({'error': '该用户已在群中'}, status=400)
    if group.member_count() >= group.max_members:
        return JsonResponse({'error': '群成员已达上限'}, status=400)
    GroupMember.objects.create(group=group, user=user, role='member')
    return JsonResponse({'status': 'ok', 'username': user.username})


@login_required
@require_POST
def group_remove_member(request, group_id):
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_admin(request.user):
        return JsonResponse({'error': '只有群主或管理员可以移除成员'}, status=403)
    user_id = request.POST.get('user_id')
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': '参数错误'}, status=400)
    member = get_object_or_404(GroupMember, group=group, user_id=user_id)
    if member.role == 'owner':
        return JsonResponse({'error': '不能移除群主'}, status=400)
    if member.role == 'admin' and not group.is_owner(request.user):
        return JsonResponse({'error': '只有群主可以移除管理员'}, status=403)
    member.delete()
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def group_mute_member(request, group_id):
    """群禁言成员"""
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_admin(request.user):
        return JsonResponse({'error': '只有群主或管理员可以禁言成员'}, status=403)
    user_id = request.POST.get('user_id')
    duration = request.POST.get('duration', '0')  # 分钟数，0表示永久
    try:
        user_id = int(user_id)
        duration = int(duration)
    except (ValueError, TypeError):
        return JsonResponse({'error': '参数错误'}, status=400)
    member = get_object_or_404(GroupMember, group=group, user_id=user_id)
    if member.role == 'owner':
        return JsonResponse({'error': '不能禁言群主'}, status=400)
    if member.role == 'admin' and not group.is_owner(request.user):
        return JsonResponse({'error': '只有群主可以禁言管理员'}, status=403)
    member.is_muted = True
    if duration > 0:
        member.muted_until = timezone.now() + timedelta(minutes=duration)
    else:
        member.muted_until = None
    member.save(update_fields=['is_muted', 'muted_until'])
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def group_unmute_member(request, group_id):
    """解除群禁言"""
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_admin(request.user):
        return JsonResponse({'error': '只有群主或管理员可以解除禁言'}, status=403)
    user_id = request.POST.get('user_id')
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': '参数错误'}, status=400)
    member = get_object_or_404(GroupMember, group=group, user_id=user_id)
    member.is_muted = False
    member.muted_until = None
    member.save(update_fields=['is_muted', 'muted_until'])
    return JsonResponse({'status': 'ok'})


@login_required
@require_GET
def group_search(request, group_id):
    """群聊内搜索消息"""
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_member(request.user):
        return JsonResponse({'error': '无权访问'}, status=403)
    keyword = request.GET.get('q', '').strip()
    if not keyword:
        return JsonResponse({'messages': []})
    messages = group.messages.filter(
        content__icontains=keyword, is_deleted=False
    ).select_related('sender').order_by('-timestamp')[:50]
    data = [{
        'id': m.id,
        'sender_id': m.sender.id,
        'username': m.sender.username,
        'content': m.content,
        'timestamp': timezone.localtime(m.timestamp).strftime('%Y-%m-%d %H:%M:%S'),
        'is_own': m.sender == request.user,
    } for m in messages]
    return JsonResponse({'messages': data})


@login_required
@require_POST
def group_announcement_save(request, group_id):
    group = get_object_or_404(GroupChat, id=group_id)
    member = GroupMember.objects.filter(group=group, user=request.user).first()
    if not member or member.role not in ['owner', 'admin']:
        return JsonResponse({'error': '只有群主或管理员可以修改公告'}, status=403)
    announcement = request.POST.get('announcement', '')
    group.announcement = announcement
    group.save(update_fields=['announcement'])
    return JsonResponse({'status': 'ok', 'announcement': announcement})


@login_required
@require_POST
def group_set_admin(request, group_id):
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_owner(request.user):
        return JsonResponse({'error': '只有群主可以设置管理员'}, status=403)
    user_id = request.POST.get('user_id')
    action = request.POST.get('action', 'set')
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': '参数错误'}, status=400)
    member = get_object_or_404(GroupMember, group=group, user_id=user_id)
    if member.role == 'owner':
        return JsonResponse({'error': '不能修改群主角色'}, status=400)
    if action == 'set':
        member.role = 'admin'
    else:
        member.role = 'member'
    member.save(update_fields=['role'])
    return JsonResponse({'status': 'ok', 'role': member.role})


@login_required
@require_POST
def group_leave(request, group_id):
    group = get_object_or_404(GroupChat, id=group_id)
    if group.is_owner(request.user):
        return JsonResponse({'error': '群主不能直接退群，请先转让群主或解散群'}, status=400)
    member = get_object_or_404(GroupMember, group=group, user=request.user)
    member.delete()
    return JsonResponse({'status': 'ok'})


# ========== 入群申请（需审核的群） ==========
@login_required
@require_GET
def api_all_groups(request):
    """返回全部群（用于发现群聊与自助入群）"""
    groups = GroupChat.objects.select_related('owner').all()[:100]
    joined_ids = set(GroupMember.objects.filter(user=request.user).values_list('group_id', flat=True))
    data = [{
        'id': g.id,
        'name': g.name,
        'description': g.description,
        'owner': g.owner.username,
        'member_count': g.member_count(),
        'max_members': g.max_members,
        'join_mode': g.join_mode,
        'joined': g.id in joined_ids,
        'has_pin': bool(g.join_pin),
    } for g in groups]
    return JsonResponse({'groups': data})


@login_required
@require_POST
def group_join(request, group_id):
    """自助入群：自由加入直接进群；需审核时，输入正确PIN直接进群，否则提交申请等待群主审批"""
    group = get_object_or_404(GroupChat, id=group_id)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if profile.is_banned:
        return JsonResponse({'error': '账号已被封禁'}, status=403)
    if group.is_member(request.user):
        return JsonResponse({'error': '你已在群中'}, status=400)
    if group.member_count() >= group.max_members:
        return JsonResponse({'error': '群成员已达上限'}, status=400)
    if group.join_mode == 'open':
        GroupMember.objects.create(group=group, user=request.user, role='member')
        return JsonResponse({'status': 'ok', 'joined': True, 'redirect': f'/group/{group.id}/'})
    # 需审核模式：先验证PIN
    pin = request.POST.get('pin', '').strip()
    if group.join_pin and pin and pin == group.join_pin:
        GroupMember.objects.create(group=group, user=request.user, role='member')
        return JsonResponse({'status': 'ok', 'joined': True, 'redirect': f'/group/{group.id}/'})
    # 无PIN或PIN错误 → 提交/更新入群申请
    message = request.POST.get('message', '')[:200]
    req, created = GroupJoinRequest.objects.get_or_create(
        group=group, user=request.user,
        defaults={'status': 'pending', 'message': message},
    )
    if not created:
        if req.status == 'approved':
            # 状态异常（已通过但非成员）→ 直接补为成员
            GroupMember.objects.get_or_create(group=group, user=request.user, role='member')
            return JsonResponse({'status': 'ok', 'joined': True, 'redirect': f'/group/{group.id}/'})
        if req.status == 'rejected':
            req.status = 'pending'
            req.message = message
            req.handled_at = None
            req.save(update_fields=['status', 'message', 'handled_at'])
        else:
            return JsonResponse({'status': 'requested', 'error': '你已提交过入群申请，请耐心等待群主审核'})
    return JsonResponse({'status': 'requested', 'error': '入群申请已提交，请等待群主审核'})


@login_required
@require_GET
def group_join_requests(request, group_id):
    """群主查看待处理的入群申请"""
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_owner(request.user):
        return JsonResponse({'error': '只有群主可以查看入群申请'}, status=403)
    reqs = group.join_requests.select_related('user').filter(status='pending')
    data = [{
        'id': r.id,
        'user_id': r.user.id,
        'username': r.user.username,
        'message': r.message,
        'created_at': timezone.localtime(r.created_at).strftime('%Y-%m-%d %H:%M'),
    } for r in reqs]
    return JsonResponse({'requests': data, 'count': len(data)})


@login_required
@require_POST
def group_handle_join_request(request, group_id, req_id):
    """群主同意/拒绝入群申请"""
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_owner(request.user):
        return JsonResponse({'error': '只有群主可以处理入群申请'}, status=403)
    req = get_object_or_404(GroupJoinRequest, id=req_id, group=group)
    action = request.POST.get('action', '')
    if req.status != 'pending':
        return JsonResponse({'error': '该申请已处理过'}, status=400)
    if action == 'approve':
        if group.member_count() >= group.max_members:
            return JsonResponse({'error': '群成员已达上限，无法通过申请'}, status=400)
        member, created = GroupMember.objects.get_or_create(group=group, user=req.user, role='member')
        req.status = 'approved'
    elif action == 'reject':
        req.status = 'rejected'
    else:
        return JsonResponse({'error': '无效的操作'}, status=400)
    req.handled_at = timezone.now()
    req.save(update_fields=['status', 'handled_at'])
    return JsonResponse({'status': 'ok', 'username': req.user.username})


@login_required
@require_POST
def group_transfer(request, group_id):
    """群主转让群聊给其他成员"""
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_owner(request.user):
        return JsonResponse({'error': '只有群主可以转让群聊'}, status=403)
    user_id = request.POST.get('user_id')
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': '参数错误'}, status=400)
    if user_id == request.user.id:
        return JsonResponse({'error': '不能转让给自己'}, status=400)
    member = get_object_or_404(GroupMember, group=group, user_id=user_id)
    # 原群主降为普通成员，接收者升为群主
    old_owner = GroupMember.objects.get(group=group, user=request.user)
    member.role = 'owner'
    old_owner.role = 'member'
    member.save(update_fields=['role'])
    old_owner.save(update_fields=['role'])
    group.owner = member.user
    group.save(update_fields=['owner'])
    return JsonResponse({'status': 'ok', 'new_owner': member.user.username})


@login_required
@require_POST
def private_delete_chat(request, chat_id):
    """删除私聊会话（解除好友关系），同时删除该会话下的所有消息"""
    chat = get_object_or_404(PrivateChat, id=chat_id)
    if chat.user1 != request.user and chat.user2 != request.user:
        return JsonResponse({'error': '无权访问'}, status=403)
    other = chat.user2 if chat.user1 == request.user else chat.user1
    # 单方删除：只从自己视角隐藏会话，不删除任何消息，对方记录不受影响
    chat.set_hidden_for(request.user, True)
    return JsonResponse({'status': 'ok', 'deleted_with': other.username, 'hidden': True})


@login_required
def api_user_info(request, username):
    """获取用户公开信息"""
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({'error': '用户不存在'}, status=404)
    profile = _get_user_profile(user)
    is_blocked = Blacklist.objects.filter(user=request.user, blocked_user=user).exists()
    blocked_me = Blacklist.objects.filter(user=user, blocked_user=request.user).exists()
    return JsonResponse({
        'username': user.username,
        'nickname': profile.nickname if profile else '',
        'signature': profile.signature if profile else '',
        'avatar': profile.avatar.url if profile and profile.avatar else None,
        'user_title': profile.user_title if profile and profile.user_title else None,
        'custom_id': profile.custom_id if profile else None,
        'status': profile.status if profile else 'offline',
        'date_joined': user.date_joined.strftime('%Y-%m-%d') if user.date_joined else '',
        'is_blocked': is_blocked,
        'blocked_me': blocked_me,
    })


def api_groups(request):
    """返回当前用户加入的群（含未读数），供转发弹窗等使用"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': '请先登录'}, status=401)
    my_groups = GroupChat.objects.filter(members__user=request.user).distinct()
    # 一次性查出当前用户在各自群中的已读位置与群消息总数
    memberships = {
        m.group_id: m for m in GroupMember.objects.filter(user=request.user).select_related('group')
    }
    groups_data = []
    for g in my_groups:
        m = memberships.get(g.id)
        last_read = m.last_read_message_id if m else 0
        unread = g.messages.filter(id__gt=last_read, is_deleted=False).count()
        groups_data.append({
            'id': g.id,
            'name': g.name,
            'unread': unread,
        })
    return JsonResponse({'groups': groups_data})


# ========== 消息转发 ==========
@login_required
@require_POST
def forward_message(request):
    """转发消息到私聊或群聊"""
    source_type = request.POST.get('source_type', '')  # private / group
    source_msg_id = request.POST.get('message_id', '')
    target_type = request.POST.get('target_type', '')  # private / group
    target_id = request.POST.get('target_id', '')
    if not all([source_type, source_msg_id, target_type, target_id]):
        return JsonResponse({'error': '参数不完整'}, status=400)
    try:
        source_msg_id = int(source_msg_id)
        target_id = int(target_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': '参数格式错误'}, status=400)
    # 读取源消息
    original_sender = ''
    content = ''
    attach_file = None
    attach_name = ''
    attach_type = ''
    if source_type == 'private':
        msg = PrivateMessage.objects.filter(id=source_msg_id).first()
        if not msg:
            return JsonResponse({'error': '消息不存在'}, status=404)
        if msg.chat.user1 != request.user and msg.chat.user2 != request.user:
            return JsonResponse({'error': '无权访问该消息'}, status=403)
        if msg.is_deleted or msg.deleted_by_sender:
            return JsonResponse({'error': '已撤回或已删除的消息不能转发'}, status=400)
        original_sender = _get_user_title(msg.sender) or msg.sender.username
        content = msg.content
        if msg.attachment:
            attach_file = msg.attachment
            attach_name = msg.attachment_name
            attach_type = msg.attachment_type
    elif source_type == 'group':
        msg = GroupMessage.objects.filter(id=source_msg_id).first()
        if not msg:
            return JsonResponse({'error': '消息不存在'}, status=404)
        if not msg.group.is_member(request.user):
            return JsonResponse({'error': '无权访问该消息'}, status=403)
        if msg.is_deleted:
            return JsonResponse({'error': '已撤回的消息不能转发'}, status=400)
        original_sender = _get_user_title(msg.sender) or msg.sender.username
        content = msg.content
        if msg.attachment:
            attach_file = msg.attachment
            attach_name = msg.attachment_name
            attach_type = msg.attachment_type
    else:
        return JsonResponse({'error': '无效的源类型'}, status=400)
    forwarded_label = f'[转发自 {original_sender}]'
    # 发送到目标
    if target_type == 'private':
        chat = PrivateChat.objects.filter(id=target_id).first()
        if not chat:
            return JsonResponse({'error': '目标会话不存在'}, status=404)
        if chat.user1 != request.user and chat.user2 != request.user:
            return JsonResponse({'error': '无权发送到该会话'}, status=403)
        other = chat.user2 if chat.user1 == request.user else chat.user1
        if Blacklist.objects.filter(user=other, blocked_user=request.user).exists():
            return JsonResponse({'error': '对方已将你拉黑'}, status=403)
        if Blacklist.objects.filter(user=request.user, blocked_user=other).exists():
            return JsonResponse({'error': '你已拉黑对方，无法发送'}, status=403)
        new_msg = PrivateMessage.objects.create(
            chat=chat, sender=request.user,
            content=content, forwarded_from=forwarded_label,
            attachment=attach_file, attachment_name=attach_name, attachment_type=attach_type,
        )
        return JsonResponse({'status': 'ok', 'msg_id': new_msg.id, 'target_type': 'private'})
    elif target_type == 'group':
        group = GroupChat.objects.filter(id=target_id).first()
        if not group:
            return JsonResponse({'error': '目标群不存在'}, status=404)
        if not group.is_member(request.user):
            return JsonResponse({'error': '你不是该群成员'}, status=403)
        member = group.members.filter(user=request.user).first()
        if member and member.is_currently_muted():
            return JsonResponse({'error': '您已被群主禁言'}, status=403)
        new_msg = GroupMessage.objects.create(
            group=group, sender=request.user,
            content=content, forwarded_from=forwarded_label,
            attachment=attach_file, attachment_name=attach_name, attachment_type=attach_type,
        )
        return JsonResponse({'status': 'ok', 'msg_id': new_msg.id, 'target_type': 'group'})
    return JsonResponse({'error': '无效的目标类型'}, status=400)


# ========== 群@提及未读统计 ==========
@login_required
@require_GET
def group_unread_mentions(request, group_id):
    """获取当前用户在群中的未读@提及消息"""
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_member(request.user):
        return JsonResponse({'error': '无权访问'}, status=403)
    my_member = group.members.filter(user=request.user).first()
    last_read = my_member.last_read_message_id if my_member else 0
    username = request.user.username
    # 查找未读消息中 @了当前用户 或 @全体成员 的
    unread_msgs = group.messages.filter(
        id__gt=last_read, is_deleted=False
    ).exclude(sender=request.user)
    mentioned = []
    for m in unread_msgs:
        if not m.mentions:
            continue
        mention_list = m.mentions.split(',')
        if username in mention_list or '__all__' in mention_list:
            mentioned.append({
                'id': m.id,
                'sender': m.sender.username,
                'content': m.content[:100],
                'time': m.timestamp.strftime('%Y-%m-%d %H:%M'),
            })
    return JsonResponse({'count': len(mentioned), 'messages': mentioned[:20]})


# ========== 群解散 ==========
@login_required
@require_POST
def group_disband(request, group_id):
    """群主解散群聊"""
    group = get_object_or_404(GroupChat, id=group_id)
    if not group.is_owner(request.user):
        return JsonResponse({'error': '只有群主可以解散群聊'}, status=403)
    group_name = group.name
    group.delete()
    return JsonResponse({'status': 'ok', 'msg': f'群聊「{group_name}」已解散'})


def media_file(request, path):
    """服务附件文件：显式设置 charset=utf-8（文本不乱码）并支持 Range（音视频可拖动）"""
    import os
    import mimetypes
    from django.http import FileResponse, Http404
    full = os.path.normpath(os.path.join(settings.MEDIA_ROOT, path))
    if not full.startswith(os.path.normpath(settings.MEDIA_ROOT)) or not os.path.isfile(full):
        raise Http404
    ctype, _ = mimetypes.guess_type(full)
    if ctype is None:
        ctype = 'application/octet-stream'
    if ctype.startswith('text/') or ctype in ('application/json', 'application/xml'):
        ctype += '; charset=utf-8'
    f = open(full, 'rb')
    return FileResponse(f, content_type=ctype)
