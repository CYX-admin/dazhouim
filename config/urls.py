from django.contrib import admin
from django.urls import path, include, reverse_lazy
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/dashboard/', RedirectView.as_view(url=reverse_lazy('admin.index'), permanent=False)),
    path('admin/users/', RedirectView.as_view(url=reverse_lazy('admin.index'), permanent=False)),
    path('admin/ip-blacklist/', RedirectView.as_view(url=reverse_lazy('admin.index'), permanent=False)),
    path('admin/login-logs/', RedirectView.as_view(url=reverse_lazy('admin.index'), permanent=False)),
    path('admin/admins/', RedirectView.as_view(url=reverse_lazy('admin.index'), permanent=False)),
    path('admin/', admin.site.urls),
    path('', include('chat.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
