# -*- coding: utf-8 -*-
"""
滨江校区游戏1 · 联机卡牌游戏核心逻辑
====================================
规则（用户自定义，扑克牌数字版）：
- 一副扑克牌去掉大小王与 J/Q/K，只取数字 1-9，不看花色。
- 牌堆构成：1 有 6 张，9 有 2 张，2-8 各 4 张，共 36 张。
- 游戏开始每人摸 1 张起始手牌，随机座位，按顺时针顺序行动。
- 每回合：先从牌堆摸 1 张，再打出 1 张（9 不能打出）。
- 手牌上限：你的回合最多 2 张；不是你的回合（别人回合）最多 1 张。
- 出不了牌时必须弃牌过回合：由自己选择要弃的牌（9 不能主动弃出）。
- 对方免疫护盾不豁免手牌上限，超出的牌必须弃掉（无法弃牌的全 9 例外）。
- 牌效果：
    1 猜牌   : 猜一名角色的一张手牌点数，猜对则对方死亡
    2 看牌   : 查看一名角色的手牌（仅自己可见）
    3 比大小 : 与一名角色各选一张手牌比大小，点数小者死亡，相同无事
    4 护盾   : 直到你的下回合开始前，你免疫其他角色指向你的牌
    5 换牌   : 指定一名角色（可自己）弃一张手牌，再从牌堆摸一张
    6 观星   : 查看牌堆顶 2 张牌，并按任意顺序放回
    7 交换   : 令两名角色（可含自己）交换全部手牌
    8 强制   : 若你手中有 5 或 7，本回合必须打出 8；也可主动打出（无效果）
    9 死亡牌 : 不能打出，打出即死亡
- 死亡角色手牌公开并移出游戏。
- 只剩 1 名存活角色时游戏结束，该角色获胜。
- 牌堆用尽时游戏结束，展示所有存活角色手牌，按大小决定名次（大者胜）。

纯 Python 实现，无 Django 依赖，便于单元测试。
"""
import random
import threading
import time

# ---------- 牌堆构成 ----------
CARD_COUNTS = {1: 6, 2: 4, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 2}
CARD_NAMES = {
    1: "猜牌", 2: "看牌", 3: "比大小", 4: "护盾",
    5: "换牌", 6: "观星", 7: "交换", 8: "强制", 9: "死亡牌",
}
CARD_DESCS = {
    1: "猜一名角色的一张手牌点数，猜对则对方死亡",
    2: "查看一名角色的手牌（仅自己可见）",
    3: "与一名角色各选一张手牌比大小，点数小者死亡，相同无事",
    4: "直到你的下回合开始前，你免疫其他角色指向你的牌",
    5: "指定一名角色（可自己）弃一张手牌，再从牌堆摸一张",
    6: "查看牌堆顶 2 张牌，并按任意顺序放回牌堆",
    7: "令两名角色（可含自己）交换全部手牌",
    8: "强制牌：若你手中有 5 或 7，本回合必须打出；也可主动打出（无效果）",
    9: "死亡牌：不能打出，也不能用于比大小，打出即死亡",
}
MIN_PLAYERS = 2
MAX_PLAYERS = 6
ROOM_TTL = 7200  # 房间 2 小时无操作自动清理
TURN_TIMEOUT = 90   # 轮到的玩家 90 秒无操作，系统自动跳过其回合
PENDING_TIMEOUT = 60  # 比大小/弃牌/观星等待者 60 秒无响应，系统自动处理
# 手牌上限
MAX_HAND_ON_TURN = 2   # 你的回合（轮到你自己行动）手牌最多 2 张
MAX_HAND_OFF_TURN = 1  # 别人的回合手牌最多 1 张


def build_deck():
    deck = []
    for num, cnt in CARD_COUNTS.items():
        deck.extend([num] * cnt)
    random.shuffle(deck)
    return deck


class Player:
    def __init__(self, uid, username):
        self.uid = uid
        self.username = username
        self.hand = []            # 手牌（数字列表）
        self.alive = True
        self.shield = False       # 4 护盾
        self.dead_order = None    # 死亡顺序
        self.is_owner = False


