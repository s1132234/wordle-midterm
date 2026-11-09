import sys
import os
import pygame
import requests

# 桌面 client 在本機執行，透過這個網址呼叫雲端 FastAPI server。
API_BASE_URL = "https://wordle-midterm-0eco.onrender.com"
#API_BASE_URL = "http://127.0.0.1:8000"

# 顏色定義
COLOR_BG = (18, 18, 19)
COLOR_TEXT = (255, 255, 255)
COLOR_SUBTEXT = (170, 170, 170)
COLOR_EMPTY = (58, 58, 60)
COLOR_CORRECT = (83, 141, 78)   # 綠色
COLOR_PRESENT = (181, 159, 59)  # 黃色
COLOR_ABSENT = (58, 58, 60)     # 灰色
COLOR_DIVIDER = (90, 90, 90)
COLOR_HARD = (220, 80, 80)

MAX_ROWS = 6

pygame.init()
WIDTH, HEIGHT = 700, 650
GAME_AREA_WIDTH = 500
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pygame Wordle + FastAPI Client")
font = pygame.font.SysFont("Arial", 36, bold=True)
small_font = pygame.font.SysFont("Arial", 18)
side_title_font = pygame.font.SysFont("Arial", 20, bold=True)
history_font = pygame.font.SysFont("Arial", 22, bold=True)


def fit_font(text, max_width, start_size=16, min_size=10, bold=False):
    """ 自動縮小字體，讓文字塞得進指定寬度 """
    size = start_size
    f = pygame.font.SysFont("Arial", size, bold=bold)
    while f.size(text)[0] > max_width and size > min_size:
        size -= 1
        f = pygame.font.SysFont("Arial", size, bold=bold)
    return f


def safe_json(res):
    """ 安全解析 JSON，避免伺服器回傳非 JSON 時程式崩潰 """
    try:
        return res.json()
    except ValueError:
        return {}


