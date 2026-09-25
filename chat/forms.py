import re
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

# 严格邮箱格式校验：用户名部分 + 合法域名（至少包含一个点，避免 a@a 这种假邮箱）
EMAIL_RE = re.compile(
    r"^(?P<user>[A-Za-z0-9._%+\-]+)@(?P<domain>[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)$"
)
# 常见的一次性/临时邮箱域名，注册时直接拒绝（可自行增删）
DISPOSABLE_DOMAINS = {
    'mailinator.com', 'mailinator.net', 'yopmail.com', 'guerrillamail.com',
    'tempmail.com', '10minutemail.com', 'throwawaymail.com', 'getnada.com',
    'temp-mail.org', 'sharklasers.com', 'trashmail.com', 'maildrop.cc',
    'discard.email', 'tempail.com', 'mytemp.email', 'emailondeck.com',
    'tempinbox.com', 'spam4.me', 'fakeinbox.com', 'mintemail.com',
}

class RegisterForm(forms.Form):
    username = forms.CharField(max_length=20, min_length=3, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': '可选填'}))
    password = forms.CharField(min_length=4, widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    confirm_password = forms.CharField(min_length=4, widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    agree_privacy = forms.BooleanField(required=True, error_messages={'required': '请先阅读并同意《隐私协议》'}, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    def clean_username(self):
        username = self.cleaned_data['username']
        if not re.match(r'^[A-Za-z0-9_]+$', username):
            raise ValidationError('用户名只能包含字母、数字和下划线')
        if User.objects.filter(username=username).exists():
            raise ValidationError('该用户名已被注册')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            return ''
        m = EMAIL_RE.match(email)
        if not m:
            raise ValidationError('邮箱格式不正确（例如 abc@example.com）')
        domain = m.group('domain').lower()
        if len(m.group('user')) > 64:
            raise ValidationError('邮箱用户名部分过长')
        if domain in DISPOSABLE_DOMAINS:
            raise ValidationError('请使用真实邮箱，不支持一次性临时邮箱')
        if User.objects.filter(email=email).exists():
            raise ValidationError('该邮箱已被注册')
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') != cleaned.get('confirm_password'):
            raise ValidationError('两次输入的密码不一致')
        return cleaned

class LoginForm(forms.Form):
    username = forms.CharField(max_length=20, widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))


class GroupCreateForm(forms.Form):
    JOIN_MODE_CHOICES = [
        ('open', '自由加入'),
        ('approval', '需审核'),
    ]
    name = forms.CharField(max_length=50, min_length=2, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '群名称（2-50字）'}))
    description = forms.CharField(max_length=200, required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '群描述（可选）'}))
    join_mode = forms.ChoiceField(choices=JOIN_MODE_CHOICES, initial='open', required=False, widget=forms.Select(attrs={'class': 'form-control'}))
    join_pin = forms.CharField(max_length=16, required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '入群PIN码（可选）'}))

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError('群名称不能为空')
        return name

    def clean_join_pin(self):
        pin = self.cleaned_data.get('join_pin', '').strip()
        if not pin:
            return None
        if not re.match(r'^[A-Za-z0-9]{4,16}$', pin):
            raise forms.ValidationError('PIN码需为4-16位字母或数字')
        return pin