class GameRoom:
    def __init__(self, room_id, owner_uid, owner_name):
        self.room_id = room_id
        self.owner_uid = owner_uid
        self.created_at = time.time()
        self.last_active = time.time()
        self.players = {}          # uid -> Player
        self.seats = []            # 座位顺序 uid 列表（随机）
        self.deck = []
        self.discard = []
        self.revealed = {}         # uid -> 死亡时公开的手牌
        self.status = "lobby"      # lobby / playing / finished
        self.turn_index = 0
        self.turn_no = 0
        self.phase = None          # draw / play / effect
        self.pending = None        # 待处理效果
        self.log = []              # [{turn, text, visible}]
        self.dead_count = 0
        self.winner = None
        self.ranking = []          # 最终排名 uid 列表（大者在前）
        self.private_views = {}    # uid -> {target_uid: [cards], "stargaze": [cards]}
        self.last_seen = {}        # uid -> 最后活跃时间戳（轮询/操作时更新，用于掉线检测）

    # ---------------- 基础工具 ----------------
    def touch(self):
        self.last_active = time.time()

    def mark_seen(self, uid):
        """记录玩家活跃（轮询/操作时调用）"""
        if uid in self.players:
            self.last_seen[uid] = time.time()

    def _idle_seconds(self, uid):
        now = time.time()
        if uid in self.last_seen:
            return now - self.last_seen[uid]
        # 从未活跃：从开局或加入时刻起算
        return now - self.created_at

    def add_log(self, text, visible="all"):
        self.log.append({"turn": self.turn_no, "text": text, "visible": visible})
        if len(self.log) > 200:
            self.log = self.log[-150:]

    def draw_from_deck(self):
        if not self.deck:
            return None
        return self.deck.pop(0)

    def alive_uids(self):
        return [u for u in self.seats if self.players[u].alive]

    def is_targetable(self, uid, by_uid=None):
        """是否可作为他人用牌目标（死亡不可，护盾免疫他人）"""
        p = self.players.get(uid)
        if not p or not p.alive:
            return False
        if p.shield and by_uid is not None and by_uid != uid:
            return False
        return True

    # ---------------- 回合控制 ----------------
    def _hand_limit(self, uid):
        """某玩家当前手牌上限：自己的回合 2 张，别人回合 1 张"""
        if self.status == "playing" and self.seats and self.seats[self.turn_index] == uid:
            return MAX_HAND_ON_TURN
        return MAX_HAND_OFF_TURN

    def _maybe_trigger_overflow_discard(self):
        """若存在手牌超出上限且可弃（含非 9 牌）的存活玩家，发起弃牌待处理，暂停回合推进。
        手牌全为 9 的玩家无法弃牌，视为规则内例外，不在此触发。
        返回是否触发。"""
        if self.status != "playing":
            return False
        for u in self.alive_uids():
            p = self.players[u]
            limit = self._hand_limit(u)
            if len(p.hand) > limit and any(c != 9 for c in p.hand):
                self.pending = {"type": "overflow_discard", "player": u}
                self.phase = "effect"
                self.add_log(f"{p.username} 手牌超出上限（{len(p.hand)}/{limit}），请弃掉一张牌（9 除外）")
                return True
        return False

    def _advance_turn(self):
        # 先执行手牌上限检查：任何存活玩家手牌超出上限时，先由其弃牌，回合暂不推进
        if self._maybe_trigger_overflow_discard():
            return
        n = len(self.seats)
        if n == 0:
            return
        for _ in range(n):
            self.turn_index = (self.turn_index + 1) % n
            u = self.seats[self.turn_index]
            if self.players[u].alive:
                break
        self.turn_no += 1
        cur = self.players[self.seats[self.turn_index]]
        cur.shield = False  # 护盾持续到"你的下回合开始"
        self.phase = "draw"
        self.pending = None

    def _check_end_by_players(self):
        alive = self.alive_uids()
        if len(alive) <= 1:
            self._finish()
            return True
        return False

    def _hand_key(self, uid):
        """排名键：手牌从大到小逐张比较，大者胜"""
        hand = sorted(self.players[uid].hand, reverse=True)
        return hand + [0] * 10

    def _finish(self):
        if self.status == "finished":
            return
        self.status = "finished"
        self.phase = None
        self.pending = None
        alive = self.alive_uids()
        self.ranking = sorted(alive, key=lambda u: self._hand_key(u), reverse=True)
        for u in alive:
            p = self.players[u]
            cards = " ".join(str(c) for c in sorted(p.hand, reverse=True)) or "（空手牌）"
            self.add_log(f"存活玩家 {p.username} 手牌：{cards}")
        if len(alive) == 1:
            self.winner = alive[0]
        elif self.ranking:
            self.winner = self.ranking[0]
        if self.winner:
            self.add_log(f"{self.players[self.winner].username} 获胜！")
        elif self.ranking:
            names = " > ".join(self.players[u].username for u in self.ranking)
            self.add_log(f"牌堆耗尽，按手牌大小排名：{names}")

    def _kill(self, uid, reason):
        p = self.players.get(uid)
        if not p or not p.alive:
            return False
        p.alive = False
        self.dead_count += 1
        p.dead_order = self.dead_count
        self.revealed[uid] = list(p.hand)
        cards = " ".join(str(c) for c in self.revealed[uid]) or "（空手牌）"
        self.add_log(f"{p.username} 死亡（{reason}），公开手牌：{cards}")
        self.discard.extend(p.hand)
        p.hand = []
        self._check_end_by_players()
        return True

    # ---------------- 效果校验（不修改状态） ----------------
    def _validate_guess(self, uid, payload):
        target = str(payload.get("target_id", ""))
        if target not in self.players or target == uid:
            return "猜牌目标无效"
        if not self.is_targetable(target, uid):
            return "目标已阵亡或处于护盾状态"
        try:
            guess = int(payload.get("guess"))
        except (TypeError, ValueError):
            return "猜数无效"
        if guess < 1 or guess > 9:
            return "猜数需在 1-9 之间"
        return None

    def _validate_peek(self, uid, payload):
        target = str(payload.get("target_id", ""))
        if target not in self.players or target == uid:
            return "看牌目标无效"
        if not self.is_targetable(target, uid):
            return "目标已阵亡或处于护盾状态"
        return None

    def _validate_compare(self, uid, payload):
        target = str(payload.get("target_id", ""))
        if target not in self.players or target == uid:
            return "比大小目标无效"
        if not self.is_targetable(target, uid):
            return "目标已阵亡或处于护盾状态"
        if len(self.players[uid].hand) < 1:
            return "你还需要一张手牌才能比大小"
        my_card = payload.get("my_card_id")
        if my_card not in self.players[uid].hand:
            return "你的备选手牌无效"
        if my_card == 9:
            return "9 是死亡牌，不能用于比大小"
        if len(self.players[target].hand) < 1:
            return "目标没有手牌，无法比大小"
        if all(c == 9 for c in self.players[target].hand):
            return "目标手牌全是死亡牌，无法比大小"
        return None

    def _validate_discard_draw(self, uid, payload):
        target = str(payload.get("target_id", ""))
        if target not in self.players:
            return "换牌目标无效"
        if target != uid and not self.is_targetable(target, uid):
            return "目标已阵亡或处于护盾状态"
        return None

    def _validate_swap(self, uid, payload):
        a = str(payload.get("target_a", ""))
        b = str(payload.get("target_b", ""))
        if a not in self.players or b not in self.players:
            return "交换目标无效"
        if a == b:
            return "两个目标不能相同"
        for t in (a, b):
            if t != uid and not self.is_targetable(t, uid):
                return "目标已阵亡或处于护盾状态"
        return None

    # ---------------- 效果执行 ----------------
    def _effect_guess(self, uid, payload):
        target = str(payload["target_id"])
        guess = int(payload["guess"])
        tp = self.players[target]
        if guess in tp.hand:
            self.add_log(f"{self.players[uid].username} 猜 {tp.username} 是「{guess}」——猜中了！")
            self._kill(target, f"被 {self.players[uid].username} 猜中手牌 {guess}")
        else:
            self.add_log(f"{self.players[uid].username} 猜 {tp.username} 是「{guess}」——猜错了")
        if self.status != "finished":
            self._advance_turn()

    def _effect_peek(self, uid, payload):
        target = str(payload["target_id"])
        tp = self.players[target]
        self.private_views.setdefault(uid, {})[target] = list(tp.hand)
        cards = " ".join(str(c) for c in tp.hand) or "（空手牌）"
        self.add_log(f"你查看了 {tp.username} 的手牌：{cards}", visible=uid)
        self.add_log(f"{self.players[uid].username} 查看了 {tp.username} 的手牌")
        self._advance_turn()

    def _effect_compare(self, uid, payload):
        target = str(payload["target_id"])
        my_card = payload["my_card_id"]
        self.pending = {"type": "compare", "player": target, "attacker": uid, "my_card": my_card}
        self.phase = "effect"
        self.add_log(f"{self.players[uid].username} 向 {self.players[target].username} 发起比大小，等待对方选牌")

    def _effect_shield(self, uid):
        self.players[uid].shield = True
        self.add_log(f"{self.players[uid].username} 打出护盾，直到其下回合开始前免疫所有用牌")
        self._advance_turn()

    def _effect_discard_draw(self, uid, payload):
        target = str(payload["target_id"])
        tp = self.players[target]
        self.add_log(f"{self.players[uid].username} 指定 {tp.username} 弃一张手牌并摸一张")
        discardable = [c for c in tp.hand if c != 9]
        if len(discardable) > 1:
            self.pending = {"type": "discard", "player": target}
            self.phase = "effect"
        elif len(discardable) == 1:
            c = discardable[0]
            tp.hand.remove(c)
            self.discard.append(c)
            self._draw_for(target)
            if self.status != "finished":
                self._advance_turn()
        else:
            # 空手或手牌全为 9：无可弃牌，跳过弃牌直接摸一张
            self._draw_for(target)
            if self.status != "finished":
                self._advance_turn()

    def _effect_stargaze(self, uid):
        n = min(2, len(self.deck))
        if n == 0:
            self._finish()
            return
        cards = self.deck[:n]
        self.deck = self.deck[n:]
        self.private_views.setdefault(uid, {})["stargaze"] = list(cards)
        self.pending = {"type": "stargaze", "player": uid, "cards": list(cards)}
        self.phase = "effect"
        self.add_log(f"你发动观星，看到了牌堆顶的牌：{'、'.join(str(c) for c in cards)}", visible=uid)
        self.add_log(f"{self.players[uid].username} 发动了观星")

    def _effect_swap(self, uid, payload):
        a = str(payload["target_a"])
        b = str(payload["target_b"])
        pa, pb = self.players[a], self.players[b]
        pa.hand, pb.hand = pb.hand, pa.hand
        self.add_log(f"{self.players[uid].username} 令 {pa.username} 与 {pb.username} 交换了手牌")
        self._advance_turn()

    def _effect_force(self, uid):
        self.add_log(f"{self.players[uid].username} 打出了强制牌（无效果）")
        self._advance_turn()

    def _draw_for(self, uid):
        card = self.draw_from_deck()
        if card is None:
            self._finish()
            return
        self.players[uid].hand.append(card)

    # ---------------- 动作入口 ----------------
    def _act_draw(self, uid):
        if uid != self.seats[self.turn_index]:
            return False, "还没轮到你摸牌"
        if self.phase != "draw":
            return False, "当前不是摸牌阶段"
        if self.pending:
            return False, "有操作待处理"
        card = self.draw_from_deck()
        if card is None:
            self._finish()
            return True, None
        self.players[uid].hand.append(card)
        self.phase = "play"
        self.add_log(f"{self.players[uid].username} 摸了一张牌")
        # 若手牌全是9（死亡牌，不能打出也不能弃出），自动跳过出牌避免卡死
        if all(c == 9 for c in self.players[uid].hand):
            self.add_log(f"{self.players[uid].username} 手牌全是死亡牌，无法弃牌，本回合跳过出牌")
            self._advance_turn()
        return True, None

    def _act_play(self, uid, payload):
        if uid != self.seats[self.turn_index]:
            return False, "还没轮到你出牌"
        if self.phase != "play":
            return False, "当前不是出牌阶段"
        if self.pending:
            return False, "有操作待处理"
        card = payload.get("card_id")
        hand = self.players[uid].hand
        if card not in hand:
            return False, "你没有这张牌"
        if card == 9:
            return False, "9 是死亡牌，打出即死亡，不能打出"
        # 8 强制规则：手中有 5 或 7 时必须打出 8
        has_5or7 = (5 in hand) or (7 in hand)
        if card != 8 and has_5or7 and 8 in hand:
            return False, "你手中有 5 或 7，本回合必须打出强制牌 8"
        # 先校验效果参数
        err = None
        if card == 1:
            err = self._validate_guess(uid, payload)
        elif card == 2:
            err = self._validate_peek(uid, payload)
        elif card == 3:
            err = self._validate_compare(uid, payload)
        elif card == 5:
            err = self._validate_discard_draw(uid, payload)
        elif card == 7:
            err = self._validate_swap(uid, payload)
        if err:
            return False, err
        # 打出
        hand.remove(card)
        self.discard.append(card)
        if card == 1:
            self._effect_guess(uid, payload)
        elif card == 2:
            self._effect_peek(uid, payload)
        elif card == 3:
            self._effect_compare(uid, payload)
        elif card == 4:
            self._effect_shield(uid)
        elif card == 5:
            self._effect_discard_draw(uid, payload)
        elif card == 6:
            self._effect_stargaze(uid)
        elif card == 7:
            self._effect_swap(uid, payload)
        else:  # 8
            self._effect_force(uid)
        return True, None

    def _act_pass(self, uid, card_id=None):
        """弃牌过回合：出不了牌时必须弃掉一张牌（9 除外，由玩家自选）后结束回合。
        手牌全为 9（无牌可弃）时可直接跳过；手中有 5/7 且有 8 时禁止跳过。"""
        if uid != self.seats[self.turn_index]:
            return False, "还没轮到你出牌"
        if self.phase != "play":
            return False, "当前不是出牌阶段"
        if self.pending:
            return False, "有操作待处理"
        hand = self.players[uid].hand
        if (5 in hand or 7 in hand) and 8 in hand:
            return False, "你手中有 5 或 7，必须打出 8，不能弃牌跳过"
        discardable = [c for c in hand if c != 9]
        if discardable:
            if card_id not in hand or card_id == 9:
                return False, "请选择要弃掉的一张牌（9 除外）"
            hand.remove(card_id)
            self.discard.append(card_id)
            self.add_log(f"{self.players[uid].username} 弃掉了「{card_id}」并跳过出牌")
        else:
            self.add_log(f"{self.players[uid].username} 手牌全是死亡牌，无法弃牌，跳过出牌")
        self._advance_turn()
        return True, None

    def _act_compare_choose(self, uid, payload):
        pen = self.pending
        if not pen or pen.get("type") != "compare" or pen.get("player") != uid:
            return False, "当前不需要你选牌"
        card = payload.get("card_id")
        if card not in self.players[uid].hand:
            return False, "你手牌中没有这张牌"
        if card == 9:
            return False, "9 是死亡牌，不能用于比大小"
        attacker = pen["attacker"]
        my_card = pen["my_card"]
        # 出牌者的牌此刻还在其手牌中，比较后一并弃置
        if my_card in self.players[attacker].hand:
            self.players[attacker].hand.remove(my_card)
            self.discard.append(my_card)
        self.players[uid].hand.remove(card)
        self.discard.append(card)
        a = self.players[attacker]
        t = self.players[uid]
        self.add_log(f"比大小：{a.username} 出「{my_card}」 vs {t.username} 出「{card}」")
        if my_card > card:
            self._kill(uid, "比大小落败")
        elif my_card < card:
            self._kill(attacker, "比大小落败")
        else:
            self.add_log("点数相同，无人死亡")
        self.pending = None
        if self.status != "finished":
            self._advance_turn()
        return True, None

    def _act_discard_choose(self, uid, payload):
        pen = self.pending
        if not pen or pen.get("type") != "discard" or pen.get("player") != uid:
            return False, "当前不需要你弃牌"
        card = payload.get("card_id")
        if card not in self.players[uid].hand:
            return False, "你手牌中没有这张牌"
        if card == 9:
            return False, "9 是死亡牌，不能弃出"
        self.players[uid].hand.remove(card)
        self.discard.append(card)
        self.pending = None
        self._draw_for(uid)
        if self.status != "finished":
            self._advance_turn()
        return True, None

    def _act_overflow_discard(self, uid, payload):
        """手牌超出上限时，玩家自选弃掉一张牌（9 除外）"""
        pen = self.pending
        if not pen or pen.get("type") != "overflow_discard" or pen.get("player") != uid:
            return False, "当前不需要你弃牌"
        card = payload.get("card_id")
        if card not in self.players[uid].hand:
            return False, "你手牌中没有这张牌"
        if card == 9:
            return False, "9 是死亡牌，不能弃出"
        self.players[uid].hand.remove(card)
        self.discard.append(card)
        self.pending = None
        self.add_log(f"{self.players[uid].username} 弃掉了「{card}」（手牌超出上限）")
        if self.status != "finished":
            self._advance_turn()
        return True, None

    def _act_stargaze_order(self, uid, payload):
        pen = self.pending
        if not pen or pen.get("type") != "stargaze" or pen.get("player") != uid:
            return False, "当前不需要你观星"
        cards = list(pen["cards"])
        top = payload.get("top_card")
        if top not in cards:
            return False, "请选择要放回牌堆顶的牌"
        other = [c for c in cards if c != top]
        self.deck = [top] + other + self.deck
        self.pending = None
        self.private_views.setdefault(uid, {})["stargaze"] = []
        self.add_log(f"你把 {'、'.join(str(c) for c in cards)} 放回了牌堆（{top} 在最上面）", visible=uid)
        self._advance_turn()
        return True, None

    def _act_surrender(self, uid):
        self._kill(uid, "主动认输")
        if self.status != "finished":
            if self.seats[self.turn_index] == uid:
                self._advance_turn()
            else:
                self._check_end_by_players()
        return True, None

    # ---------------- 超时自动处理（防卡死） ----------------
    def _tick_timeouts(self):
        """轮询时调用：掉线/超时玩家自动处理，保证对局永远能推进。
        返回本轮自动处理的事件数（供日志/前端提示）。"""
        if self.status != "playing":
            return 0
        acted = 0
        n = len(self.seats) + 3  # 最多循环处理这么多次，防止死循环
        for _ in range(n):
            if self.status != "playing":
                break
            # 1) pending 等待者超时 -> 自动响应
            if self.pending:
                pen = self.pending
                waiter = pen.get("player")
                if waiter and self._idle_seconds(waiter) > PENDING_TIMEOUT:
                    p = self.players.get(waiter)
                    if p and p.alive:
                        if pen["type"] == "compare":
                            hand = [c for c in p.hand if c != 9]
                            if hand:
                                self._act_compare_choose(waiter, {"card_id": max(hand)})
                                self.add_log("（对方长时间未响应，系统自动选牌）")
                                acted += 1
                                continue
                        elif pen["type"] == "discard":
                            discardable = [c for c in p.hand if c != 9]
                            if discardable:
                                self._act_discard_choose(waiter, {"card_id": min(discardable)})
                                self.add_log("（对方长时间未响应，系统自动弃牌）")
                            else:
                                # 无可弃牌（空手/全9）：跳过弃牌直接摸一张
                                self.pending = None
                                self._draw_for(waiter)
                                self.add_log("（对方长时间未响应且无可弃牌，系统自动摸牌）")
                                if self.status == "playing":
                                    self._advance_turn()
                            acted += 1
                            continue
                        elif pen["type"] == "overflow_discard":
                            discardable = [c for c in p.hand if c != 9]
                            if discardable:
                                self._act_overflow_discard(waiter, {"card_id": min(discardable)})
                                self.add_log("（对方长时间未响应，系统自动弃牌）")
                            else:
                                # 无可弃牌（全9例外）：解除等待让回合推进
                                self.pending = None
                                if self.status == "playing":
                                    self._advance_turn()
                                self.add_log("（对方长时间未响应，系统解除等待）")
                            acted += 1
                            continue
                        elif pen["type"] == "stargaze":
                            cards = pen["cards"]
                            if cards:
                                self._act_stargaze_order(waiter, {"top_card": cards[0]})
                                self.add_log("（长时间未响应，系统按原顺序放回牌堆）")
                                acted += 1
                                continue
                    # 等待者已死亡等异常：清除 pending 推进
                    self.pending = None
                    if self.status == "playing":
                        self._advance_turn()
                    acted += 1
                    continue
            # 2) 轮到当前玩家但超时 -> 自动跳过/打出强制8
            cur = self.seats[self.turn_index]
            if self.phase in ("draw", "play") and self._idle_seconds(cur) > TURN_TIMEOUT:
                curp = self.players[cur]
                if self.phase == "draw":
                    self._act_draw(cur)
                    self.add_log(f"（{curp.username} 长时间未操作，系统自动摸牌）")
                    acted += 1
                    continue
                # play 阶段：有强制8则自动打出，否则跳过
                if (5 in curp.hand or 7 in curp.hand) and 8 in curp.hand:
                    self._act_play(cur, {"card_id": 8})
                    self.add_log(f"（{curp.username} 长时间未操作，系统自动打出强制8）")
                else:
                    discardable = [c for c in curp.hand if c != 9]
                    if discardable:
                        self._act_pass(cur, discardable[0])
                        self.add_log(f"（{curp.username} 长时间未操作，系统自动弃牌过回合）")
                    else:
                        self._act_pass(cur, None)
                        self.add_log(f"（{curp.username} 长时间未操作，系统自动跳过回合）")
                acted += 1
                continue
            break
        return acted

    # ---------------- 统一动作入口 ----------------
    def action(self, uid, action, payload):
        p = self.players.get(uid)
        if not p:
            return False, "你不在该房间"
        if self.status != "playing":
            return False, "游戏未开始"
        if not p.alive:
            return False, "你已阵亡，只能观战"
        if action == "draw":
            return self._act_draw(uid)
        if action == "play":
            return self._act_play(uid, payload)
        if action == "compare_choose":
            return self._act_compare_choose(uid, payload)
        if action == "discard_choose":
            return self._act_discard_choose(uid, payload)
        if action == "overflow_discard":
            return self._act_overflow_discard(uid, payload)
        if action == "stargaze_order":
            return self._act_stargaze_order(uid, payload)
        if action == "pass":
            return self._act_pass(uid, payload.get("card_id"))
        if action == "surrender":
            return self._act_surrender(uid)
        return False, "未知操作"

    # ---------------- 状态输出 ----------------
    def get_state(self, uid):
        self.touch()
        self._tick_timeouts()
        seats = []
        for u in self.seats:
            p = self.players[u]
            idle = int(self._idle_seconds(u))
            seats.append({
                "uid": u,
                "username": p.username,
                "alive": p.alive,
                "shield": p.shield,
                "hand_count": len(p.hand),
                "is_owner": p.is_owner,
                "dead_order": p.dead_order,
                "revealed": self.revealed.get(u, []),
                "is_me": u == uid,
                "idle": idle,
                "is_online": self.status != "playing" or idle < TURN_TIMEOUT,
            })
        me = self.players.get(uid)
        # 构造对该玩家可见的 pending
        pend_view = None
        if self.pending and self.status == "playing":
            pen = self.pending
            if pen["type"] == "compare":
                if pen["player"] == uid:
                    pend_view = {"type": "compare_choose", "waiting": True, "player_uid": pen["player"]}
                elif pen["attacker"] == uid:
                    pend_view = {"type": "compare_wait", "my_card": pen["my_card"], "player_uid": pen["player"]}
                else:
                    pend_view = {"type": "compare_other", "attacker": pen["attacker"], "player_uid": pen["player"]}
            elif pen["type"] == "discard":
                if pen["player"] == uid:
                    pend_view = {"type": "discard_choose", "waiting": True, "player_uid": pen["player"]}
                else:
                    pend_view = {"type": "discard_other", "player": pen["player"], "player_uid": pen["player"]}
            elif pen["type"] == "stargaze":
                if pen["player"] == uid:
                    pend_view = {"type": "stargaze_choose", "cards": pen["cards"], "waiting": True, "player_uid": pen["player"]}
                else:
                    pend_view = {"type": "stargaze_other", "player": pen["player"], "player_uid": pen["player"]}
            elif pen["type"] == "overflow_discard":
                if pen["player"] == uid:
                    pend_view = {"type": "overflow_discard", "waiting": True, "player_uid": pen["player"]}
                else:
                    pend_view = {"type": "overflow_other", "player": pen["player"], "player_uid": pen["player"]}
        state = {
            "room_id": self.room_id,
            "status": self.status,
            "seats": seats,
            "deck_count": len(self.deck),
            "discard_count": len(self.discard),
            "turn_no": self.turn_no,
            "turn_uid": self.seats[self.turn_index] if self.seats and self.status == "playing" else None,
            "phase": self.phase,
            "pending": pend_view,
            "hand": list(me.hand) if me else [],
            "private_views": self.private_views.get(uid, {}),
            "logs": [l for l in self.log if l["visible"] == "all" or l["visible"] == uid][-60:],
            "winner": self.winner,
            "winner_name": self.players[self.winner].username if self.winner else None,
            "ranking": [{"uid": u, "username": self.players[u].username} for u in self.ranking],
            "owner_uid": self.owner_uid,
            "is_owner": uid == self.owner_uid,
            "min_players": MIN_PLAYERS,
            "max_players": MAX_PLAYERS,
            "card_names": CARD_NAMES,
            "turn_timeout": TURN_TIMEOUT,
            "pending_timeout": PENDING_TIMEOUT,
            "max_hand_on_turn": MAX_HAND_ON_TURN,
            "max_hand_off_turn": MAX_HAND_OFF_TURN,
        }
        return state


class GameManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.rooms = {}

    def _new_room_id(self):
        while True:
            rid = str(random.randint(100000, 999999))
            if rid not in self.rooms:
                return rid

    def _cleanup(self):
        now = time.time()
        for rid in list(self.rooms):
            if now - self.rooms[rid].last_active > ROOM_TTL:
                del self.rooms[rid]

    # ---------- 房间管理 ----------
    def create_room(self, uid, username):
        with self._lock:
            self._cleanup()
            rid = self._new_room_id()
            room = GameRoom(rid, uid, username)
            p = Player(uid, username)
            p.is_owner = True
            room.players[uid] = p
            room.seats = [uid]
            self.rooms[rid] = room
            return rid

    def join_room(self, rid, uid, username):
        with self._lock:
            room = self.rooms.get(rid)
            if not room:
                return False, "房间不存在"
            room.touch()
            if room.status != "lobby":
                return False, "游戏已开始，无法加入"
            if uid in room.players:
                return True, None
            if len(room.players) >= MAX_PLAYERS:
                return False, "房间已满"
            room.players[uid] = Player(uid, username)
            room.seats.append(uid)
            room.mark_seen(uid)
            room.add_log(f"{username} 加入了房间")
            return True, None

    def leave_room(self, rid, uid):
        with self._lock:
            room = self.rooms.get(rid)
            if not room:
                return False, "房间不存在"
            room.touch()
            if room.status == "playing":
                return False, "游戏进行中无法直接退出，可点击「认输」"
            if uid not in room.players:
                return False, "你不在该房间"
            name = room.players[uid].username
            del room.players[uid]
            room.seats.remove(uid)
            room.add_log(f"{name} 离开了房间")
            if not room.players:
                del self.rooms[rid]
            elif room.owner_uid == uid:
                room.owner_uid = room.seats[0]
                room.players[room.owner_uid].is_owner = True
                room.add_log(f"{room.players[room.owner_uid].username} 成为新房主")
            return True, None

    def disband_room(self, rid, uid):
        with self._lock:
            room = self.rooms.get(rid)
            if not room:
                return False, "房间不存在"
            if room.owner_uid != uid:
                return False, "只有房主能解散房间"
            del self.rooms[rid]
            return True, None

    def start_game(self, rid, uid):
        with self._lock:
            room = self.rooms.get(rid)
            if not room:
                return False, "房间不存在"
            room.touch()
            if room.owner_uid != uid:
                return False, "只有房主能开始游戏"
            if room.status != "lobby":
                return False, "游戏已开始"
            if len(room.players) < MIN_PLAYERS:
                return False, f"至少需要 {MIN_PLAYERS} 名玩家才能开始"
            random.shuffle(room.seats)
            room.deck = build_deck()
            room.discard = []
            room.revealed = {}
            room.log = []
            room.dead_count = 0
            room.private_views = {}
            room.turn_index = 0
            room.turn_no = 1
            room.status = "playing"
            for u in room.seats:
                room.players[u].hand = []
                room.players[u].alive = True
                room.players[u].shield = False
                room.players[u].dead_order = None
                room.players[u].is_owner = (u == room.owner_uid)
            # 每人 1 张起始手牌
            for u in room.seats:
                c = room.draw_from_deck()
                if c is not None:
                    room.players[u].hand.append(c)
                room.mark_seen(u)
            room.phase = "draw"
            room.add_log("游戏开始！每人 1 张起始手牌，随机座位，按顺时针出牌")
            room.add_log(f"牌堆共 {len(room.deck)} 张，当前轮到 {room.players[room.seats[0]].username}")
            return True, None

    def list_rooms(self):
        with self._lock:
            self._cleanup()
            out = []
            for rid, room in self.rooms.items():
                out.append({
                    "room_id": rid,
                    "status": room.status,
                    "player_count": len(room.players),
                    "max_players": MAX_PLAYERS,
                    "owner": room.players[room.owner_uid].username if room.owner_uid in room.players else "",
                })
            out.sort(key=lambda r: (r["status"] != "lobby", -r["player_count"]))
            return out

    # ---------- 动作 / 状态 ----------
    def action(self, rid, uid, username, action, payload):
        with self._lock:
            room = self.rooms.get(rid)
            if not room:
                return False, "房间不存在或已解散", None
            room.touch()
            room.mark_seen(uid)
            ok, err = room.action(uid, action, payload or {})
            if not ok:
                return False, err, None
            return True, None, room.get_state(uid)

    def get_state(self, rid, uid):
        with self._lock:
            room = self.rooms.get(rid)
            if not room:
                return None
            room.touch()
            room.mark_seen(uid)
            return room.get_state(uid)