class WordleGame:
    def __init__(self):
        self.game_id = None
        self.hard_mode = False
        self.history = []  # 本局已猜過的單字 [(word, [color x5]), ...]
        self.total_games = 0
        self.wins = 0
        self.win_rate = 0.0
        self.reset_board()
        self.message = "ENTER: submit | R: restart | H: hard mode"
        self.start_new_game()

    def reset_board(self):
        self.grid = [["" for _ in range(5)] for _ in range(MAX_ROWS)]
        self.colors = [[COLOR_EMPTY for _ in range(5)] for _ in range(MAX_ROWS)]
        self.row = 0
        self.col = 0
        self.game_over = False
        self.history = []

    def update_stats(self, stats):
        if not stats:
            return
        self.total_games = stats.get("total_games", self.total_games)
        self.wins = stats.get("wins", self.wins)
        self.win_rate = stats.get("win_rate", self.win_rate)

    def fetch_stats(self):
        try:
            res = requests.get(f"{API_BASE_URL}/api/stats", timeout=60)
            if res.status_code == 200:
                self.update_stats(safe_json(res))
        except requests.exceptions.RequestException:
            pass  # 統計抓不到不影響遊戲進行

    def start_new_game(self):
        """ 向 FastAPI 伺服器請求建立新的一局 """
        try:
            # Render 免費服務休眠後，第一次請求可能需要較久才會喚醒。
            payload = {"hard_mode": self.hard_mode}
            res = requests.post(f"{API_BASE_URL}/api/new-game", json=payload, timeout=60)
            data = safe_json(res)
            if res.status_code == 200 and "game_id" in data:
                self.game_id = data["game_id"]
                self.hard_mode = data.get("hard_mode", self.hard_mode)
                self.reset_board()
                self.update_stats(data.get("stats"))
                mode = "HARD" if self.hard_mode else "Normal"
                self.message = f"New game started! ({mode} mode)"
            else:
                self.game_id = None
                self.message = "Server error starting new game."
        except requests.exceptions.Timeout:
            self.game_id = None
            self.message = "Server timeout! Press R to retry."
        except requests.exceptions.RequestException:
            self.game_id = None
            self.message = "Cannot connect to FastAPI server!"

    def submit_guess(self):
        """ 將當前行單字發送至 FastAPI 驗證 """
        if self.game_id is None:
            self.message = "No game session. Press R to retry."
            return

        if self.col < 5:
            self.message = "Not enough letters!"
            return

        guess_word = "".join(self.grid[self.row])
        try:
            payload = {"game_id": self.game_id, "guess": guess_word}
            res = requests.post(f"{API_BASE_URL}/api/guess", json=payload, timeout=60)
            data = safe_json(res)

            if res.status_code == 200 and "feedback" in data:
                feedback = data["feedback"]

                # 依據後端回傳更新格子顏色
                for i in range(5):
                    if feedback[i] == "correct":
                        self.colors[self.row][i] = COLOR_CORRECT
                    elif feedback[i] == "present":
                        self.colors[self.row][i] = COLOR_PRESENT
                    else:
                        self.colors[self.row][i] = COLOR_ABSENT

                self.history.append((guess_word, list(self.colors[self.row])))
                self.update_stats(data.get("stats"))

                if data.get("is_correct"):
                    self.message = "Congratulations! You won! Press R to restart."
                    self.game_over = True
                else:
                    self.row += 1
                    self.col = 0
                    if self.row >= MAX_ROWS:
                        target = data.get("target_word") or "?????"
                        self.message = f"Game Over! The word was {target}. Press R to restart."
                        self.game_over = True
                    else:
                        tries_left = MAX_ROWS - self.row
                        self.message = f"Keep guessing! ({tries_left} tries left)"
            else:
                detail = data.get("detail", "Error processing guess")
                if not isinstance(detail, str):
                    detail = "Error processing guess"
                if "dictionary" in detail.lower():
                    self.message = "Not in word list!"
                else:
                    self.message = detail
        except requests.exceptions.Timeout:
            self.message = "Server timeout! Please try again."
        except requests.exceptions.RequestException:
            self.message = "Network error during guess!"

    def toggle_hard_mode(self):
        self.hard_mode = not self.hard_mode
        self.start_new_game()

    def handle_keydown(self, event):
        # 按住 Shift 時 R / H 當成一般字母輸入，方便猜含有 R、H 的單字
        shift = bool(event.mod & pygame.KMOD_SHIFT)

        if event.key == pygame.K_r and not shift:
            self.start_new_game()
            return

        if event.key == pygame.K_h and not shift:
            self.toggle_hard_mode()
            return

        if self.game_over:
            return

        if event.key == pygame.K_BACKSPACE:
            if self.col > 0:
                self.col -= 1
                self.grid[self.row][self.col] = ""
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.submit_guess()
        elif event.unicode and event.unicode.isascii() and event.unicode.isalpha() and len(event.unicode) == 1:
            if self.col < 5:
                self.grid[self.row][self.col] = event.unicode.upper()
                self.col += 1

    def draw_sidebar(self, surface):
        x0 = GAME_AREA_WIDTH
        side_w = WIDTH - GAME_AREA_WIDTH
        padding = 12

        # 分隔線
        pygame.draw.line(surface, COLOR_DIVIDER, (x0, 0), (x0, HEIGHT), 2)

        # 右上角模式提示
        mode_text = "Mode: HARD" if self.hard_mode else "Mode: Normal"
        mode_color = COLOR_HARD if self.hard_mode else COLOR_TEXT
        mode_surface = side_title_font.render(mode_text, True, mode_color)
        mode_rect = mode_surface.get_rect(topright=(WIDTH - padding, 12))
        surface.blit(mode_surface, mode_rect)

        # 勝率統計
        stats_text = f"Total: {self.total_games} | Wins: {self.wins} | Win Rate: {self.win_rate}%"
        stats_font = fit_font(stats_text, side_w - padding * 2)
        stats_surface = stats_font.render(stats_text, True, COLOR_SUBTEXT)
        surface.blit(stats_surface, (x0 + padding, 45))

        # 歷史紀錄標題
        pygame.draw.line(surface, COLOR_DIVIDER, (x0 + padding, 75), (WIDTH - padding, 75), 1)
        title_surface = side_title_font.render("History", True, COLOR_TEXT)
        surface.blit(title_surface, (x0 + padding, 85))

        # 依序垂直列出本局猜過的單字（含小色塊）
        mini = 26
        mini_gap = 4
        y = 120
        for idx, (word, colors) in enumerate(self.history):
            num_surface = small_font.render(f"{idx + 1}.", True, COLOR_SUBTEXT)
            surface.blit(num_surface, (x0 + padding, y + 3))
            for i, ch in enumerate(word):
                bx = x0 + padding + 25 + i * (mini + mini_gap)
                rect = pygame.Rect(bx, y, mini, mini)
                pygame.draw.rect(surface, colors[i], rect, border_radius=3)
                ch_surface = history_font.render(ch, True, COLOR_TEXT)
                surface.blit(ch_surface, ch_surface.get_rect(center=rect.center))
            y += mini + 10

        # 操作說明
        tips = ["R: restart   H: hard mode", "Shift+R / Shift+H: type R/H"]
        for i, tip in enumerate(tips):
            tip_font = fit_font(tip, side_w - padding * 2, start_size=14)
            tip_surface = tip_font.render(tip, True, COLOR_SUBTEXT)
            surface.blit(tip_surface, (x0 + padding, HEIGHT - 50 + i * 20))

    def draw(self, surface):
        surface.fill(COLOR_BG)
        # 繪製 6x5 網格
        margin_x, margin_y = 75, 50
        box_size = 60
        gap = 10

        for r in range(MAX_ROWS):
            for c in range(5):
                x = margin_x + c * (box_size + gap)
                y = margin_y + r * (box_size + gap)
                rect = pygame.Rect(x, y, box_size, box_size)

                # 畫背景框
                pygame.draw.rect(surface, self.colors[r][c], rect, border_radius=4)
                if self.colors[r][c] == COLOR_EMPTY:
                    pygame.draw.rect(surface, (80, 80, 80), rect, width=2, border_radius=4)

                # 畫字母
                char = self.grid[r][c]
                if char:
                    text_surface = font.render(char, True, COLOR_TEXT)
                    text_rect = text_surface.get_rect(center=rect.center)
                    surface.blit(text_surface, text_rect)

        # 畫底部提示訊息（置中於左側遊戲區）
        msg_font = fit_font(self.message, GAME_AREA_WIDTH - 20, start_size=18)
        msg_surface = msg_font.render(self.message, True, COLOR_TEXT)
        msg_rect = msg_surface.get_rect(center=(GAME_AREA_WIDTH // 2, HEIGHT - 40))
        surface.blit(msg_surface, msg_rect)

        self.draw_sidebar(surface)


def main():
    clock = pygame.time.Clock()
    game = WordleGame()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                game.handle_keydown(event)

        game.draw(screen)
        pygame.display.flip()
        clock.tick(30)


if __name__ == "__main__":
    main()