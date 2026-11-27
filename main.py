#!/usr/bin/env python3
"""Шахматы со способностями для Android (Pydroid 3) — один файл, графика и звук на pygame.

Как запустить в Pydroid 3:
  1. Меню -> Pip -> установить pygame (если ещё не установлен).
  2. Открыть этот файл и нажать жёлтую кнопку запуска.
Порядок: стартовое меню -> «Играть» -> выбор способностей -> «В бой».
Управление: тап по фигуре, затем тап по клетке. Кнопки под доской: способность,
новая игра, отмена хода, поворот доски, режим (ИИ / вдвоём), уровень ИИ (1-3),
сторона, звук, анимации, меню. Портретная и ландшафтная ориентации.
Звуки синтезируются кодом, внешние файлы не нужны.
"""
from array import array
import glob
import math
import os
import random
import sys
import threading
import time

import pygame

START = ["rnbqkbnr", "pppppppp", "........", "........",
         "........", "........", "PPPPPPPP", "RNBQKBNR"]
UNI = {'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
       'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'}
KNIGHT = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
KING = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
ROOK = [(-1, 0), (1, 0), (0, -1), (0, 1)]
BISHOP = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
VALUE = {'p': 100, 'n': 320, 'b': 330, 'r': 500, 'q': 900, 'k': 0}
CORNERS = {(7, 0): 'Q', (7, 7): 'K', (0, 0): 'q', (0, 7): 'k'}


def color(p):
    return 'w' if p.isupper() else 'b'


def inside(r, c):
    return 0 <= r < 8 and 0 <= c < 8


