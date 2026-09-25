from django.urls import path
from . import views

urlpatterns = [
    path('', views.admin_index, name='admin_index'),
    path('login/', views.admin_login, name='admin_login'),
    path('logout/', views.admin_logout, name='admin_logout'),
    path('dashboard/', views.dashboard, name='admin_dashboard'),
    path('users/', views.user_list, name='admin_users'),
    path('users/<int:user_id>/ban/', views.user_ban, name='admin_user_ban'),
    path('users/<int:user_id>/mute/', views.user_mute, name='admin_user_mute'),
    path('users/<int:user_id>/email-exempt/', views.user_email_exempt, name='admin_user_email_exempt'),
    path('users/<int:user_id>/delete/', views.user_delete, name='admin_user_delete'),
    path('ip-blacklist/', views.ip_blacklist, name='admin_ip_blacklist'),
    path('ip-blacklist/add/', views.ip_add, name='admin_ip_add'),
    path('ip-blacklist/<int:ip_id>/toggle/', views.ip_toggle, name='admin_ip_toggle'),
    path('login-logs/', views.login_logs, name='admin_login_logs'),
    path('admins/', views.admin_manage, name='admin_manage'),
    path('admins/add/', views.admin_add, name='admin_add'),
    path('admins/<int:admin_id>/delete/', views.admin_delete, name='admin_delete'),
    path('change-password/', views.change_password, name='admin_change_password'),
]
