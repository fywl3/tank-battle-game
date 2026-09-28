# -*- coding: utf-8 -*-
"""
=============================================================================
游戏名称：坦克大战 · 浪尖儿社区硬核战术防守版 [LYL作品]
技术规范：Python 标准内置库 (Tkinter GUI + PCM 算法音效 + JSON 持久化)
开发作者：LYL
核心优化：开箱即用新手引导 + 纯鼠标/键盘全支持 + 跨平台兼容
=============================================================================
"""

import sys
import os
import math
import random
import time
import json
import io
import wave
import struct
import tkinter as tk
from tkinter import messagebox

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# ==================== 1. PCM 16-bit 算法音效 ====================
class SoundEngine:
    def __init__(self):
        self.sounds = {}
        self.enabled = HAS_WINSOUND
        if self.enabled:
            self._pre_synth_sounds()

    def _synth_wav(self, freq_start, freq_end, duration, wave_type="square", volume=0.3):
        sample_rate = 22050
        num_samples = int(sample_rate * duration)
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            frames = bytearray()
            for i in range(num_samples):
                t = i / sample_rate
                prog = i / max(1, num_samples)
                freq = freq_start + (freq_end - freq_start) * prog
                phase = 2 * math.pi * freq * t
                env = math.exp(-prog * 4.5) * volume

                if wave_type == "square":
                    val = 1.0 if math.sin(phase) > 0 else -1.0
                elif wave_type == "sawtooth":
                    val = 2.0 * (t * freq - math.floor(0.5 + t * freq))
                elif wave_type == "triangle":
                    val = 2.0 * abs(2.0 * (t * freq - math.floor(t * freq + 0.5))) - 1.0
                else:
                    val = math.sin(phase)

                sample = int(max(-32767, min(32767, val * env * 32767)))
                frames.extend(struct.pack('<h', sample))
            wf.writeframes(frames)
        return wav_io.getvalue()

    def _synth_chord(self, freqs, duration=0.4, volume=0.25):
        sample_rate = 22050
        num_samples = int(sample_rate * duration)
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            frames = bytearray()
            for i in range(num_samples):
                t = i / sample_rate
                prog = i / max(1, num_samples)
                env = math.exp(-prog * 3.0) * volume
                val = 0
                for f in freqs:
                    val += math.sin(2 * math.pi * f * t) / len(freqs)
                sample = int(max(-32767, min(32767, val * env * 32767)))
                frames.extend(struct.pack('<h', sample))
            wf.writeframes(frames)
        return wav_io.getvalue()

    def _pre_synth_sounds(self):
        try:
            self.sounds['shoot'] = self._synth_wav(380, 120, 0.1, "square", 0.25)
            self.sounds['explosion'] = self._synth_wav(140, 25, 0.3, "sawtooth", 0.4)
            self.sounds['hit'] = self._synth_wav(240, 80, 0.06, "triangle", 0.2)
            self.sounds['powerup'] = self._synth_wav(260, 880, 0.25, "sine", 0.35)
            self.sounds['base_damage'] = self._synth_wav(90, 220, 0.25, "sawtooth", 0.45)
            self.sounds['shockwave'] = self._synth_wav(160, 40, 0.4, "sine", 0.5)
            self.sounds['achieve'] = self._synth_chord([523.25, 659.25, 783.99, 1046.50], 0.35, 0.3)
        except Exception:
            self.enabled = False

    def play(self, sound_name):
        if not self.enabled or sound_name not in self.sounds:
            return
        try:
            winsound.PlaySound(self.sounds[sound_name], winsound.SND_MEMORY | winsound.SND_ASYNC)
        except Exception:
            pass

sound_fx = SoundEngine()

# ==================== 2. 常量与成就配置 ====================
GRID_SIZE = 26
TILE_SIZE = 24
CANVAS_SIZE = GRID_SIZE * TILE_SIZE

TILE_EMPTY = 0
TILE_BRICK = 1
TILE_STEEL = 2
TILE_TREE = 3
TILE_WATER = 4
TILE_BASE = 9

DIR_UP = 0
DIR_RIGHT = 1
DIR_DOWN = 2
DIR_LEFT = 3

DIR_VECTORS = [(0, -1), (1, 0), (0, 1), (-1, 0)]

ACHIEVEMENTS = [
    {"id": "first_blood", "name": "首战告捷", "icon": "🎖️", "desc": "在防守战中成功击毁第 1 辆敌军坦克"},
    {"id": "morning_rush", "name": "早八战神", "icon": "⏰", "desc": "成功在 3 分钟内通关防守并守住浪尖基地"},
    {"id": "full_gpa", "name": "满绩通关 (GPA 4.0)", "icon": "🎓", "desc": "以基地 100% 满装甲状态完成整场战役"},
    {"id": "kfc_craze", "name": "疯狂星期四", "icon": "🍗", "desc": "单局累计拾取 3 次定时战术空投物资"},
    {"id": "steel_fortress", "name": "钢铁长城", "icon": "🛡️", "desc": "使用基地加固使钛合金防线累计承受 5 次炮火"},
    {"id": "cyber_buddha", "name": "赛博佛祖", "icon": "📿", "desc": "利用减速泥沼同时封锁控制 3 辆敌军坦克"}
]