class Game:
    def __init__(self):
        self.board = [list(row) for row in START]
        self.turn = 'w'
        self.castle = set('KQkq')
        self.ep = None  # клетка, которую можно взять на проходе
        self.used = {}  # сторона -> число её ходов к моменту использования способности

    def clone(self):
        g = Game.__new__(Game)
        g.board = [row[:] for row in self.board]
        g.turn = self.turn
        g.castle = set(self.castle)
        g.ep = self.ep
        g.used = dict(self.used)
        return g

    # ---------- атаки и шахи ----------
    def attacked(self, r, c, by):
        b = self.board
        pawn_row = r + (1 if by == 'w' else -1)
        pawn = 'P' if by == 'w' else 'p'
        for dc in (-1, 1):
            if inside(pawn_row, c + dc) and b[pawn_row][c + dc] == pawn:
                return True
        for dr, dc in KNIGHT:
            rr, cc = r + dr, c + dc
            if inside(rr, cc) and b[rr][cc] != '.' and color(b[rr][cc]) == by and b[rr][cc].lower() == 'n':
                return True
        for dr, dc in KING:
            rr, cc = r + dr, c + dc
            if inside(rr, cc) and b[rr][cc] != '.' and color(b[rr][cc]) == by and b[rr][cc].lower() == 'k':
                return True
        for dirs, kinds in ((ROOK, 'rq'), (BISHOP, 'bq')):
            for dr, dc in dirs:
                rr, cc = r + dr, c + dc
                while inside(rr, cc):
                    p = b[rr][cc]
                    if p != '.':
                        if color(p) == by and p.lower() in kinds:
                            return True
                        break
                    rr += dr
                    cc += dc
        return False

    def king_pos(self, col):
        k = 'K' if col == 'w' else 'k'
        for r in range(8):
            for c in range(8):
                if self.board[r][c] == k:
                    return r, c

    def in_check(self):
        r, c = self.king_pos(self.turn)
        return self.attacked(r, c, 'b' if self.turn == 'w' else 'w')

    # ---------- генерация ходов ----------
    def pseudo(self):
        b, me = self.board, self.turn
        enemy = 'b' if me == 'w' else 'w'
        moves = []

        def add(r, c, rr, cc, promo_row=None):
            if rr == promo_row:
                for pr in 'qrbn':
                    moves.append((r, c, rr, cc, pr))
            else:
                moves.append((r, c, rr, cc, None))

        for r in range(8):
            for c in range(8):
                p = b[r][c]
                if p == '.' or color(p) != me:
                    continue
                t = p.lower()
                if t == 'p':
                    d = -1 if me == 'w' else 1
                    start = 6 if me == 'w' else 1
                    last = 0 if me == 'w' else 7
                    r1 = r + d
                    if inside(r1, c) and b[r1][c] == '.':
                        add(r, c, r1, c, last)
                        if r == start and b[r + 2 * d][c] == '.':
                            add(r, c, r + 2 * d, c)
                    for dc in (-1, 1):
                        c1 = c + dc
                        if inside(r1, c1):
                            tg = b[r1][c1]
                            if (tg != '.' and color(tg) == enemy) or (r1, c1) == self.ep:
                                add(r, c, r1, c1, last)
                elif t in 'nk':
                    for dr, dc in (KNIGHT if t == 'n' else KING):
                        rr, cc = r + dr, c + dc
                        if inside(rr, cc) and (b[rr][cc] == '.' or color(b[rr][cc]) == enemy):
                            add(r, c, rr, cc)
                else:
                    dirs = ROOK if t == 'r' else BISHOP if t == 'b' else ROOK + BISHOP
                    for dr, dc in dirs:
                        rr, cc = r + dr, c + dc
                        while inside(rr, cc):
                            if b[rr][cc] == '.':
                                add(r, c, rr, cc)
                            else:
                                if color(b[rr][cc]) == enemy:
                                    add(r, c, rr, cc)
                                break
                            rr += dr
                            cc += dc

        # рокировка
        row = 7 if me == 'w' else 0
        ks, qs, rook = ('K', 'Q', 'R') if me == 'w' else ('k', 'q', 'r')
        if b[row][4] == ('K' if me == 'w' else 'k') and not self.attacked(row, 4, enemy):
            if (ks in self.castle and b[row][7] == rook and b[row][5] == '.' and b[row][6] == '.'
                    and not self.attacked(row, 5, enemy)):
                moves.append((row, 4, row, 6, None))
            if (qs in self.castle and b[row][0] == rook and b[row][1] == '.' and b[row][2] == '.'
                    and b[row][3] == '.' and not self.attacked(row, 3, enemy)):
                moves.append((row, 4, row, 2, None))
        return moves

    def apply(self, m):
        g = self.clone()
        fr, fc, tr, tc, promo = m
        piece = g.board[fr][fc]
        captured = g.board[tr][tc]
        g.board[fr][fc] = '.'
        if piece.lower() == 'p' and (tr, tc) == self.ep and captured == '.':
            g.board[fr][tc] = '.'  # взятие на проходе
        placed = piece
        if promo:
            placed = promo.upper() if self.turn == 'w' else promo
        g.board[tr][tc] = placed
        if piece.lower() == 'k' and abs(tc - fc) == 2:  # двигаем ладью при рокировке
            if tc > fc:
                g.board[tr][5], g.board[tr][7] = g.board[tr][7], '.'
            else:
                g.board[tr][3], g.board[tr][0] = g.board[tr][0], '.'
        g.ep = ((fr + tr) // 2, fc) if piece.lower() == 'p' and abs(tr - fr) == 2 else None
        if piece.lower() == 'k':
            g.castle -= set('KQ' if self.turn == 'w' else 'kq')
        for sq in ((fr, fc), (tr, tc)):
            if sq in CORNERS:
                g.castle.discard(CORNERS[sq])
        g.turn = 'b' if self.turn == 'w' else 'w'
        return g

    def legal(self):
        enemy = 'b' if self.turn == 'w' else 'w'
        res = []
        for m in self.pseudo():
            g = self.apply(m)
            kr, kc = g.king_pos(self.turn)
            if not g.attacked(kr, kc, enemy):
                res.append(m)
        return res


# ---------- простой ИИ ----------
def evaluate(g):
    score = 0
    for r in range(8):
        for c in range(8):
            p = g.board[r][c]
            if p == '.':
                continue
            v = VALUE[p.lower()] + (10 - (abs(3.5 - r) + abs(3.5 - c)) * 2 if p.lower() in 'pnb' else 0)
            score += v if p.isupper() else -v
    return score if g.turn == 'w' else -score


_NODES = [0]


def negamax(g, depth, alpha, beta):
    _NODES[0] += 1
    if _NODES[0] % 120 == 0:
        time.sleep(0.0006)  # уступаем процессор интерфейсу, чтобы анимация не дёргалась
    moves = g.legal()
    if not moves:
        return -100000 - depth if g.in_check() else 0
    if depth == 0:
        return evaluate(g)
    moves.sort(key=lambda m: g.board[m[2]][m[3]] == '.')  # взятия сначала
    best = -10**9
    for m in moves:
        best = max(best, -negamax(g.apply(m), depth - 1, -beta, -alpha))
        alpha = max(alpha, best)
        if alpha >= beta:
            break
    return best


def best_move(g, depth):
    best, best_score = None, -10**9
    for m in g.legal():
        s = -negamax(g.apply(m), depth - 1, -10**9, 10**9)
        if s > best_score:
            best, best_score = m, s
    return best




# ======================================================================
#                              ЗВУКИ (синтез)
# ======================================================================
class Sfx:
    """Все звуки создаются кодом при запуске — внешние файлы не нужны."""

    def __init__(self):
        self.sounds, self.ok, self.on = {}, False, True
        self.rate, self.channels = 22050, 1
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 512)
            rate, fmt, ch = pygame.mixer.get_init()
            if fmt != -16:
                return
            self.rate, self.channels, self.ok = rate, ch, True
        except Exception:
            return
        threading.Thread(target=self.build, daemon=True).start()

    def tone(self, f, dur, vol=0.5, decay=20.0, f_end=None):
        n, ph, out = int(self.rate * dur), 0.0, []
        for i in range(n):
            fn = f if f_end is None else f + (f_end - f) * i / n
            ph += 6.283185307 * fn / self.rate
            out.append(math.sin(ph) * vol * math.exp(-decay * i / self.rate))
        return out

    def thud(self, dur, vol, decay, smooth):
        n, lp, out = int(self.rate * dur), 0.0, []
        for i in range(n):
            lp += smooth * (random.uniform(-1, 1) - lp)
            out.append(3 * lp * vol * math.exp(-decay * i / self.rate))
        return out

    def mix(self, *parts):
        size = max(int(o * self.rate) + len(s) for o, s in parts)
        out = [0.0] * size
        for o, s in parts:
            k = int(o * self.rate)
            for i, v in enumerate(s):
                out[k + i] += v
        return out

    def make(self, samples, peak):
        m = max(abs(v) for v in samples) or 1.0
        k = peak * 32767 / m
        fade = min(300, len(samples) // 4)
        data = array('h')
        for i, v in enumerate(samples):
            if i >= len(samples) - fade:
                v *= (len(samples) - i) / fade
            x = int(v * k)
            for _ in range(self.channels):
                data.append(x)
        return pygame.mixer.Sound(buffer=data.tobytes())

    def build(self):
        try:
            random.seed(7)
            t, th, mx, S = self.tone, self.thud, self.mix, self.sounds
            move = mx((0, th(.08, .9, 60, .3)), (0, t(170, .09, .5, 45)))
            S['move'] = self.make(move, .55)
            S['select'] = self.make(t(1300, .03, .6, 120), .22)
            S['click'] = self.make(t(800, .04, .6, 90), .30)
            S['undo'] = self.make(t(520, .12, .6, 25, 300), .35)
            S['capture'] = self.make(mx((0, th(.12, 1, 40, .55)), (0, t(130, .12, .6, 35)),
                                        (0, t(95, .14, .4, 30)), (.04, th(.07, .6, 60, .4))), .8)
            S['castle'] = self.make(mx((0, move), (.15, move)), .5)
            S['check'] = self.make(mx((0, t(880, .1, .6, 18)), (.1, t(1175, .16, .6, 14))), .45)
            S['promo'] = self.make(mx(*[(i * .07, t(f, .2, .6, 12))
                                        for i, f in enumerate((523, 659, 784, 1047))]), .45)
            S['start'] = self.make(mx((0, t(392, .2, .6, 10)), (.12, t(523, .3, .6, 8))), .45)
            S['draw'] = self.make(mx((0, t(392, .4, .6, 6)), (.25, t(294, .5, .6, 5))), .45)
            S['mate'] = self.make(mx(*[(i * .2, mx((0, t(f, .35, .6, 7)), (0, t(f / 2, .3, .4, 7))))
                                       for i, f in enumerate((440, 370, 311, 262))]), .55)
            S['sande_on'] = self.make(mx((0, t(120, .4, .6, 2.5, 950)), (0, t(55, .45, .5, 2))), .55)
            S['sande_off'] = self.make(t(700, .28, .6, 7, 140), .35)
            S['dash'] = self.make(mx((0, th(.22, .9, 9, .6)), (0, t(1300, .22, .4, 12, 250))), .5)
            S['destroy'] = self.make(mx((0, th(.4, 1, 8, .9)), (.04, t(240, .35, .5, 9, 35)),
                                        (.14, th(.25, .7, 14, .7)), (.3, th(.2, .5, 18, .8))), .75)
        except Exception:
            pass

    def play(self, name):
        if self.ok and self.on and name in self.sounds:
            try:
                self.sounds[name].play()
            except Exception:
                pass


# ======================================================================
#                    ГРАФИКА И СЕНСОРНЫЙ ИНТЕРФЕЙС (pygame)
# ======================================================================
C_LIGHT, C_DARK = (240, 217, 181), (181, 136, 99)
C_SEL, C_LAST, C_CHECK = (246, 246, 105), (205, 210, 106), (230, 70, 70)
C_DOT, C_BG = (20, 85, 30), (38, 36, 33)
C_BTN, C_BTN_HI = (84, 82, 78), (118, 116, 110)
C_TXT, C_DIM = (240, 240, 240), (170, 170, 170)
C_YELLOW, C_NEON, C_MARK, C_CARD = (252, 238, 10), (0, 229, 255), (255, 40, 120), (50, 48, 44)
SOLID = {'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'}
BUTTONS = ('power', 'new', 'undo', 'flip', 'mode', 'level', 'side', 'sound', 'anim', 'menu')


def on_android():
    return 'ANDROID_ROOT' in os.environ or hasattr(sys, 'getandroidapilevel')


def ease(t):
    """Плавный старт и плавная остановка."""
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def lerp_color(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def has_glyphs(path):
    try:
        m = pygame.font.Font(path, 40).metrics('♚♛♜♝♞♟')
        return bool(m) and all(x is not None for x in m)
    except Exception:
        return False


def pick_fonts():
    text = ['/system/fonts/Roboto-Regular.ttf', '/system/fonts/NotoSans-Regular.ttf',
            '/system/fonts/DroidSans.ttf']
    sym = glob.glob('/system/fonts/*Symbols*.ttf') + ['/system/fonts/DroidSansFallback.ttf']
    for n in ('dejavusans', 'arial', 'freesans', 'liberationsans'):
        p = pygame.font.match_font(n)
        if p:
            text.append(p)
    for n in ('dejavusans', 'segoeuisymbol', 'notosanssymbols2', 'applesymbols', 'freeserif'):
        p = pygame.font.match_font(n)
        if p:
            sym.append(p)
    t = next((p for p in text if os.path.exists(p)), None)
    s = next((p for p in sym if os.path.exists(p) and has_glyphs(p)), None)
    return t, s


FADE_TIME = 0.3
COOLDOWN = 7  # ходов перезарядки Сандевистана
DESC = ("Открывается после 5-го хода. Ферзь делает до 3 рывков подряд в любых направлениях "
        "и проходит сквозь любые фигуры. Когда рывок закончен, все пройденные вражеские "
        "фигуры уничтожаются (кроме короля). Перезарядка — 7 ходов.")


def wrap(font, text, maxw):
    lines, cur = [], ''
    for word in text.split():
        t = (cur + ' ' + word).strip()
        if font.size(t)[0] <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


class App:
    """Приложение. Плавность достигается так:
    * доска рисуется в отдельный слой и пересобирается только при изменениях;
    * во время хода слой-основа собирается один раз, а на кадр рисуются лишь летящие фигуры;
    * на экран отправляются только изменившиеся области (display.update);
    * масштабированные фигуры и тексты кэшируются;
    * ИИ в потоке регулярно «уступает» процессор, чтобы анимация не дёргалась.
    """

    def __init__(self):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("Шахматы")
        if on_android():
            pygame.display.set_mode((0, 0))  # весь экран телефона
        else:
            pygame.display.set_mode((480, 860), pygame.RESIZABLE)
        sys.setswitchinterval(0.001)
        self.text_path, self.sym_path = pick_fonts()
        self.fonts, self.texts = {}, {}
        self.pieces, self.scache, self.shadow_surf = {}, {}, None
        self.sq, self.size, self.screen = 0, None, None
        self.layer, self.bg, self.bg_key = None, None, None
        self.full, self.layer_dirty, self.panel_key = True, True, None
        self.clock = pygame.time.Clock()
        self.t, self.pressed, self.sel_t = self.now(), None, 0
        self.sfx = Sfx()
        self.vs_ai, self.depth, self.human, self.flipped = True, 2, 'w', False
        self.anim_on = True
        self.page, self.ability_on = 'menu', False
        self.fade_t0, self.was_fading, self.fade_surf, self.menu_key = self.now(), False, None, None
        self.dash = None
        self.gen = 0
        self.new_game(quiet=True)

    @staticmethod
    def now():
        return pygame.time.get_ticks() / 1000.0

    # ---------- состояние ----------
    def new_game(self, quiet=False):
        self.gen += 1
        self.history = [Game()]
        self.last, self.result, self.dash = None, None, None
        self.thinking, self.anim, self.sched, self.ai_t0 = False, None, [], 0
        self.flipped = self.vs_ai and self.human == 'b'
        self.refresh()
        if not quiet:
            self.sfx.play('start')

    def refresh(self):
        g = self.history[-1]
        self.legal = g.legal()
        self.checked = g.in_check()
        self.selected, self.targets, self.promo = None, [], []
        self.layer_dirty = True

    def go(self, page):
        self.page = page
        self.fade_t0 = self.now()
        self.menu_key = None
        self.full = True

    def moves_made(self, col):
        plies = len(self.history) - 1
        return (plies + 1) // 2 if col == 'w' else plies // 2

    def push(self, move):
        g = self.history[-1]
        ng = g.apply(move)
        fr, fc, tr, tc, promo = move
        piece = g.board[fr][fc]
        captured, movers = [], [(piece, (fr, fc), (tr, tc))]
        if g.board[tr][tc] != '.':
            captured.append((g.board[tr][tc], (tr, tc)))
        elif piece.lower() == 'p' and (tr, tc) == g.ep:
            captured.append((g.board[fr][tc], (fr, tc)))
        castle = piece.lower() == 'k' and abs(tc - fc) == 2
        if castle:
            r0, r1 = (7, 5) if tc > fc else (0, 3)
            movers.append((g.board[tr][r0], (tr, r0), (tr, r1)))
        sounds = ['castle' if castle else 'capture' if captured else 'move']
        if promo:
            sounds.append('promo')
        self.last = move
        self.history.append(ng)
        self.refresh()
        if not self.legal:
            sounds.append('mate' if self.checked else 'draw')
        elif self.checked:
            sounds.append('check')
        if self.anim_on:
            dist = max(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for _, a, b in movers)
            self.anim = {'t0': self.now(), 'dur': min(0.5, 0.22 + 0.05 * dist), 'movers': movers,
                         'captured': captured, 'hide': {m[2] for m in movers}, 'sounds': sounds}
        else:
            self.schedule(sounds)

    def schedule(self, names):
        t = self.now()
        for i, n in enumerate(names):
            self.sched.append((t + 0.16 * i, n))
        self.sched.sort()

    def undo(self):
        steps = 2 if self.vs_ai else 1
        if len(self.history) > steps:
            self.gen += 1
            self.thinking, self.anim, self.sched = False, None, []
            del self.history[-steps:]
            self.last = None
            self.refresh()
            self.sfx.play('undo')

    def human_turn(self):
        return not self.vs_ai or self.history[-1].turn == self.human

    # ---------- способность «Сандевистан» ----------
    def power_color(self):
        return self.human if self.vs_ai else self.history[-1].turn

    def power_info(self):
        """(надпись кнопки, стиль) для кнопки способности."""
        if not self.ability_on:
            return "Без способности", 'off'
        g, col, d = self.history[-1], self.power_color(), self.dash
        if d:
            return "Завершить рывок", ('active' if d['can_end'] else 'active_dim')
        queen = 'Q' if col == 'w' else 'q'
        if not any(queen in row for row in g.board):
            return "Сандевистан: нет ферзя", 'used'
        n = self.moves_made(col)
        if col in g.used:  # перезарядка: 7 собственных ходов после применения
            left = g.used[col] + COOLDOWN - n
            if left > 0:
                return f"Сандевистан: КД {left}", 'locked'
        elif n < 5:
            return f"Сандевистан: ход {n}/5", 'locked'
        if g.turn != col:
            return "Сандевистан", 'locked'
        return "Сандевистан", 'ready'

    def start_dash(self):
        g = self.history[-1]
        col = g.turn
        queen = 'Q' if col == 'w' else 'q'
        queens = [(r, c) for r in range(8) for c in range(8) if g.board[r][c] == queen]
        self.dash = {'color': col, 'wg': g.clone(), 'marked': set(), 'trail': [], 'left': 3, 'q': None,
                     'cands': {}, 'can_end': False, 'stuck': False, 'queens': queens}
        self.selected, self.targets, self.promo = None, [], []
        self.sfx.play('sande_on')
        if len(queens) == 1:
            self.dash_begin(queens[0])
        self.layer_dirty = True

    def dash_begin(self, q):
        d = self.dash
        d['q'], d['trail'], d['left'] = q, [q], 3
        d['cands'] = self.dash_cands()
        d['stuck'] = not d['cands']
        self.sel_t = self.now()
        self.layer_dirty = True

    def cancel_dash(self):
        if self.dash:
            self.dash, self.anim = None, None
            self.sfx.play('sande_off')
            self.layer_dirty = True

    def dash_cands(self):
        """Куда ферзь может рывком: сквозь любые фигуры, приземляясь только на пустые клетки."""
        d = self.dash
        wg, col = d['wg'], d['color']
        r, c = d['q']
        res = {}
        for dr, dc in KING:
            marks = []
            rr, cc = r + dr, c + dc
            while inside(rr, cc):
                p = wg.board[rr][cc]
                if p == '.':
                    res[(rr, cc)] = list(marks)
                elif p.lower() != 'k' and color(p) != col:  # вражеские фигуры — под уничтожение;
                    marks.append((rr, cc))                  # свои и короли пролетаются без отметки
                rr += dr
                cc += dc
        if d['left'] == 1:  # последний рывок обязан оставить своего короля вне шаха
            res = {k: v for k, v in res.items() if self.dash_final_ok(k, v)}
        return res

    def dash_result(self, wg, marked, col):
        """Итоговая позиция: пройденные вражеские фигуры (кроме короля) уничтожены."""
        F, destroyed = wg.clone(), []
        for (r, c) in marked:
            p = F.board[r][c]
            if p != '.' and p.lower() != 'k' and color(p) != col:
                destroyed.append((p, (r, c)))
                F.board[r][c] = '.'
        for sq, k in CORNERS.items():
            if F.board[sq[0]][sq[1]] != ('R' if k.isupper() else 'r'):
                F.castle.discard(k)
        F.ep = None
        F.turn = 'b' if col == 'w' else 'w'
        F.used = dict(F.used)
        F.used[col] = self.moves_made(col) + 1  # рывок считается ходом
        return F, destroyed

    def dash_final_ok(self, dest=None, marks=()):
        d = self.dash
        wg, q, col = d['wg'].clone(), d['q'], d['color']
        if dest:
            wg.board[dest[0]][dest[1]], wg.board[q[0]][q[1]] = wg.board[q[0]][q[1]], '.'
        F, _ = self.dash_result(wg, d['marked'] | set(marks), col)
        kr, kc = F.king_pos(col)
        return not F.attacked(kr, kc, 'b' if col == 'w' else 'w')

    def dash_step(self, dest):
        d = self.dash
        wg, fr = d['wg'], d['q']
        marks = d['cands'][dest]
        q = wg.board[fr[0]][fr[1]]
        wg.board[fr[0]][fr[1]], wg.board[dest[0]][dest[1]] = '.', q
        d['marked'].update(marks)
        d['q'], d['left'], d['cands'], d['can_end'] = dest, d['left'] - 1, {}, False
        d['trail'].append(dest)
        self.selected, self.targets = None, []
        self.sfx.play('dash')
        self.layer_dirty = True
        if self.anim_on:
            dist = ((fr[0] - dest[0]) ** 2 + (fr[1] - dest[1]) ** 2) ** 0.5
            self.anim = {'t0': self.now(), 'dur': min(0.4, 0.2 + 0.04 * dist), 'movers': [(q, fr, dest)],
                         'captured': [], 'hide': {dest}, 'sounds': [], 'ghosts': True, 'after': 'dash'}
        else:
            self.dash_after()

    def dash_after(self):
        d = self.dash
        if not d:
            return
        d['cands'] = self.dash_cands() if d['left'] > 0 else {}
        d['can_end'] = len(d['trail']) > 1 and self.dash_final_ok()
        self.sel_t = self.now()
        self.layer_dirty = True
        if d['left'] == 0 or not d['cands']:
            if d['can_end']:
                self.dash_finish()
            else:
                d['stuck'] = True

    def dash_finish(self):
        d = self.dash
        F, destroyed = self.dash_result(d['wg'], d['marked'], d['color'])
        fr, to = d['trail'][-2], d['trail'][-1]
        self.last = (fr[0], fr[1], to[0], to[1], None)
        self.dash = None
        self.history.append(F)
        self.refresh()
        sounds = ['destroy' if destroyed else 'sande_off']
        if not self.legal:
            sounds.append('mate' if self.checked else 'draw')
        elif self.checked:
            sounds.append('check')
        if self.anim_on and destroyed:
            self.anim = {'t0': self.now(), 'dur': 0.75, 'movers': [], 'captured': destroyed, 'hide': set(),
                         'sounds': sounds, 'style': 'shatter', 'fade0': 0.3}
        else:
            self.schedule(sounds)

    # ---------- компьютер в отдельном потоке ----------
    def poll_ai(self):
        if self.anim or self.page != 'game':
            return
        g, now = self.history[-1], self.t
        if self.legal and self.vs_ai and g.turn != self.human and not self.thinking:
            self.thinking, self.ai_t0 = True, now
            gen, depth = self.gen, self.depth

            def work():
                m = best_move(g, depth)
                if gen == self.gen:
                    self.result = (gen, m)
            threading.Thread(target=work, daemon=True).start()
        if self.result and now - self.ai_t0 >= 0.35:  # небольшая «пауза на раздумье»
            gen, m = self.result
            self.result, self.thinking = None, False
            if gen == self.gen:
                self.push(m)

    def update(self):
        now = self.now()
        a = self.anim
        if a and now - a['t0'] >= a['dur']:
            self.anim = None
            self.layer_dirty = True
            self.schedule(a['sounds'])
            if a.get('after') == 'dash':
                self.dash_after()
        while self.sched and self.sched[0][0] <= now:
            self.sfx.play(self.sched.pop(0)[1])

    # ---------- шрифты, тексты, фигуры ----------
    def font(self, size, symbols=False):
        key = (size, symbols)
        if key not in self.fonts:
            self.fonts[key] = pygame.font.Font(self.sym_path if symbols else self.text_path, size)
        return self.fonts[key]

    def text(self, s, size, color_):
        key = (s, size, color_)
        if key not in self.texts:
            self.texts[key] = self.font(size).render(s, True, color_)
        return self.texts[key]

    def piece_surface(self, p):
        if p in self.pieces:
            return self.pieces[p]
        sq = self.sq
        white = p.isupper()
        fill, edge = ((250, 250, 250), (30, 30, 30)) if white else ((35, 35, 35), (225, 225, 225))
        s = pygame.Surface((sq, sq), pygame.SRCALPHA)
        c = (sq // 2, sq // 2)
        if self.sym_path:
            f = self.font(int(sq * 0.82), True)
            ch, d = SOLID[p.lower()], max(1, sq // 40)
            for dx in (-d, 0, d):
                for dy in (-d, 0, d):
                    if dx or dy:
                        o = f.render(ch, True, edge)
                        s.blit(o, o.get_rect(center=(c[0] + dx, c[1] + dy)))
            t = f.render(ch, True, fill)
            s.blit(t, t.get_rect(center=c))
        else:  # запасной вариант без шрифта с шахматными знаками
            pygame.draw.circle(s, edge, c, sq // 2 - sq // 8)
            pygame.draw.circle(s, fill, c, sq // 2 - sq // 8 - 3)
            t = self.font(int(sq * 0.45)).render(p.upper(), True, edge)
            s.blit(t, t.get_rect(center=c))
        self.pieces[p] = s
        return s

    def scaled(self, p, k):
        """Фигура, увеличенная в k раз (кэшируется с шагом 1/40)."""
        step = int(round(k * 40))
        key = (p, step)
        if key not in self.scache:
            size = max(1, int(self.sq * step / 40))
            self.scache[key] = pygame.transform.smoothscale(self.piece_surface(p), (size, size))
        return self.scache[key]

    def faded(self, p, step):
        """Исчезающая фигура: step от 0 до 12 (кэшируется)."""
        key = (p, 'f', step)
        if key not in self.scache:
            s = self.scaled(p, 1 - 0.3 * step / 12).copy()
            s.set_alpha(int(255 * (1 - step / 12)))
            self.scache[key] = s
        return self.scache[key]

    def ghost(self, p, lvl):
        """Полупрозрачный «послеобраз» фигуры (lvl 0..2)."""
        key = (p, 'g', lvl)
        if key not in self.scache:
            s = self.piece_surface(p).copy()
            s.set_alpha((120, 75, 40)[lvl])
            self.scache[key] = s
        return self.scache[key]

    def shadow(self):
        if self.shadow_surf is None:
            w, h = int(self.sq * 0.76), int(self.sq * 0.26)
            self.shadow_surf = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.ellipse(self.shadow_surf, (0, 0, 0, 80), (0, 0, w, h))
        return self.shadow_surf

    # ---------- раскладка под экран (портрет и ландшафт) ----------
    def layout(self):
        self.screen = pygame.display.get_surface()
        size = self.screen.get_size()
        if size == self.size:
            return
        self.size = size
        w, h = size
        if h >= w:
            sq = max(1, w // 8)
            self.bx, self.by = (w - sq * 8) // 2, sq // 2
            panel = pygame.Rect(0, self.by + sq * 8, w, h - self.by - sq * 8)
            cols = 4
        else:
            sq = max(1, min(h // 8, int(w * 0.6) // 8))
            self.bx, self.by = 4, (h - sq * 8) // 2
            x = self.bx + sq * 8 + 12
            panel = pygame.Rect(x, 8, w - x - 8, h - 16)
            cols = 2
        if sq != self.sq:
            self.sq, self.pieces, self.scache, self.shadow_surf = sq, {}, {}, None
        self.layer = pygame.Surface((sq * 8, sq * 8)).convert()
        self.bg_key = None
        self.board_rect = pygame.Rect(self.bx, self.by, sq * 8, sq * 8)
        self.ui = max(14, int(sq * 0.28))
        grid = [n for n in BUTTONS if n != 'power']
        rows, gap = -(-len(grid) // cols) + 1, 8
        top = panel.y + int(self.ui * 2.6)
        bh = max(24, min(int(sq * 1.15), (panel.bottom - top - gap * (rows + 1)) // rows))
        bw = (panel.w - gap * (cols + 1)) // cols
        self.panel = panel
        self.buttons = [('power', pygame.Rect(panel.x + gap, top + gap, panel.w - 2 * gap, bh))]
        for i, name in enumerate(grid):
            r, c = divmod(i, cols)
            self.buttons.append((name, pygame.Rect(panel.x + gap + c * (bw + gap),
                                                   top + gap + (r + 1) * (bh + gap), bw, bh)))
        self.build_menus()
        self.fade_surf = pygame.Surface(size)
        self.fade_surf.fill((0, 0, 0))
        if self.anim:
            self.anim['ready'] = False
        self.full = True

    def build_menus(self):
        w, h = self.size
        base = min(w, h)
        bw, bh = int(min(w * 0.7, base * 0.85)), int(base * 0.16)
        play = pygame.Rect((w - bw) // 2, int(h * 0.6), bw, bh)
        m, p = int(base * 0.05), int(base * 0.035)
        ia, cw = int(base * 0.26), w - 2 * int(base * 0.05)
        body, name_s, label_s = max(12, int(base * 0.036)), max(16, int(base * 0.06)), max(12, int(base * 0.04))
        title_s = max(20, int(base * 0.085))
        lines = wrap(self.font(body), DESC, cw - ia - 3 * p)
        lh = self.font(body).get_height() + 2
        text_h = self.font(name_s).get_height() + self.font(label_s).get_height() + 8 + len(lines) * lh
        chip_h = int(base * 0.07)
        top = m + self.font(title_s).get_height() + int(base * 0.07)
        card = pygame.Rect(m, top, cw, max(ia, text_h + chip_h + p) + 2 * p)
        b2 = int(base * 0.14)
        y2 = h - m - b2
        back = pygame.Rect(m, y2, int(cw * 0.3), b2)
        go = pygame.Rect(m + int(cw * 0.3) + p, y2, cw - int(cw * 0.3) - p, b2)
        self.md = {'m': m, 'p': p, 'ia': ia, 'lines': lines, 'lh': lh, 'body': body, 'name_s': name_s,
                   'label_s': label_s, 'title_s': title_s, 'sub_s': max(12, int(base * 0.04)),
                   'chip_h': chip_h, 'base': base}
        self.mrects = {'menu': {'play': play}, 'abilities': {'card': card, 'back': back, 'go': go}}

    def label(self, name):
        return {'power': self.power_info()[0], 'new': "Новая", 'undo': "Отмена", 'flip': "Поворот",
                'mode': "Играю с ИИ" if self.vs_ai else "Вдвоём",
                'level': f"Уровень {self.depth}",
                'side': ("За белых" if self.human == 'w' else "За чёрных") if self.vs_ai else "—",
                'sound': "Звук: вкл" if self.sfx.on else "Звук: выкл",
                'anim': "Аним.: вкл" if self.anim_on else "Аним.: выкл", 'menu': "Меню"}[name]

    def press(self, name):
        self.pressed = (name, self.now())
        if name == 'sound':
            self.sfx.on = not self.sfx.on
            self.sfx.play('click')
            return
        if name == 'power':
            d = self.dash
            if self.anim or self.thinking:
                return
            if d:
                if d['can_end']:
                    self.dash_finish()
                return
            if self.power_info()[1] == 'ready' and self.legal and self.human_turn():
                self.start_dash()
            return
        self.sfx.play('click')
        if name == 'new':
            self.new_game()
        elif name == 'undo':
            if self.dash:
                self.cancel_dash()
            else:
                self.undo()
        elif name == 'flip':
            self.flipped = not self.flipped
            self.layer_dirty = True
        elif name == 'mode':
            self.vs_ai = not self.vs_ai
            self.new_game()
        elif name == 'level':
            self.depth = self.depth % 3 + 1
        elif name == 'side' and self.vs_ai:
            self.human = 'b' if self.human == 'w' else 'w'
            self.new_game()
        elif name == 'menu':
            self.go('menu')
        elif name == 'anim':
            self.anim_on = not self.anim_on
            if not self.anim_on:
                a, self.anim = self.anim, None
                if a:
                    self.schedule(a['sounds'])
                    if a.get('after') == 'dash':
                        self.dash_after()
                self.layer_dirty = True

    # ---------- координаты ----------
    def to_px(self, r, c):
        if self.flipped:
            r, c = 7 - r, 7 - c
        return self.bx + c * self.sq, self.by + r * self.sq

    def cell(self, r, c):
        x, y = self.to_px(r, c)
        return x - self.bx, y - self.by

    def to_sq(self, x, y):
        c, r = (x - self.bx) // self.sq, (y - self.by) // self.sq
        return (7 - r, 7 - c) if self.flipped else (r, c)

    def promo_rects(self):
        """Прямоугольники выбора фигуры в координатах слоя доски."""
        x0, y0 = self.sq * 2, self.sq * 7 // 2
        return [(pr, pygame.Rect(x0 + i * self.sq, y0, self.sq, self.sq)) for i, pr in enumerate('qrbn')]

    # ---------- нажатия ----------
    def click(self, pos):
        if self.page != 'game':
            for name, rect in self.mrects[self.page].items():
                if rect.collidepoint(pos):
                    self.menu_press(name)
                    return
            return
        for name, rect in self.buttons:
            if rect.collidepoint(pos):
                self.press(name)
                return
        if self.thinking or self.anim or not self.legal or not self.human_turn():
            return
        if self.dash:
            d = self.dash
            if self.board_rect.collidepoint(pos):
                rc = self.to_sq(*pos)
                if d['q'] is None:
                    if rc in d['queens']:
                        self.dash_begin(rc)
                elif rc in d['cands']:
                    self.dash_step(rc)
            return
        if self.promo:
            for pr, rect in self.promo_rects():
                if rect.move(self.bx, self.by).collidepoint(pos):
                    self.push(next(m for m in self.promo if m[4] == pr))
                    return
            self.promo = []
            self.layer_dirty = True
            return
        x, y = pos
        if not self.board_rect.collidepoint(pos):
            return
        r, c = self.to_sq(x, y)
        g = self.history[-1]
        hits = [m for m in self.targets if m[2:4] == (r, c)]
        if hits:
            if len(hits) > 1:
                self.promo = hits
                self.layer_dirty = True
            else:
                self.push(hits[0])
            return
        p = g.board[r][c]
        if p != '.' and p.isupper() == (g.turn == 'w'):
            self.selected = (r, c)
            self.targets = [m for m in self.legal if m[:2] == (r, c)]
            self.sel_t = self.now()
            self.sfx.play('select')
        else:
            self.selected, self.targets = None, []
        self.layer_dirty = True

    def menu_press(self, name):
        self.pressed = (name, self.now())
        self.sfx.play('click')
        if name == 'play':
            self.go('abilities')
        elif name == 'back':
            self.go('menu')
        elif name == 'card':
            self.ability_on = not self.ability_on
            self.sfx.play('sande_on' if self.ability_on else 'sande_off')
        elif name == 'go':
            self.new_game()
            self.go('game')

    # ---------- рисование доски ----------
    def ensure_bg(self):
        key = (self.sq, self.flipped)
        if self.bg_key == key:
            return
        sq = self.sq
        bg = pygame.Surface((sq * 8, sq * 8)).convert()
        ls = max(11, int(sq * 0.18))
        lh = self.font(ls).get_height()
        for r in range(8):
            for c in range(8):
                x, y = self.cell(r, c)
                pygame.draw.rect(bg, C_LIGHT if (r + c) % 2 == 0 else C_DARK, (x, y, sq, sq))
        for i in range(8):
            fx, fy = self.cell(7, i)
            rx, ry = self.cell(i, 0)
            bg.blit(self.text("abcdefgh"[i], ls, C_DARK if i % 2 == 0 else C_LIGHT),
                    (fx + sq - lh // 2 - 6, fy + sq - lh - 1))
            bg.blit(self.text(str(8 - i), ls, C_DARK if i % 2 else C_LIGHT), (rx + 3, ry + 1))
        self.bg, self.bg_key = bg, key

    def mark(self, rc, rgb, alpha):
        s = pygame.Surface((self.sq, self.sq), pygame.SRCALPHA)
        s.fill((rgb[0], rgb[1], rgb[2], alpha))
        self.layer.blit(s, self.cell(*rc))

    def render_layer(self, hide=()):
        """Собирает слой доски: клетки, подсветки, фигуры, точки ходов."""
        d = self.dash
        g = d['wg'] if d else self.history[-1]
        L, sq, now = self.layer, self.sq, self.t
        pulse = 0.5 + 0.5 * math.sin(now * 5)
        self.ensure_bg()
        L.blit(self.bg, (0, 0))
        if self.last:
            self.mark(self.last[:2], C_LAST, 150)
            self.mark(self.last[2:4], C_LAST, 150)
        if self.selected and not d:
            self.mark(self.selected, C_SEL, 175)
        if self.checked and not self.anim and not d:
            self.mark(g.king_pos(g.turn), C_CHECK, int(100 + 130 * pulse))
        if d:
            for sqr in d['marked']:  # вражеские фигуры, которые будут уничтожены
                self.mark(sqr, C_MARK, int(120 + 90 * pulse))
            if d['q']:
                self.mark(d['q'], C_NEON, 90)
            else:
                for sqr in d['queens']:
                    self.mark(sqr, C_NEON, int(90 + 90 * pulse))
        for r in range(8):
            for c in range(8):
                p = g.board[r][c]
                if p != '.' and (r, c) not in hide:
                    L.blit(self.piece_surface(p), self.cell(r, c))
        if d and d['q']:  # послеобразы прошлых позиций ферзя
            qp = g.board[d['q'][0]][d['q'][1]]
            for sqr in d['trail'][:-1]:
                if sqr != d['q'] and g.board[sqr[0]][sqr[1]] == '.':
                    L.blit(self.ghost(qp, 1), self.cell(*sqr))
        grow = min(1.0, (now - self.sel_t) / 0.15)  # точки ходов «вырастают»
        if grow > 0.05:
            if d:
                for (r, c), marks in d['cands'].items():
                    x, y = self.cell(r, c)
                    mid = (x + sq // 2, y + sq // 2)
                    pygame.draw.circle(L, C_NEON, mid, max(2, int(max(5, sq // 7) * grow)))
                    if marks:
                        pygame.draw.circle(L, C_MARK, mid, int(max(8, sq // 4) * grow), max(2, sq // 22))
            else:
                for m in self.targets:
                    x, y = self.cell(m[2], m[3])
                    mid = (x + sq // 2, y + sq // 2)
                    if g.board[m[2]][m[3]] == '.':
                        pygame.draw.circle(L, C_DOT, mid, max(2, int(max(5, sq // 8) * grow)))
                    else:
                        pygame.draw.circle(L, C_DOT, mid, int((sq // 2 - 3) * (0.6 + 0.4 * grow)), max(2, sq // 20))
        if self.promo:
            pygame.draw.rect(L, (40, 40, 40), (sq * 2 - 6, sq * 7 // 2 - 6, sq * 4 + 12, sq + 12), border_radius=8)
            for pr, rect in self.promo_rects():
                pygame.draw.rect(L, C_LIGHT, rect)
                L.blit(self.piece_surface(pr.upper() if g.turn == 'w' else pr), rect.topleft)

    def draw_anim(self, a, now):
        """Рисует только летящие и исчезающие фигуры поверх готового слоя."""
        scr, sq = self.screen, self.sq
        t = max(0.0, min(1.0, (now - a['t0']) / a['dur']))
        smooth = lambda x: x * x * x * (x * (6 * x - 15) + 10)  # очень мягкий разгон и торможение
        e = smooth(t)
        f0 = a.get('fade0', 0.55)
        fade = max(0.0, (t - f0) / (1 - f0))
        shatter = a.get('style') == 'shatter'
        for i, (p, (r, c)) in enumerate(a['captured']):
            x, y = self.to_px(r, c)
            if shatter:  # мерцание и дрожь при уничтожении
                if t < 0.5 and (int(t * 40) + i) % 2:
                    continue
                x += ((int(t * 60) * 7 + i * 13) % 5 - 2) * sq * 0.015 * (1 - t)
                y += ((int(t * 60) * 5 + i * 11) % 5 - 2) * sq * 0.015 * (1 - t)
            step = int(fade * 12)
            if step > 0:
                s = self.faded(p, step)
                scr.blit(s, (int(x + (sq - s.get_width()) // 2), int(y + (sq - s.get_height()) // 2)))
            else:
                scr.blit(self.piece_surface(p), (int(x), int(y)))
        lift = math.sin(math.pi * e)
        for p, (fr, fc), (tr, tc) in a['movers']:
            x0, y0 = self.to_px(fr, fc)
            x1, y1 = self.to_px(tr, tc)
            if a.get('ghosts'):  # шлейф из послеобразов при рывке
                for lvl, lag in enumerate((0.10, 0.20, 0.30)):
                    el = smooth(max(0.0, t - lag))
                    scr.blit(self.ghost(p, 2 - lvl), (int(x0 + (x1 - x0) * el), int(y0 + (y1 - y0) * el)))
            x, y = x0 + (x1 - x0) * e, y0 + (y1 - y0) * e
            sh = self.shadow()
            scr.blit(sh, (int(x + (sq - sh.get_width()) / 2), int(y + sq * 0.68)))
            s = self.scaled(p, 1 + 0.16 * lift)
            scr.blit(s, (int(x - (s.get_width() - sq) / 2), int(y - (s.get_height() - sq) / 2 - lift * sq * 0.07)))

    # ---------- панель игры ----------
    def panel_state(self):
        g, now, d = self.history[-1], self.t, self.dash
        if d:
            if d['q'] is None:
                msg = "Выбери ферзя для рывка"
            elif d['stuck']:
                msg = "Нет ходов — нажми «Отмена»"
            else:
                msg = f"Сандевистан · рывков: {d['left']}/3 · целей: {len(d['marked'])}"
        elif not self.legal:
            msg = ("Мат! Победили " + ("чёрные" if g.turn == 'w' else "белые")) if self.checked else "Пат — ничья"
        elif self.thinking:
            msg = "Компьютер думает" + "." * (int(now * 3) % 4)
        else:
            msg = ("Ход белых" if g.turn == 'w' else "Ход чёрных") + (" — ШАХ!" if self.checked else "")
        pressed = self.pressed[0] if self.pressed and now - self.pressed[1] < 0.12 else None
        return (msg, self.thinking and self.depth == 3, pressed,
                tuple(self.label(n) for n, _ in self.buttons), self.power_info()[1])

    def render_panel(self, key):
        scr, ui = self.screen, self.ui
        msg, hint, pressed, _, pstyle = key
        pygame.draw.rect(scr, C_BG, self.panel)
        scr.blit(self.text(msg, ui, C_NEON if self.dash else C_TXT), (self.panel.x + 12, self.panel.y + 6))
        if hint:
            scr.blit(self.text("Уровень 3 может думать долго", max(11, int(ui * 0.7)), C_DIM),
                     (self.panel.x + 12, self.panel.y + 6 + int(ui * 1.3)))
        bsize = max(12, int(ui * 0.9))
        styles = {'ready': (C_YELLOW, (20, 20, 20)), 'active': (C_NEON, (10, 10, 10)),
                  'active_dim': ((40, 90, 100), C_DIM)}
        for name, rect in self.buttons:
            bg, fg = C_BTN_HI if name == pressed else C_BTN, C_TXT
            if name == 'power':
                bg, fg = styles.get(pstyle, (C_BTN, C_DIM))
            elif name == 'side' and not self.vs_ai:
                fg = C_DIM
            pygame.draw.rect(scr, bg, rect, border_radius=10)
            t = self.text(self.label(name), bsize, fg)
            if t.get_width() > rect.w - 8:
                t = pygame.transform.smoothscale(t, (rect.w - 8, max(1, int(t.get_height() * (rect.w - 8) / t.get_width()))))
            scr.blit(t, t.get_rect(center=rect.center))

    def frame_game(self):
        scr, now, a = self.screen, self.t, self.anim
        rects = []
        if self.full:
            scr.fill(C_BG)
            self.panel_key = None
        active = bool(self.dash)
        pulsing = bool((self.checked or active) and not a)
        growing = bool((self.targets or active) and not a and now - self.sel_t < 0.2)
        if self.full or a or self.layer_dirty or pulsing or growing:
            if a:
                if not a.get('ready') or self.layer_dirty:
                    self.render_layer(a['hide'])
                    a['ready'] = True
            else:
                self.render_layer()
            self.layer_dirty = False
            scr.blit(self.layer, (self.bx, self.by))
            if a:
                self.draw_anim(a, now)
            rects.append(self.board_rect)
        key = self.panel_state()
        if key != self.panel_key:
            self.render_panel(key)
            self.panel_key = key
            rects.append(self.panel)
        return rects

    # ---------- меню ----------
    def menu_button(self, rect, label, size, primary=True, pressed=False):
        bg = C_YELLOW if primary else C_BTN
        if pressed:
            bg = lerp_color(bg, (255, 255, 255), 0.35)
        pygame.draw.rect(self.screen, bg, rect, border_radius=max(8, rect.h // 4))
        t = self.text(label, size, (20, 20, 20) if primary else C_TXT)
        self.screen.blit(t, t.get_rect(center=rect.center))

    def render_menu(self, key):
        scr, md = self.screen, self.md
        w, h = self.size
        base = md['base']
        pressed = key[2]
        scr.fill(C_BG)
        if self.page == 'menu':
            play = self.mrects['menu']['play']
            if self.sym_path:
                q = self.font(int(base * 0.34), True).render(SOLID['q'], True, C_YELLOW)
                scr.blit(q, q.get_rect(center=(w // 2, int(h * 0.27))))
            t = self.text("ШАХМАТЫ", max(24, int(base * 0.13)), C_TXT)
            scr.blit(t, t.get_rect(center=(w // 2, int(h * 0.46))))
            sub = self.text("со способностями", md['sub_s'], C_NEON)
            scr.blit(sub, sub.get_rect(center=(w // 2, int(h * 0.46) + t.get_height() // 2 + md['sub_s'])))
            self.menu_button(play, "Играть", max(18, int(base * 0.075)), True, pressed == 'play')
            return
        m, p, ia = md['m'], md['p'], md['ia']
        t = self.text("Способности", md['title_s'], C_TXT)
        scr.blit(t, t.get_rect(midtop=(w // 2, m)))
        sub = self.text("Нажми на карточку, чтобы взять способность", md['sub_s'], C_DIM)
        scr.blit(sub, sub.get_rect(midtop=(w // 2, m + t.get_height() + 2)))
        card = self.mrects['abilities']['card']
        on = key[1]
        pygame.draw.rect(scr, C_CARD, card, border_radius=16)
        pygame.draw.rect(scr, C_YELLOW if on else (95, 93, 88), card, 3, border_radius=16)
        ic = (card.x + p + ia // 2, card.centery)
        pygame.draw.circle(scr, (28, 27, 25), ic, ia // 2)
        pygame.draw.circle(scr, C_NEON, ic, ia // 2, 3)
        if self.sym_path:
            g_ = self.font(int(ia * 0.78), True).render(SOLID['q'], True, C_YELLOW)
            scr.blit(g_, g_.get_rect(center=ic))
        else:
            g_ = self.text("Q", int(ia * 0.6), C_YELLOW)
            scr.blit(g_, g_.get_rect(center=ic))
        tx, ty = card.x + p + ia + p, card.y + p
        n = self.text("Сандевистан", md['name_s'], C_YELLOW)
        scr.blit(n, (tx, ty))
        ty += n.get_height()
        lb = self.text("Фигура: Ферзь", md['label_s'], C_NEON)
        scr.blit(lb, (tx, ty))
        ty += lb.get_height() + 8
        for line in md['lines']:
            scr.blit(self.text(line, md['body'], C_TXT), (tx, ty))
            ty += md['lh']
        chip = pygame.Rect(tx, card.bottom - p - md['chip_h'], int(md['chip_h'] * 2.8), md['chip_h'])
        if on:
            pygame.draw.rect(scr, C_YELLOW, chip, border_radius=chip.h // 2)
            c_ = self.text("ВЗЯТО", md['label_s'], (20, 20, 20))
        else:
            pygame.draw.rect(scr, C_DIM, chip, 2, border_radius=chip.h // 2)
            c_ = self.text("ВЗЯТЬ", md['label_s'], C_DIM)
        scr.blit(c_, c_.get_rect(center=chip.center))
        b = self.mrects['abilities']
        self.menu_button(b['back'], "Назад", max(14, int(base * 0.05)), False, pressed == 'back')
        self.menu_button(b['go'], "В бой", max(16, int(base * 0.065)), True, pressed == 'go')

    def frame_menu(self):
        now = self.t
        pressed = self.pressed[0] if self.pressed and now - self.pressed[1] < 0.12 else None
        key = (self.page, self.ability_on, pressed)
        if self.full or key != self.menu_key:
            self.render_menu(key)
            self.menu_key = key
            self.full = True
        return []

    # ---------- кадр ----------
    def frame(self):
        fading = self.t - self.fade_t0 < FADE_TIME
        if fading or self.was_fading:
            self.full = True
        self.was_fading = fading
        rects = self.frame_menu() if self.page != 'game' else self.frame_game()
        if fading:
            p = (self.t - self.fade_t0) / FADE_TIME
            self.fade_surf.set_alpha(int(255 * (1 - p) ** 2))  # плавное появление экрана
            self.screen.blit(self.fade_surf, (0, 0))
        if self.full:
            pygame.display.flip()
            self.full = False
        elif rects:
            try:
                pygame.display.update(rects)
            except Exception:
                pygame.display.flip()

    def run(self):
        while True:
            self.t = self.now()
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.quit()
                    return
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    self.layout()
                    self.click(e.pos)
            self.layout()
            self.update()
            self.poll_ai()
            self.frame()
            busy = self.anim or self.dash or (self.checked and self.page == 'game') or self.t - self.fade_t0 < FADE_TIME
            self.clock.tick(60 if busy else 30)


if __name__ == '__main__':
    App().run()
