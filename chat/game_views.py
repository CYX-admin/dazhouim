# -*- coding: utf-8 -*-
"""滨江校区游戏1 · 联机卡牌游戏视图"""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .game_logic import GameManager, CARD_NAMES, CARD_DESCS, CARD_COUNTS, MIN_PLAYERS, MAX_PLAYERS

manager = GameManager()


@login_required
def game_page(request, room_id=None):
    return render(request, "chat/game.html", {
        "initial_room": room_id or "",
        "card_names": CARD_NAMES,
        "card_descs": CARD_DESCS,
        "card_counts": CARD_COUNTS,
        "min_players": MIN_PLAYERS,
        "max_players": MAX_PLAYERS,
    })


@login_required
@require_GET
def api_rooms(request):
    return JsonResponse({"ok": True, "rooms": manager.list_rooms()})


@login_required
@require_POST
def api_create(request):
    rid = manager.create_room(str(request.user.id), request.user.username)
    return JsonResponse({"ok": True, "room_id": rid})


@login_required
@require_POST
def api_join(request):
    rid = (request.POST.get("room_id") or "").strip()
    ok, err = manager.join_room(rid, str(request.user.id), request.user.username)
    if not ok:
        return JsonResponse({"ok": False, "error": err})
    return JsonResponse({"ok": True, "room_id": rid})


@login_required
@require_POST
def api_leave(request):
    rid = (request.POST.get("room_id") or "").strip()
    ok, err = manager.leave_room(rid, str(request.user.id))
    if not ok:
        return JsonResponse({"ok": False, "error": err})
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_disband(request):
    rid = (request.POST.get("room_id") or "").strip()
    ok, err = manager.disband_room(rid, str(request.user.id))
    if not ok:
        return JsonResponse({"ok": False, "error": err})
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_start(request):
    rid = (request.POST.get("room_id") or "").strip()
    ok, err = manager.start_game(rid, str(request.user.id))
    if not ok:
        return JsonResponse({"ok": False, "error": err})
    return JsonResponse({"ok": True})


@login_required
@require_GET
def api_state(request):
    rid = request.GET.get("room_id", "").strip()
    state = manager.get_state(rid, str(request.user.id))
    if state is None:
        return JsonResponse({"ok": False, "error": "房间不存在或已解散"})
    return JsonResponse({"ok": True, "state": state})


@login_required
@require_POST
def api_action(request):
    try:
        data = json.loads(request.body or "{}")
    except Exception:
        data = request.POST
    rid = str(data.get("room_id", "")).strip()
    action = str(data.get("action", ""))
    ok, err, state = manager.action(rid, str(request.user.id), request.user.username, action, data)
    if not ok:
        return JsonResponse({"ok": False, "error": err})
    return JsonResponse({"ok": True, "state": state})