class AchievementManager:
    def __init__(self, filename="achievements.json"):
        # 存放在程序同级目录
        base_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
        self.filepath = os.path.join(base_dir, filename)
        self.unlocked = self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.unlocked, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def unlock(self, ach_id, effects):
        if not self.unlocked.get(ach_id, False):
            self.unlocked[ach_id] = True
            self.save()
            for a in ACHIEVEMENTS:
                if a["id"] == ach_id:
                    effects.add_floating_text(CANVAS_SIZE // 2, 80, f"🏆 解锁成就：【{a['name']}】!", "#ffd166")
                    sound_fx.play('achieve')
                    break

# ==================== 3. 实体类 ====================
def create_map_lyl():
    map_data = [[TILE_EMPTY for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    for y in range(6, 15):
        map_data[y][4] = TILE_STEEL; map_data[y][5] = TILE_STEEL
    for x in range(6, 9):
        map_data[13][x] = TILE_STEEL; map_data[14][x] = TILE_STEEL

    map_data[6][10] = TILE_BRICK; map_data[6][11] = TILE_BRICK
    map_data[7][11] = TILE_BRICK; map_data[7][12] = TILE_BRICK
    map_data[6][14] = TILE_BRICK; map_data[6][15] = TILE_BRICK
    map_data[7][13] = TILE_BRICK; map_data[7][14] = TILE_BRICK
    map_data[8][12] = TILE_BRICK; map_data[8][13] = TILE_BRICK
    map_data[9][12] = TILE_BRICK; map_data[9][13] = TILE_BRICK
    for y in range(10, 15):
        map_data[y][12] = TILE_BRICK; map_data[y][13] = TILE_BRICK

    for y in range(6, 15):
        map_data[y][18] = TILE_STEEL; map_data[y][19] = TILE_STEEL
    for x in range(20, 23):
        map_data[13][x] = TILE_STEEL; map_data[14][x] = TILE_STEEL

    for x in range(7, 19):
        if x % 2 == 0:
            map_data[17][x] = TILE_TREE; map_data[18][x] = TILE_TREE

    for r in range(16, 18):
        map_data[r][2] = TILE_WATER; map_data[r][3] = TILE_WATER
        map_data[r][22] = TILE_WATER; map_data[r][23] = TILE_WATER

    bx, by = 12, 24
    map_data[by][bx] = TILE_BASE; map_data[by][bx+1] = TILE_BASE
    map_data[by+1][bx] = TILE_BASE; map_data[by+1][bx+1] = TILE_BASE

    set_base_wall(map_data, TILE_BRICK)
    return map_data

def set_base_wall(map_data, tile_type):
    map_data[23][11] = tile_type; map_data[23][12] = tile_type
    map_data[23][13] = tile_type; map_data[23][14] = tile_type
    map_data[24][11] = tile_type; map_data[24][14] = tile_type
    map_data[25][11] = tile_type; map_data[25][14] = tile_type

class MudZone:
    def __init__(self, x, y, radius=95, duration=360):
        self.x, self.y, self.radius, self.duration, self.alive = x, y, radius, duration, True
    def update(self):
        self.duration -= 1
        if self.duration <= 0: self.alive = False

class PowerUp:
    def __init__(self, x, y, p_type):
        self.x, self.y, self.size, self.type, self.life, self.alive = x, y, 24, p_type, 720, True

class Bullet:
    def __init__(self, x, y, direction, is_player, speed=7.2, damage=1, is_ap=False):
        self.x, self.y, self.dir, self.is_player, self.speed, self.damage, self.is_ap = x, y, direction, is_player, speed, damage, is_ap
        self.radius, self.active = (4.2 if is_ap else 3.2), True

    def update(self, map_data, tanks, base_obj, effects):
        if not self.active: return
        vx, vy = DIR_VECTORS[self.dir]
        self.x += vx * self.speed
        self.y += vy * self.speed

        if random.random() < 0.4:
            effects.particles.append({
                'x': self.x, 'y': self.y, 'vx': -vx * 0.5, 'vy': -vy * 0.5,
                'life': 0.4, 'decay': 0.15, 'radius': 1.5,
                'color': '#38bdf8' if self.is_player else '#f87171'
            })

        if self.x < 0 or self.x > CANVAS_SIZE or self.y < 0 or self.y > CANVAS_SIZE:
            self.active = False
            return

        gx, gy = int(self.x // TILE_SIZE), int(self.y // TILE_SIZE)
        if 0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE:
            tile = map_data[gy][gx]
            if tile == TILE_BRICK:
                map_data[gy][gx] = TILE_EMPTY
                self.active = False
                effects.add_explosion(self.x, self.y, 6, '#f39c12')
                sound_fx.play('hit')
                return
            elif tile == TILE_STEEL:
                self.active = False
                effects.add_spark(self.x, self.y)
                sound_fx.play('hit')
                return
            elif tile == TILE_BASE:
                self.active = False
                base_obj.take_damage(self.damage, effects)
                return

        for t in tanks:
            if not t.alive or self.is_player == t.is_player: continue
            if t.x <= self.x <= t.x + t.size and t.y <= self.y <= t.y + t.size:
                self.active = False
                t.take_damage(self.damage, effects)
                break

class Tank:
    def __init__(self, x, y, direction, is_player=False, t_type='normal'):
        self.x, self.y, self.size, self.dir, self.is_player, self.type = x, y, 23, direction, is_player, t_type
        self.base_speed = 1.9 if is_player else (1.8 if t_type == 'scout' else (1.1 if t_type == 'siege' else 1.3))
        self.speed = self.base_speed
        self.hp = 1 if is_player else (3 if t_type == 'siege' else (2 if t_type == 'raider' else 1))
        self.max_hp = self.hp
        self.alive = True
        self.shoot_cooldown = 0
        self.reload_time = 36 if is_player else (50 if t_type == 'siege' else 38)
        self.change_dir_timer, self.stuck_timer, self.shield_timer = 0, 0, (120 if is_player else 0)

    def can_move_at(self, test_x, test_y, map_data, tanks):
        if test_x < 2 or test_x + self.size > CANVAS_SIZE - 2 or test_y < 2 or test_y + self.size > CANVAS_SIZE - 2:
            return False
        min_gx, max_gx = int(test_x // TILE_SIZE), int((test_x + self.size - 0.5) // TILE_SIZE)
        min_gy, max_gy = int(test_y // TILE_SIZE), int((test_y + self.size - 0.5) // TILE_SIZE)

        for gy in range(min_gy, max_gy + 1):
            for gx in range(min_gx, max_gx + 1):
                if 0 <= gy < GRID_SIZE and 0 <= gx < GRID_SIZE:
                    if map_data[gy][gx] in (TILE_BRICK, TILE_STEEL, TILE_WATER, TILE_BASE):
                        return False

        for t in tanks:
            if t == self or not t.alive: continue
            if (test_x < t.x + t.size and test_x + self.size > t.x and test_y < t.y + t.size and test_y + self.size > t.y):
                if (test_x - t.x)**2 + (test_y - t.y)**2 > (self.x - t.x)**2 + (self.y - t.y)**2:
                    continue
                return False
        return True

    def move(self, direction, map_data, tanks):
        self.dir = direction
        vx, vy = DIR_VECTORS[direction]
        next_x, next_y = self.x + vx * self.speed, self.y + vy * self.speed

        if self.can_move_at(next_x, next_y, map_data, tanks):
            self.x, self.y, self.stuck_timer = next_x, next_y, 0
            return True

        snap_thresh = 9
        if direction in (DIR_UP, DIR_DOWN):
            snap1 = math.floor(self.x / TILE_SIZE) * TILE_SIZE
            snap2 = snap1 + TILE_SIZE
            if abs(self.x - snap1) <= snap_thresh and self.can_move_at(snap1, next_y, map_data, tanks):
                self.x += (snap1 - self.x) * 0.6; self.y, self.stuck_timer = next_y, 0
                return True
            elif abs(self.x - snap2) <= snap_thresh and self.can_move_at(snap2, next_y, map_data, tanks):
                self.x += (snap2 - self.x) * 0.6; self.y, self.stuck_timer = next_y, 0
                return True
        elif direction in (DIR_LEFT, DIR_RIGHT):
            snap1 = math.floor(self.y / TILE_SIZE) * TILE_SIZE
            snap2 = snap1 + TILE_SIZE
            if abs(self.y - snap1) <= snap_thresh and self.can_move_at(next_x, snap1, map_data, tanks):
                self.y += (snap1 - self.y) * 0.6; self.x, self.stuck_timer = next_x, 0
                return True
            elif abs(self.y - snap2) <= snap_thresh and self.can_move_at(next_x, snap2, map_data, tanks):
                self.y += (snap2 - self.y) * 0.6; self.x, self.stuck_timer = next_x, 0
                return True

        self.stuck_timer += 1
        return False

    def shoot(self, bullets, is_dual=False):
        if self.shoot_cooldown > 0: return
        self.shoot_cooldown = self.reload_time
        vx, vy = DIR_VECTORS[self.dir]
        bx = self.x + self.size / 2 + vx * (self.size / 2 + 3)
        by = self.y + self.size / 2 + vy * (self.size / 2 + 3)
        b_speed = 7.2 if self.is_player else 5.0
        b_dmg = 2 if (self.type == 'siege' and not self.is_player) else 1
        bullets.append(Bullet(bx, by, self.dir, self.is_player, b_speed, b_dmg, self.is_player and is_dual))
        if self.is_player: sound_fx.play('shoot')

    def update_ai(self, map_data, tanks, bullets, target_player, mud_zones, base_obj):
        in_mud = any(mz.alive and math.hypot(mz.x - (self.x + 12), mz.y - (self.y + 12)) < mz.radius for mz in mud_zones)
        self.speed = self.base_speed * 0.4 if in_mud else self.base_speed
        self.change_dir_timer -= 1
        all_dirs = [DIR_UP, DIR_RIGHT, DIR_DOWN, DIR_LEFT]
        opposite_dir = (self.dir + 2) % 4

        if self.stuck_timer > 2: self.shoot(bullets)

        if self.stuck_timer > 4 or self.change_dir_timer <= 0:
            target_x, target_y = base_obj.x + 24, base_obj.y + 24
            if self.type == 'scout' and target_player and target_player.alive:
                target_x, target_y = target_player.x, target_player.y
            elif self.type == 'raider' and random.random() < 0.5 and target_player and target_player.alive:
                target_x, target_y = target_player.x, target_player.y

            best_dir, best_score, valid_dirs = self.dir, -99999, []
            for d in all_dirs:
                vx, vy = DIR_VECTORS[d]
                tx, ty = self.x + vx * 6, self.y + vy * 6
                if self.can_move_at(tx, ty, map_data, tanks):
                    valid_dirs.append(d)
                    score = -math.hypot(tx - target_x, ty - target_y)
                    if d == self.dir: score += 45
                    if d == opposite_dir: score -= 120
                    if self.type == 'siege' and d == DIR_DOWN: score += 70
                    if score > best_score:
                        best_score, best_dir = score, d

            if valid_dirs:
                self.dir = best_dir
            else:
                self.dir = random.choice([d for d in all_dirs if d != opposite_dir])
                self.shoot(bullets)

            self.change_dir_timer = random.randint(25, 55)
            self.stuck_timer = 0

        self.move(self.dir, map_data, tanks)
        if random.random() < (0.02 if in_mud else (0.05 if self.type == 'siege' else 0.038)):
            self.shoot(bullets)

    def take_damage(self, dmg, effects):
        if self.shield_timer > 0:
            effects.add_spark(self.x + 12, self.y + 12)
            effects.add_floating_text(self.x + 12, self.y, 'BLOCK!', '#38bdf8')
            sound_fx.play('hit')
            return
        self.hp -= dmg
        if self.hp <= 0:
            self.alive = False
            effects.add_explosion(self.x + 12, self.y + 12, 20, '#ff4757')
            effects.trigger_shake(5)
            sound_fx.play('explosion')
        else:
            effects.add_spark(self.x + 12, self.y + 12)
            sound_fx.play('hit')

class BaseHQ:
    def __init__(self):
        self.x, self.y, self.max_hp, self.hp, self.destroyed, self.steel_wall_timer = 12 * TILE_SIZE, 24 * TILE_SIZE, 5, 5, False, 0

    def take_damage(self, dmg, effects):
        if self.destroyed: return
        self.hp -= dmg
        sound_fx.play('base_damage')
        effects.add_explosion(self.x + 24, self.y + 24, 18, '#ff4757')
        effects.trigger_shake(7)
        effects.add_floating_text(self.x + 24, self.y - 12, f"基地受创! HP -{dmg}", '#ff4d4d')
        if self.hp <= 0:
            self.hp, self.destroyed = 0, True
            effects.add_explosion(self.x + 24, self.y + 24, 40, '#e74c3c')
            effects.trigger_shake(12)
            sound_fx.play('explosion')

    def repair(self, map_data, effects):
        self.hp = min(self.max_hp, self.hp + 2)
        self.steel_wall_timer = 480
        set_base_wall(map_data, TILE_STEEL)
        effects.add_floating_text(self.x + 24, self.y - 12, '基地抢修 & 合金防护!', '#4ade80')
        sound_fx.play('powerup')

    def update(self, map_data):
        if self.steel_wall_timer > 0:
            self.steel_wall_timer -= 1
            if self.steel_wall_timer == 0: set_base_wall(map_data, TILE_BRICK)

class EffectManager:
    def __init__(self):
        self.particles, self.floating_texts, self.shake_time, self.shake_magnitude = [], [], 0, 0

    def trigger_shake(self, magnitude=6, duration=12):
        self.shake_magnitude, self.shake_time = magnitude, duration

    def add_explosion(self, x, y, count=15, color='#ff4757'):
        for _ in range(count):
            angle, speed = random.uniform(0, math.pi * 2), random.uniform(1.5, 5.0)
            self.particles.append({'x': x, 'y': y, 'vx': math.cos(angle) * speed, 'vy': math.sin(angle) * speed, 'life': 1.0, 'decay': random.uniform(0.05, 0.08), 'radius': random.uniform(2, 4.5), 'color': color})

    def add_shockwave_ring(self, x, y, radius=150):
        for i in range(30):
            angle = (math.pi * 2 / 30) * i
            self.particles.append({'x': x + math.cos(angle) * 8, 'y': y + math.sin(angle) * 8, 'vx': math.cos(angle) * 4.5, 'vy': math.sin(angle) * 4.5, 'life': 1.0, 'decay': 0.045, 'radius': 4, 'color': '#f59e0b'})

    def add_spark(self, x, y):
        for _ in range(6):
            angle, speed = random.uniform(0, math.pi * 2), random.uniform(1.2, 2.8)
            self.particles.append({'x': x, 'y': y, 'vx': math.cos(angle) * speed, 'vy': math.sin(angle) * speed, 'life': 1.0, 'decay': 0.08, 'radius': 2, 'color': '#f1c40f'})

    def add_floating_text(self, x, y, text, color='#ffd166'):
        self.floating_texts.append({'x': x, 'y': y, 'text': text, 'color': color, 'life': 1.0, 'vy': -0.9})

    def update(self):
        if self.shake_time > 0: self.shake_time -= 1
        for p in self.particles[:]:
            p['x'] += p['vx']; p['y'] += p['vy']; p['life'] -= p['decay']
            if p['life'] <= 0: self.particles.remove(p)
        for ft in self.floating_texts[:]:
            ft['y'] += ft['vy']; ft['life'] -= 0.018
            if ft['life'] <= 0: self.floating_texts.remove(ft)

# ==================== 4. 主 GUI 窗口与渲染引擎 ====================
class TankBattleGame:
    def __init__(self, root):
        self.root = root
        self.root.title("坦克大战 · 浪尖儿社区战术防守版 [LYL作品]")
        self.root.geometry("980x730")
        self.root.resizable(False, False)
        self.root.configure(bg="#070d18")

        self.achieve_mgr = AchievementManager()
        self.effects = EffectManager()

        self.game_running = False
        self.game_paused = False
        self.score = 0
        self.current_wave = 1
        self.wave_enemies_left = [5, 5, 5]
        self.enemy_spawn_timer = 0
        self.airdrop_timer = 1050
        self.dual_cannon_timer = 0
        self.airdrop_pickup_count = 0
        self.current_bg_type = "poster1"

        self.keys = {'up': False, 'down': False, 'left': False, 'right': False, 'fire': False}
        self.map_data = create_map_lyl()
        self.base_obj = BaseHQ()
        self.player = Tank(9 * TILE_SIZE, 24 * TILE_SIZE, DIR_UP, is_player=True)
        self.enemies, self.bullets, self.powerups, self.mud_zones = [], [], [], []

        self._build_ui()
        self._bind_events()
        self.init_game()
        
        self.root.focus_force()
        self.canvas.focus_set()
        self.root.after(16, self.game_loop)

    def _build_ui(self):
        top_frame = tk.Frame(self.root, bg="#0d1b2a", bd=1, relief="solid")
        top_frame.pack(fill="x", padx=10, pady=6)

        title_lbl = tk.Label(top_frame, text="坦克大战 · 浪尖儿战术防守", font=("Microsoft YaHei", 14, "bold"), fg="#90e0ef", bg="#0d1b2a")
        title_lbl.pack(side="left", padx=10)

        badge_lbl = tk.Label(top_frame, text="★ 开发者: LYL", font=("Microsoft YaHei", 10, "bold"), fg="#000", bg="#ffd166", padx=8, pady=2)
        badge_lbl.pack(side="right", padx=10)

        self.status_frame = tk.Frame(self.root, bg="#000", bd=1, relief="ridge")
        self.status_frame.pack(fill="x", padx=10, pady=2)

        self.lbl_wave = tk.Label(self.status_frame, text="战术波次: 1/3", font=("Microsoft YaHei", 10, "bold"), fg="#ffd166", bg="#000")
        self.lbl_wave.pack(side="left", expand=True)

        self.lbl_base = tk.Label(self.status_frame, text="基地装甲: 100% (5/5)", font=("Microsoft YaHei", 10, "bold"), fg="#4ade80", bg="#000")
        self.lbl_base.pack(side="left", expand=True)

        self.lbl_enemies = tk.Label(self.status_frame, text="敌军剩余: 15", font=("Microsoft YaHei", 10, "bold"), fg="#f87171", bg="#000")
        self.lbl_enemies.pack(side="left", expand=True)

        self.lbl_airdrop = tk.Label(self.status_frame, text="空投倒计时: 18s", font=("Microsoft YaHei", 10, "bold"), fg="#00b4d8", bg="#000")
        self.lbl_airdrop.pack(side="left", expand=True)

        self.lbl_score = tk.Label(self.status_frame, text="积分: 0", font=("Microsoft YaHei", 10, "bold"), fg="#ffd166", bg="#000")
        self.lbl_score.pack(side="left", expand=True)

        self.lbl_lives = tk.Label(self.status_frame, text="复活: ∞ (无限)", font=("Microsoft YaHei", 10, "bold"), fg="#4ade80", bg="#000")
        self.lbl_lives.pack(side="left", expand=True)

        main_frame = tk.Frame(self.root, bg="#070d18")
        main_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(main_frame, width=CANVAS_SIZE, height=CANVAS_SIZE, bg="#050b14", highlightthickness=2, highlightbackground="#415a77", takefocus=1)
        self.canvas.pack(side="left", padx=5)
        self.canvas.bind("<Button-1>", lambda e: self.canvas.focus_set())

        side_panel = tk.Frame(main_frame, width=260, bg="#1b263b", bd=1, relief="ridge")
        side_panel.pack(side="right", fill="y", padx=5)
        side_panel.pack_propagate(False)

        c1 = tk.LabelFrame(side_panel, text="🎮 操作指令 (全端支持)", font=("Microsoft YaHei", 10, "bold"), fg="#90e0ef", bg="#1b263b", padx=6, pady=4)
        c1.pack(fill="x", padx=6, pady=4)
        ctrl_text = "W A S D / 方向键 : 疾速移位\nJ / 空格键 : 连发射击 (0.6秒/发)\nP 键 : 战术暂停/继续"
        tk.Label(c1, text=ctrl_text, font=("Microsoft YaHei", 9), fg="#e0e1dd", bg="#1b263b", justify="left").pack(anchor="w")

        c2 = tk.LabelFrame(side_panel, text="📦 战术空投 (每15~20秒)", font=("Microsoft YaHei", 10, "bold"), fg="#90e0ef", bg="#1b263b", padx=6, pady=4)
        c2.pack(fill="x", padx=6, pady=4)
        desc = "💥 战术震荡波: 锁定全体敌军震创\n❄️ 减速泥沼: 精准封锁敌军移速\n🛡️ 基地修整: 修复并加固铁壁\n⚡ 穿甲双联: 高速双发穿甲弹\n🔰 动能护盾: 获得6秒无敌护盾"
        tk.Label(c2, text=desc, font=("Microsoft YaHei", 8), fg="#caf0f8", bg="#1b263b", justify="left").pack(anchor="w")

        c3 = tk.LabelFrame(side_panel, text="🏆 荣耀与展馆", font=("Microsoft YaHei", 10, "bold"), fg="#90e0ef", bg="#1b263b", padx=6, pady=4)
        c3.pack(fill="x", padx=6, pady=4)
        btn_achieve = tk.Button(c3, text="🏆 查看大学生专属成就展馆", font=("Microsoft YaHei", 9, "bold"), bg="#ffd166", fg="#000", command=self.open_achieve_dialog)
        btn_achieve.pack(fill="x", pady=2)

        tk.Label(c3, text="选择底图模式：", font=("Microsoft YaHei", 8), fg="#caf0f8", bg="#1b263b").pack(anchor="w", pady=(4,0))
        self.bg_var = tk.StringVar(value="poster1")
        bg_menu = tk.OptionMenu(c3, self.bg_var, "poster1", "poster2", "classic", command=self.on_bg_change)
        bg_menu.config(font=("Microsoft YaHei", 8), bg="#0d1b2a", fg="#fff", width=18)
        bg_menu.pack(fill="x", pady=2)

        self.buff_label = tk.Label(c3, text="[当前无生效BUFF]", font=("Microsoft YaHei", 8, "bold"), fg="#38bdf8", bg="#1b263b")
        self.buff_label.pack(fill="x", pady=3)

        c4 = tk.LabelFrame(side_panel, text="🎯 战役调度", font=("Microsoft YaHei", 10, "bold"), fg="#90e0ef", bg="#1b263b", padx=6, pady=4)
        c4.pack(fill="x", padx=6, pady=4)
        tk.Button(c4, text="重新布防 (Restart)", font=("Microsoft YaHei", 9, "bold"), bg="#00b4d8", fg="#fff", command=self.restart_game).pack(fill="x", pady=2)
        tk.Button(c4, text="暂停 / 继续 (Pause)", font=("Microsoft YaHei", 9), bg="#415a77", fg="#fff", command=self.toggle_pause).pack(fill="x", pady=2)

        tk.Label(side_panel, text="独立设计与制作：LYL\n浪尖儿大学生社区 · 2026战术版", font=("Microsoft YaHei", 8), fg="#778da9", bg="#1b263b", justify="center").pack(side="bottom", pady=6)

    def _bind_events(self):
        self.root.bind_all("<KeyPress>", self._on_key_press)
        self.root.bind_all("<KeyRelease>", self._on_key_release)

    def _on_key_press(self, event):
        kc = event.keycode
        sym = event.keysym.lower()
        char = event.char.lower() if event.char else ""

        if kc in (87, 38) or sym in ('w', 'up') or char == 'w': self.keys['up'] = True
        elif kc in (83, 40) or sym in ('s', 'down') or char == 's': self.keys['down'] = True
        elif kc in (65, 37) or sym in ('a', 'left') or char == 'a': self.keys['left'] = True
        elif kc in (68, 39) or sym in ('d', 'right') or char == 'd': self.keys['right'] = True

        if kc in (74, 32) or sym in ('j', 'space') or char in ('j', ' '): self.keys['fire'] = True
        if kc == 80 or sym == 'p' or char == 'p': self.toggle_pause()

    def _on_key_release(self, event):
        kc = event.keycode
        sym = event.keysym.lower()
        char = event.char.lower() if event.char else ""

        if kc in (87, 38) or sym in ('w', 'up') or char == 'w': self.keys['up'] = False
        if kc in (83, 40) or sym in ('s', 'down') or char == 's': self.keys['down'] = False
        if kc in (65, 37) or sym in ('a', 'left') or char == 'a': self.keys['left'] = False
        if kc in (68, 39) or sym in ('d', 'right') or char == 'd': self.keys['right'] = False
        if kc in (74, 32) or sym in ('j', 'space') or char in ('j', ' '): self.keys['fire'] = False

    def on_bg_change(self, val):
        self.current_bg_type = val
        self.canvas.focus_set()

    def init_game(self):
        self.map_data = create_map_lyl()
        self.base_obj = BaseHQ()
        self.player = Tank(9 * TILE_SIZE, 24 * TILE_SIZE, DIR_UP, is_player=True)
        self.enemies.clear(); self.bullets.clear(); self.powerups.clear(); self.mud_zones.clear()
        self.score, self.current_wave, self.wave_enemies_left = 0, 1, [5, 5, 5]
        self.enemy_spawn_timer, self.airdrop_timer, self.dual_cannon_timer, self.airdrop_pickup_count = 0, 1050, 0, 0
        self.game_running, self.game_paused = True, False
        self.keys = {'up': False, 'down': False, 'left': False, 'right': False, 'fire': False}
        self.effects.add_floating_text(CANVAS_SIZE // 2, 70, "第 1 波：先锋包抄突击队 (5辆)", "#00b4d8")

    def restart_game(self):
        self.init_game()
        self.canvas.focus_set()

    def toggle_pause(self):
        if not self.game_running: return
        self.game_paused = not self.game_paused
        if self.game_paused:
            self.effects.add_floating_text(CANVAS_SIZE // 2, CANVAS_SIZE // 2, "战况暂停中 [按P继续]", "#ffd166")
        else:
            self.canvas.focus_set()

    def trigger_timed_airdrop(self):
        open_tiles = []
        for r in range(4, 20):
            for c in range(3, 23):
                if self.map_data[r][c] == TILE_EMPTY: open_tiles.append((c * TILE_SIZE, r * TILE_SIZE))
        if open_tiles:
            x, y = random.choice(open_tiles)
            p_types = ['shockwave', 'mud_zone', 'steel_base', 'dual_cannon', 'shield']
            self.powerups.append(PowerUp(x, y, random.choice(p_types)))
            self.effects.add_floating_text(x + 12, y - 10, "📦 战术空投已就位!", "#00b4d8")
            sound_fx.play('powerup')

    def spawn_wave_enemy(self):
        rem = self.wave_enemies_left[self.current_wave - 1]
        if rem <= 0 or len(self.enemies) >= 3: return

        spawn_pts = [(2 * TILE_SIZE, 1 * TILE_SIZE), (8 * TILE_SIZE, 1 * TILE_SIZE), (15 * TILE_SIZE, 1 * TILE_SIZE), (23 * TILE_SIZE, 1 * TILE_SIZE)]
        valid_pts = [pt for pt in spawn_pts if not any(e.alive and math.hypot(e.x - pt[0], e.y - pt[1]) < 38 for e in self.enemies)]
        if not valid_pts: return

        tx, ty = random.choice(valid_pts)
        e_type = ('scout' if random.random() < 0.6 else 'raider') if self.current_wave == 1 else (('scout' if random.random() < 0.4 else ('raider' if random.random() < 0.5 else 'siege')) if self.current_wave == 2 else ('siege' if random.random() < 0.5 else 'raider'))
        self.enemies.append(Tank(tx, ty, DIR_DOWN, is_player=False, t_type=e_type))
        self.wave_enemies_left[self.current_wave - 1] -= 1

    def handle_player_input(self):
        if not self.player or not self.player.alive: return
        all_tanks = [self.player] + self.enemies
        if self.keys['up']: self.player.move(DIR_UP, self.map_data, all_tanks)
        elif self.keys['right']: self.player.move(DIR_RIGHT, self.map_data, all_tanks)
        elif self.keys['down']: self.player.move(DIR_DOWN, self.map_data, all_tanks)
        elif self.keys['left']: self.player.move(DIR_LEFT, self.map_data, all_tanks)

        if self.keys['fire']: self.player.shoot(self.bullets, self.dual_cannon_timer > 0)

    def check_powerup_pickups(self):
        if not self.player or not self.player.alive: return
        p_box = (self.player.x, self.player.y, self.player.size, self.player.size)
        for p in self.powerups[:]:
            if (p_box[0] < p.x + p.size and p_box[0] + p_box[2] > p.x and p_box[1] < p.y + p.size and p_box[1] + p_box[3] > p.y):
                p.alive = False
                sound_fx.play('powerup')
                self.airdrop_pickup_count += 1
                if self.airdrop_pickup_count >= 3: self.achieve_mgr.unlock('kfc_craze', self.effects)

                if p.type == 'shockwave':
                    sound_fx.play('shockwave')
                    self.effects.trigger_shake(9)
                    self.effects.add_floating_text(CANVAS_SIZE // 2, CANVAS_SIZE // 2 - 30, "💥 全体敌军遭受震荡打击!", "#f59e0b")
                    for e in self.enemies:
                        if e.alive:
                            e.take_damage(2, self.effects)
                            if e.can_move_at(e.x, e.y - 18, self.map_data, []): e.y -= 18
                            self.effects.add_floating_text(e.x + 12, e.y - 12, "💥 目标受创 -2!", "#ef4444")
                elif p.type == 'mud_zone':
                    sound_fx.play('powerup')
                    self.effects.add_floating_text(CANVAS_SIZE // 2, CANVAS_SIZE // 2 - 30, "❄️ 敌军全员陷入冰霜泥沼!", "#38bdf8")
                    if len([e for e in self.enemies if e.alive]) >= 3: self.achieve_mgr.unlock('cyber_buddha', self.effects)
                    for e in self.enemies:
                        if e.alive: self.mud_zones.append(MudZone(e.x + 12, e.y + 12, 95, 360))
                elif p.type == 'steel_base':
                    self.base_obj.repair(self.map_data, self.effects)
                    self.achieve_mgr.unlock('steel_fortress', self.effects)
                elif p.type == 'dual_cannon':
                    self.dual_cannon_timer = 480
                    self.effects.add_floating_text(self.player.x, self.player.y - 15, "⚡ 穿甲双联弹装填!", "#ffd166")
                elif p.type == 'shield':
                    self.player.shield_timer = 360
                    self.effects.add_floating_text(self.player.x, self.player.y - 15, "🔰 动能护盾展开!", "#4ade80")

                self.score += 150
                self.powerups.remove(p)

    def resolve_tank_separation(self, tanks):
        for i in range(len(tanks)):
            for j in range(i + 1, len(tanks)):
                t1, t2 = tanks[i], tanks[j]
                if not t1.alive or not t2.alive: continue
                c1x, c1y, c2x, c2y = t1.x + t1.size / 2, t1.y + t1.size / 2, t2.x + t2.size / 2, t2.y + t2.size / 2
                dx, dy = c2x - c1x, c2y - c1y
                dist = math.hypot(dx, dy)
                if dist < t1.size:
                    overlap = (t1.size - (dist or 1)) / 2
                    nx = dx / dist if dist > 0.001 else 1
                    ny = dy / dist if dist > 0.001 else 0
                    p1x, p1y = t1.x - nx * overlap, t1.y - ny * overlap
                    p2x, p2y = t2.x + nx * overlap, t2.y + ny * overlap
                    if t1.can_move_at(p1x, p1y, self.map_data, []): t1.x, t1.y = p1x, p1y
                    if t2.can_move_at(p2x, p2y, self.map_data, []): t2.x, t2.y = p2x, p2y

    def update_logic(self):
        if not self.game_running or self.game_paused: return
        self.handle_player_input()

        if self.dual_cannon_timer > 0: self.dual_cannon_timer -= 1
        self.base_obj.update(self.map_data)

        self.airdrop_timer -= 1
        if self.airdrop_timer <= 0:
            self.trigger_timed_airdrop()
            self.airdrop_timer = 1050

        for mz in self.mud_zones[:]:
            mz.update()
            if not mz.alive: self.mud_zones.remove(mz)

        self.enemy_spawn_timer += 1
        if self.enemy_spawn_timer > 75:
            self.spawn_wave_enemy()
            self.enemy_spawn_timer = 0

        if self.wave_enemies_left[self.current_wave - 1] == 0 and len(self.enemies) == 0 and self.current_wave < 3:
            self.current_wave += 1
            w_names = ["第 2 波：敌军战术穿插连队 (5辆)", "第 3 波：重装攻城决战师 (5辆)"]
            self.effects.add_floating_text(CANVAS_SIZE // 2, 70, w_names[self.current_wave - 2], "#00b4d8")

        all_tanks = ([self.player] if self.player.alive else []) + self.enemies

        if self.player:
            self.player.shield_timer = max(0, self.player.shield_timer - 1)
            if self.player.shoot_cooldown > 0: self.player.shoot_cooldown -= 1

        for e in self.enemies:
            if e.shoot_cooldown > 0: e.shoot_cooldown -= 1
            e.update_ai(self.map_data, all_tanks, self.bullets, self.player, self.mud_zones, self.base_obj)

        self.resolve_tank_separation(all_tanks)

        for b in self.bullets[:]:
            b.update(self.map_data, all_tanks, self.base_obj, self.effects)
            if not b.active: self.bullets.remove(b)

        self.check_powerup_pickups()

        for e in self.enemies[:]:
            if not e.alive:
                self.score += 300 if e.type == 'siege' else (200 if e.type == 'raider' else 100)
                self.enemies.remove(e)
                self.achieve_mgr.unlock('first_blood', self.effects)

        for p in self.powerups[:]:
            p.life -= 1
            if p.life <= 0: self.powerups.remove(p)

        self.effects.update()

        # 玩家无限复活机制
        if self.player and not self.player.alive:
            self.player = Tank(9 * TILE_SIZE, 24 * TILE_SIZE, DIR_UP, is_player=True)
            self.player.shield_timer = 180
            self.effects.add_floating_text(self.player.x, self.player.y - 15, "✨ 坦克重组复活!", "#38bdf8")

        if self.base_obj.destroyed:
            self.game_running = False
            messagebox.showinfo("战役结束", f"💀 浪尖基地失守！最终得分: {self.score}")
        elif self.current_wave == 3 and self.wave_enemies_left[2] == 0 and len(self.enemies) == 0 and self.base_obj.hp > 0:
            self.game_running = False
            if self.base_obj.hp == self.base_obj.max_hp: self.achieve_mgr.unlock('full_gpa', self.effects)
            self.achieve_mgr.unlock('morning_rush', self.effects)
            messagebox.showinfo("防御大捷", f"🎖️ 成功击退三波装甲师，守卫基地！最终积分: {self.score}")

        self._update_status_ui()

    def _update_status_ui(self):
        total_rem = sum(self.wave_enemies_left) + len(self.enemies)
        self.lbl_wave.config(text=f"战术波次: {self.current_wave}/3")
        pct = int((self.base_obj.hp / self.base_obj.max_hp) * 100)
        self.lbl_base.config(text=f"基地装甲: {pct}% ({self.base_obj.hp}/{self.base_obj.max_hp})", fg="#ef4444" if self.base_obj.hp <= 2 else "#4ade80")
        self.lbl_enemies.config(text=f"敌军剩余: {total_rem}")
        self.lbl_airdrop.config(text=f"空投倒计时: {max(0, math.ceil(self.airdrop_timer / 60))}s")
        self.lbl_score.config(text=f"积分: {self.score}")

        buff_text = []
        if self.dual_cannon_timer > 0: buff_text.append(f"⚡穿甲 {math.ceil(self.dual_cannon_timer/60)}s")
        if self.base_obj.steel_wall_timer > 0: buff_text.append(f"🛡️铁壁 {math.ceil(self.base_obj.steel_wall_timer/60)}s")
        if self.player and self.player.shield_timer > 0: buff_text.append(f"🔰护盾 {math.ceil(self.player.shield_timer/60)}s")
        self.buff_label.config(text=" | ".join(buff_text) if buff_text else "[当前无生效BUFF]")

    def render(self):
        self.canvas.delete("all")
        ox, oy = 0, 0
        if self.effects.shake_time > 0:
            ox = random.uniform(-self.effects.shake_magnitude, self.effects.shake_magnitude)
            oy = random.uniform(-self.effects.shake_magnitude, self.effects.shake_magnitude)

        if self.current_bg_type == "poster1":
            self.canvas.create_rectangle(ox, oy, ox + CANVAS_SIZE, oy + CANVAS_SIZE, fill="#07192f", outline="")
            self.canvas.create_text(ox + 312, oy + 180, text="2026, 和我们一起同行", font=("Microsoft YaHei", 20, "bold"), fill="#13365c")
            self.canvas.create_text(ox + 312, oy + 220, text="欢迎来到浪尖儿社区 · LYL", font=("Microsoft YaHei", 12, "bold"), fill="#13365c")
        elif self.current_bg_type == "poster2":
            self.canvas.create_rectangle(ox, oy, ox + CANVAS_SIZE, oy + CANVAS_SIZE, fill="#2b1500", outline="")
            self.canvas.create_text(ox + 312, oy + 180, text="勇立浪尖 · 逐梦前行", font=("Microsoft YaHei", 22, "bold"), fill="#4d2a00")
            self.canvas.create_text(ox + 312, oy + 220, text="WavePeak Elite Community Battle", font=("Microsoft YaHei", 12, "bold"), fill="#4d2a00")
        else:
            self.canvas.create_rectangle(ox, oy, ox + CANVAS_SIZE, oy + CANVAS_SIZE, fill="#050b14", outline="")

        for i in range(GRID_SIZE + 1):
            pos = i * TILE_SIZE
            self.canvas.create_line(ox + pos, oy, ox + pos, oy + CANVAS_SIZE, fill="#0c1d33")
            self.canvas.create_line(ox, oy + pos, ox + CANVAS_SIZE, oy + pos, fill="#0c1d33")

        for mz in self.mud_zones:
            self.canvas.create_oval(ox + mz.x - mz.radius, oy + mz.y - mz.radius, ox + mz.x + mz.radius, oy + mz.y + mz.radius, fill="#0c2e4e", outline="#38bdf8", width=2)
            self.canvas.create_text(ox + mz.x, oy + mz.y, text="❄️ 冰霜泥沼区", font=("Microsoft YaHei", 9, "bold"), fill="#bae6fd")

        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                t = self.map_data[r][c]
                px, py = ox + c * TILE_SIZE, oy + r * TILE_SIZE
                if t == TILE_BRICK: self.canvas.create_rectangle(px+1, py+1, px+TILE_SIZE-1, py+TILE_SIZE-1, fill="#d35400", outline="#873600")
                elif t == TILE_STEEL: self.canvas.create_rectangle(px+1, py+1, px+TILE_SIZE-1, py+TILE_SIZE-1, fill="#95a5a6", outline="#ecf0f1")
                elif t == TILE_WATER: self.canvas.create_rectangle(px, py, px+TILE_SIZE, py+TILE_SIZE, fill="#2980b9", outline="")

        bx, by = ox + self.base_obj.x, oy + self.base_obj.y
        if self.base_obj.destroyed:
            self.canvas.create_rectangle(bx, by, bx+48, by+48, fill="#34495e", outline="")
            self.canvas.create_text(bx+24, by+24, text="💥", font=("Segoe UI Emoji", 20))
        else:
            base_bg = "#991b1b" if self.base_obj.hp <= 2 else "#0077b6"
            self.canvas.create_rectangle(bx+2, by+2, bx+46, by+46, fill=base_bg, outline="#38bdf8" if self.base_obj.steel_wall_timer > 0 else "#ffd166", width=2)
            self.canvas.create_text(bx+24, by+16, text="浪尖基地", font=("Microsoft YaHei", 9, "bold"), fill="#ffd166")
            self.canvas.create_text(bx+24, by+32, text="LYL", font=("Microsoft YaHei", 9, "bold"), fill="#ffffff")
            bw = 44 * (self.base_obj.hp / self.base_obj.max_hp)
            self.canvas.create_rectangle(bx+2, by-8, bx+46, by-4, fill="#000", outline="")
            self.canvas.create_rectangle(bx+2, by-8, bx+2+bw, by-4, fill="#4ade80" if self.base_obj.hp > 2 else "#ef4444", outline="")

        for p in self.powerups:
            self.canvas.create_oval(ox + p.x, oy + p.y, ox + p.x + p.size, oy + p.y + p.size, fill="#005f73", outline="#ffd166", width=2)
            self.canvas.create_text(ox + p.x + 12, oy + p.y + 12, text="📦", font=("Segoe UI Emoji", 10))

        all_render_tanks = ([self.player] if self.player.alive else []) + self.enemies
        for t in all_render_tanks:
            tx, ty = ox + t.x, oy + t.y
            cx, cy, half = tx + t.size / 2, ty + t.size / 2, t.size / 2
            body_color = "#00b4d8" if t.is_player else ("#f59e0b" if t.type == 'scout' else ("#7c3aed" if t.type == 'siege' else "#ef4444"))
            self.canvas.create_rectangle(tx, ty, tx+t.size, ty+t.size, fill=body_color, outline="#2d3436", width=1)
            self.canvas.create_oval(cx-5, cy-5, cx+5, cy+5, fill="#ffd166" if t.is_player else "#2f3640", outline="")

            vx, vy = DIR_VECTORS[t.dir]
            self.canvas.create_line(cx, cy, cx + vx * (half + 4), cy + vy * (half + 4), fill="#f39c12" if t.is_player else "#1e272e", width=4)

            if t.is_player:
                self.canvas.create_text(cx, cy, text="LYL", font=("Arial", 6, "bold"), fill="#fff")
                if t.shield_timer > 0:
                    self.canvas.create_oval(cx-half-4, cy-half-4, cx+half+4, cy+half+4, outline="#38bdf8", width=2)
            elif t.max_hp > 1:
                hw = (t.size - 4) * (t.hp / t.max_hp)
                self.canvas.create_rectangle(tx+2, ty-6, tx+t.size-2, ty-3, fill="#000", outline="")
                self.canvas.create_rectangle(tx+2, ty-6, tx+2+hw, ty-3, fill="#22c55e", outline="")

        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if self.map_data[r][c] == TILE_TREE:
                    px, py = ox + c * TILE_SIZE, oy + r * TILE_SIZE
                    self.canvas.create_oval(px+2, py+2, px+TILE_SIZE-2, py+TILE_SIZE-2, fill="#27ae60", outline="")

        for b in self.bullets:
            bx, by = ox + b.x, oy + b.y
            b_color = ("#38bdf8" if b.is_ap else "#ffd166") if b.is_player else "#ff4d4d"
            self.canvas.create_oval(bx - b.radius, by - b.radius, bx + b.radius, by + b.radius, fill=b_color, outline="")

        for pt in self.effects.particles:
            px, py = ox + pt['x'], oy + pt['y']
            self.canvas.create_oval(px - pt['radius'], py - pt['radius'], px + pt['radius'], py + pt['radius'], fill=pt['color'], outline="")

        for ft in self.effects.floating_texts:
            fx, fy = ox + ft['x'], oy + ft['y']
            self.canvas.create_text(fx+1, fy+1, text=ft['text'], font=("Microsoft YaHei", 10, "bold"), fill="#000")
            self.canvas.create_text(fx, fy, text=ft['text'], font=("Microsoft YaHei", 10, "bold"), fill=ft['color'])

    def game_loop(self):
        self.update_logic()
        self.render()
        self.root.after(16, self.game_loop)

    def open_achieve_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("🏆 大学生专属战术成就展馆")
        win.geometry("520x420")
        win.configure(bg="#0d1b2a")
        win.resizable(False, False)

        tk.Label(win, text="🏆 大学生战术成就展馆", font=("Microsoft YaHei", 14, "bold"), fg="#ffd166", bg="#0d1b2a").pack(pady=10)
        frame = tk.Frame(win, bg="#0d1b2a")
        frame.pack(fill="both", expand=True, padx=15, pady=5)

        for a in ACHIEVEMENTS:
            is_unlocked = self.achieve_mgr.unlocked.get(a["id"], False)
            c_bg = "#1b263b" if not is_unlocked else "#264653"
            card = tk.Frame(frame, bg=c_bg, bd=1, relief="ridge")
            card.pack(fill="x", pady=4, padx=5)

            tk.Label(card, text=a["icon"], font=("Segoe UI Emoji", 16), bg=c_bg).pack(side="left", padx=8)
            info = tk.Frame(card, bg=c_bg)
            info.pack(side="left", fill="both", expand=True, pady=4)

            status_str = "【已解锁 ✓】" if is_unlocked else "【未解锁】"
            tk.Label(info, text=f"{a['name']} {status_str}", font=("Microsoft YaHei", 10, "bold"), fg="#ffd166" if is_unlocked else "#94a3b8", bg=c_bg).pack(anchor="w")
            tk.Label(info, text=a["desc"], font=("Microsoft YaHei", 8), fg="#e0e1dd", bg=c_bg).pack(anchor="w")

        tk.Button(win, text="确定关闭", font=("Microsoft YaHei", 9, "bold"), bg="#00b4d8", fg="#fff", command=win.destroy).pack(pady=10)

if __name__ == "__main__":
    try:
        root = tk.Tk()
        game = TankBattleGame(root)
        root.mainloop()
    except Exception as e:
        import tkinter.messagebox as mb
        mb.showerror("启动异常", f"游戏运行时捕获到异常：\n{e}")