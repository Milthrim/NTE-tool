"""Deterministic round state machine; no operating-system input in this module."""
from dataclasses import dataclass
import math

@dataclass
class Action:
    name: str
    key: str = ""

class Controller:
    def __init__(self, trigger_size=85, max_rounds=0, repeat=True):
        self.trigger_size = trigger_size
        self.max_rounds = max_rounds
        self.repeat = repeat
        self.rounds = 0
        self.target = False
        self.target_votes = 0
        self.in_round = False
        self.await_new = False
        self.result_counted = False
        self.last_button = None
        self.button_votes = 0
        self.last_click = -100.
        self.last_score_time = -100.
        self.note = None
        self.note_seen = -100.
        self.note_fired = False
        self.last_press = -100.
        self.held = ""
        self.blue_seen = -100.
        self.hold_started = -100.
        self.burst_key = ""
        self.burst_seen = -100.
        self.burst_started = -100.
        self.status = "等待游戏画面"

    def release(self):
        actions = [Action("release", self.held)] if self.held else []
        self.held = ""
        self.blue_seen = -100.
        self.hold_started = -100.
        return actions

    def suspend(self):
        self.burst_key = ""
        self.note = None
        self.note_fired = False
        self.target_votes = 0
        self.button_votes = 0
        return self.release()

    def tick(self, reading, now):
        actions = []
        if reading.playing:
            self.button_votes = 0
            if self.await_new:
                if reading.score is None or reading.score > 600:
                    self.status = "等待新一局分数归零"
                    return self.release()
                self.await_new = False
                self.target = False
                self.target_votes = 0
                self.result_counted = False
                self.note = None
                self.note_fired = False
            self.in_round = True
            if reading.score is not None:
                self.last_score_time = now
            self.target_votes = self.target_votes + 1 if reading.reached else 0
            if self.target_votes >= 2:
                self.target = True
            if self.target:
                self.burst_key = ""
                self.status = "已达到 9000 分，等待结算"
                return self.release()
            if reading.reached:
                self.burst_key = ""
                self.status = "正在确认 9000 分"
                return self.release()  # Stop at the first candidate; latch after confirmation.
            if now - self.last_score_time > 2.5:
                self.burst_key = ""
                self.status = "分数暂未识别，等待清晰画面"
                return self.release()
            n = reading.note
            # A blue note has a head and a tail. Its translucent arrow can
            # disappear for several frames as it crosses the camera.
            if self.held:
                if n and n.kind == "blue" and n.key == self.held:
                    self.blue_seen = now
                    self.note, self.note_seen = n, now
                    self.status = f"{self.held.upper()} · 持续长按"
                    return actions
                next_ready = n is not None and n.size >= self.trigger_size
                within_tail = now - self.blue_seen < 1.4 and now - self.hold_started < 3.0
                if within_tail and not next_ready:
                    self.status = f"{self.held.upper()} · 保持至长按尾部"
                    return actions
                actions += self.release()
            if self.burst_key:
                if n and n.kind == 'orange' and n.key == self.burst_key:
                    self.burst_seen = now
                next_ready = n is not None and (n.kind != 'orange' or n.key != self.burst_key) and n.size >= self.trigger_size
                if now - self.burst_seen < 1.4 and now - self.burst_started < 3.0 and not next_ready:
                    if now - self.last_press >= .075:
                        actions.append(Action('tap', self.burst_key))
                        self.last_press = now
                    self.status = f'{self.burst_key.upper()} · 持续连按'
                    return actions
                self.burst_key = ''
            if n is None:
                if self.note and self.note.kind == "orange" and now - self.note_seen < .30:
                    if now - self.last_press >= .075:
                        actions.append(Action("tap", self.note.key))
                        self.last_press = now
                    return actions
                if now - self.note_seen > .18:
                    self.note = None
                    self.note_fired = False
                    actions += self.release()
                self.status = "识别方向中"
                return actions
            previous = self.note
            same = (previous is not None and previous.key == n.key and previous.kind == n.kind
                    and math.hypot(previous.x - n.x, previous.y - n.y) < max(90, n.size * .9)
                    and n.size >= previous.size * .70 and now - self.note_seen < .3)
            if not same:
                actions += self.release()
                self.note_fired = False
            self.note = n
            self.note_seen = now
            labels = {"pink": "点按", "blue": "长按", "orange": "连按"}
            self.status = f"{n.key.upper()} · {labels[n.kind]} · 大小 {n.size:.0f}"
            threshold = min(self.trigger_size, 72) if n.kind in ("blue", "orange") else self.trigger_size
            if n.size < threshold:
                return actions
            if n.kind == "blue":
                if self.held != n.key:
                    actions += self.release()
                    actions.append(Action("hold", n.key))
                    self.held = n.key
                    self.blue_seen = now
                    self.hold_started = now
            elif n.kind == "orange":
                self.burst_key = n.key
                self.burst_seen = self.burst_started = now
                if now - self.last_press >= .075:
                    actions.append(Action("tap", n.key))
                    self.last_press = now
            elif not self.note_fired and now - self.last_press >= .13:
                actions.append(Action("tap", n.key))
                self.note_fired = True
                self.last_press = now
            return actions
        actions += self.release()
        self.burst_key = ''
        self.note = None
        self.note_fired = False
        if reading.button:
            self.button_votes = self.button_votes + 1 if reading.button == self.last_button else 1
            self.last_button = reading.button
            if self.button_votes < 2:
                self.status = "确认结算/开始按钮"
                return actions
            if reading.button == "retry" and not self.result_counted:
                if self.in_round:
                    self.rounds += 1
                self.result_counted = True
                self.in_round = False
                if not self.repeat or (self.max_rounds > 0 and self.rounds >= self.max_rounds):
                    self.status = "本次运行已完成"
                    return actions + [Action("stop")]
            if now - self.last_click >= 3:
                actions.append(Action("click", reading.button))
                self.last_click = now
                self.await_new = True
                self.status = "等待下一局"
            return actions
        self.button_votes = 0
        self.status = "等待结算或可识别界面"
        return actions
