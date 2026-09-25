from django.http import HttpResponseForbidden
from .models import IPBlacklist

class IPBlacklistMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = request.META.get('REMOTE_ADDR', '')
        try:
            if IPBlacklist.objects.filter(ip_address=ip, is_active=True).exists():
                return HttpResponseForbidden('您的IP已被封禁')
        except Exception:
            pass
        return self.get_response(request)
