from django.urls import path, re_path
from django.views.static import serve
from django.conf import settings
from . import views
from . import game_views as views_game

urlpatterns = [
    path('api/user_info/<str:username>/', views.api_user_info, name='api_user_info'),
    path('api/groups/', views.api_groups, name='api_groups'),
    path('', views.login_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('chat/', views.chat_room, name='chat_room'),
    path('chat/public/', views.public_room, name='public_room'),
    path('verify-required/', views.verify_required_view, name='verify_required'),
    path('verify-email/', views.verify_code_view, name='verify_code'),
    path('verify-email/<str:token>/', views.verify_email_view, name='verify_email'),
    path('account/', views.account_view, name='account'),
    path('privacy/', views.privacy_view, name='privacy'),
    path('favorites/', views.favorites_view, name='favorites'),
    path('api/resend-verify/', views.resend_verify_email, name='resend_verify_email'),
    path('api/send/', views.send_message, name='send_message'),
    path('api/messages/', views.get_messages, name='get_messages'),
    path('api/online/', views.online_users, name='online_users'),
    path('api/users/', views.all_users, name='all_users'),
    path('api/heartbeat/', views.heartbeat, name='heartbeat'),
    path('api/status/', views.set_status, name='set_status'),
    # 私聊
    path('private/', views.private_chat_list, name='private_list'),
    path('private/<int:chat_id>/', views.private_chat_detail, name='private_detail'),
    path('api/private/start/', views.private_start, name='private_start'),
    path('api/private/list/', views.api_private_list, name='api_private_list'),
    path('api/private/<int:chat_id>/send/', views.private_send, name='private_send'),
    path('api/private/<int:chat_id>/messages/', views.private_messages, name='private_messages'),
    path('api/private/<int:chat_id>/delete/<int:msg_id>/', views.private_delete_message, name='private_delete_message'),
    path('api/private/<int:chat_id>/delete-chat/', views.private_delete_chat, name='private_delete_chat'),
    path('api/private/<int:chat_id>/pin/', views.private_pin_chat, name='private_pin_chat'),
    path('api/private/<int:chat_id>/mute/', views.private_mute_chat, name='private_mute_chat'),
    path('api/private/<int:chat_id>/search/', views.private_search, name='private_search'),
    path('api/private/<int:chat_id>/typing/', views.private_typing, name='private_typing'),
    path('api/recall/<int:msg_id>/', views.recall_message, name='recall_message'),
    path('api/private/<int:chat_id>/recall/<int:msg_id>/', views.private_recall_message, name='private_recall_message'),
    # 收藏
    path('api/favorite/add/', views.favorite_add, name='favorite_add'),
    path('api/favorite/remove/<int:fav_id>/', views.favorite_remove, name='favorite_remove'),
    # 消息转发
    path('api/forward/', views.forward_message, name='forward_message'),
    # 黑名单
    path('api/blacklist/add/', views.blacklist_add, name='blacklist_add'),
    path('api/blacklist/remove/', views.blacklist_remove, name='blacklist_remove'),
    path('api/blacklist/list/', views.blacklist_list, name='blacklist_list'),
    # 群聊
    path('groups/', views.group_list, name='group_list'),
    path('group/create/', views.group_create, name='group_create'),
    path('group/<int:group_id>/', views.group_detail, name='group_detail'),
    path('group/<int:group_id>/profile/', views.group_profile, name='group_profile'),
    path('group/<int:group_id>/members/', views.group_members, name='group_members'),
    path('api/group/<int:group_id>/send/', views.group_send, name='group_send'),
    path('api/group/<int:group_id>/messages/', views.group_messages, name='group_messages'),
    path('api/group/<int:group_id>/recall/<int:msg_id>/', views.group_recall, name='group_recall'),
    path('api/group/<int:group_id>/add-member/', views.group_add_member, name='group_add_member'),
    path('api/group/<int:group_id>/remove-member/', views.group_remove_member, name='group_remove_member'),
    path('api/group/<int:group_id>/set-admin/', views.group_set_admin, name='group_set_admin'),
    path('api/group/<int:group_id>/leave/', views.group_leave, name='group_leave'),
    path('api/group/<int:group_id>/announcement/save/', views.group_announcement_save, name='group_announcement_save'),
    path('api/group/<int:group_id>/mute-member/', views.group_mute_member, name='group_mute_member'),
    path('api/group/<int:group_id>/unmute-member/', views.group_unmute_member, name='group_unmute_member'),
    path('api/group/<int:group_id>/search/', views.group_search, name='group_search'),
    path('api/group/<int:group_id>/update-info/', views.group_update_info, name='group_update_info'),
    path('api/group/<int:group_id>/transfer/', views.group_transfer, name='group_transfer'),
    path('api/group/<int:group_id>/disband/', views.group_disband, name='group_disband'),
    path('api/group/<int:group_id>/unread-mentions/', views.group_unread_mentions, name='group_unread_mentions'),
    # 入群申请（需审核的群）
    path('api/group/<int:group_id>/join/', views.group_join, name='group_join'),
    path('api/group/<int:group_id>/join-requests/', views.group_join_requests, name='group_join_requests'),
    path('api/group/<int:group_id>/join-request/<int:req_id>/handle/', views.group_handle_join_request, name='group_handle_join_request'),
    path('api/groups/all/', views.api_all_groups, name='api_all_groups'),

    # 联机游戏（数字大逃杀）
    path('game/', views_game.game_page, name='game_page'),
    path('game/room/<str:room_id>/', views_game.game_page, name='game_room'),
    path('game/api/rooms/', views_game.api_rooms, name='game_api_rooms'),
    path('game/api/create/', views_game.api_create, name='game_api_create'),
    path('game/api/join/', views_game.api_join, name='game_api_join'),
    path('game/api/leave/', views_game.api_leave, name='game_api_leave'),
    path('game/api/disband/', views_game.api_disband, name='game_api_disband'),
    path('game/api/start/', views_game.api_start, name='game_api_start'),
    path('game/api/state/', views_game.api_state, name='game_api_state'),
    path('game/api/action/', views_game.api_action, name='game_api_action'),
]

# 附件文件由 Django 直接服务：保证 text/plain; charset=utf-8（中文不乱码）并支持 HTTP Range（音频可拖动播放）
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', views.media_file),
]
