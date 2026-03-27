import sys
import os
import random
import math
from datetime import datetime
from PyQt5.QtWidgets import QWidget, QApplication, QLabel, QMenu, qApp  # 新增 QMenu, qApp
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QPixmap, QTransform, QCursor

# --- 【路径转换函数】 ---
# 这一步是为了让打包后的 .exe 自动找到内部的图片素材
def resource_path(relative_path):
    """ 获取文件的绝对路径，兼容 PyInstaller 打包后的路径 """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class YuanTouPet(QWidget):
    def __init__(self):
        super().__init__()
        # 1. 窗口基础设置
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True) 
        
        # --- 【新增：允许右键菜单】 ---
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)
        
        self.label = QLabel(self)
        self.is_dragging = False
        self.direction = 1  # 1向右，-1向左
        
        # --- 【动作素材定义 - 使用 resource_path】 ---
        self.img_stand = resource_path('shime1.png')
        self.img_walk = [resource_path('shime2.png'), resource_path('shime3.png')]
        self.img_fall = resource_path('shime4.png') 
        self.img_click = resource_path('shime34.png')
        self.img_sit_seq = [resource_path(f'shime{i}.png') for i in [11, 15, 16, 17]]
        self.img_swing_seq = [resource_path(f'shime{i}.png') for i in [31, 32, 33, 32]]
        self.img_climb_seq = [resource_path(f'shime{i}.png') for i in [12, 13, 14]]
        self.img_top_climb_seq = [resource_path(f'shime{i}.png') for i in [23, 24, 25]]
        self.img_crawl_seq = [resource_path(f'shime{i}.png') for i in [18, 20, 21]]
        self.img_drag_seq = [resource_path(f'shime{i}.png') for i in [5, 6, 7, 8, 9, 10]]
        self.img_alert_seq = [resource_path('shime34.png'), resource_path('shime35.png')] 
        self.img_sleep_seq = [resource_path(f'shime{i}.png') for i in [40, 41, 47]]

        self.update_image(self.img_stand)
        self._set_to_bottom()

        # --- 定时器设置 ---
        self.main_timer = QTimer(self); self.main_timer.timeout.connect(self.handle_state_machine); self.main_timer.start(350)
        self.physics_timer = QTimer(self); self.physics_timer.timeout.connect(self.handle_physics)
        self.animation_timer = QTimer(self); self.animation_timer.timeout.connect(self.play_loop_animations); self.animation_timer.start(550)
        
        # 状态变量
        self.state = 'stand' 
        self.walk_step = self.sit_step = self.swing_step = self.climb_step = 0
        self.top_climb_step = self.crawl_step = self.drag_step = self.action_timer = 0
        self.alert_step = self.sleep_step = 0 
        self.sit_timer = self.sleep_timer = 0  
        self.state_cooldown = 0 
        
        # 物理参数
        self.climb_plan = 'top'; self.top_climb_dist = 0; self.fall_lock = False  
        self.speed_x = self.speed_y = 0; self.gravity = 1.2; self.bounce_factor = -0.3; self.last_pos = QPoint(0, 0)
        self.detect_range = 150 
        
        self.show()

    # --- 【新增：右键退出功能】 ---
    def showContextMenu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: white; border: 1px solid gray; }")
        exit_action = menu.addAction("退出雁桌宠")
        action = menu.exec_(self.mapToGlobal(pos))
        if action == exit_action:
            qApp.quit()

    def _set_to_bottom(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() // 2, screen.height() - 150)

    def update_image(self, img_path):
        if os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            if self.direction == 1: pixmap = pixmap.transformed(QTransform().scale(-1, 1))
            self.label.setPixmap(pixmap)
            self.resize(pixmap.width(), pixmap.height())

    def play_loop_animations(self):
        if self.state == 'dragging':
            self.drag_step = (self.drag_step + 1) % len(self.img_drag_seq)
            self.update_image(self.img_drag_seq[self.drag_step])
        elif self.state == 'swing':
            self.swing_step = (self.swing_step + 1) % len(self.img_swing_seq)
            self.update_image(self.img_swing_seq[self.swing_step])
        elif self.state == 'top_climb':
            self.top_climb_step = (self.top_climb_step + 1) % len(self.img_top_climb_seq)
            self.update_image(self.img_top_climb_seq[self.top_climb_step])
        elif self.state == 'crawl':
            self.crawl_step = (self.crawl_step + 1) % len(self.img_crawl_seq)
            self.update_image(self.img_crawl_seq[self.crawl_step])
        elif self.state == 'alert_walk':
            self.alert_step = (self.alert_step + 1) % len(self.img_alert_seq)
            self.update_image(self.img_alert_seq[self.alert_step])

    def handle_state_machine(self):
        self.check_mouse_proximity()
        if self.state in ['dragging', 'fall', 'stop']: return
        screen_geo = QApplication.primaryScreen().geometry()

        if self.state == 'climb':
            if self.climb_step < len(self.img_climb_seq):
                self.update_image(self.img_climb_seq[self.climb_step]); self.climb_step += 1
                return
            self.move(self.x(), self.y() - 12); self.climb_step = 1
            if self.climb_plan == 'fall' and random.random() < 0.08: self._trigger_fall()
            elif self.y() <= 0:
                self.move(self.x(), 0); self.state = 'top_climb'; self.top_climb_step = 0; self.direction *= -1 
            return
        elif self.state == 'top_climb':
            self.top_climb_dist += 1; self.move(self.x() + (self.direction * 6), 0)
            if self.top_climb_dist > 30 or random.random() < 0.03: self._trigger_fall()
            return

        if self.state == 'stand':
            self.update_image(self.img_stand)
            self.state_cooldown = max(0, self.state_cooldown - 1)
            now_hour = datetime.now().hour
            is_late_night = now_hour >= 23 or now_hour < 5
            r = random.random()
            if self.state_cooldown <= 0:
                if is_late_night and r < 0.3: 
                    self.state = 'sleep'; self.sleep_step = 0; self.sleep_timer = 0
                elif r < 0.15: self.state = 'sit'; self.sit_step = 0; self.sit_timer = 0
                elif r < 0.30: self.state = 'swing'; self.swing_step = 0; self.action_timer = 0
                elif r < 0.45: self.state = 'crawl'; self.crawl_step = 0
                elif r < 0.60: self.state = 'walk'; self.direction = random.choice([1, -1])
            else:
                if r < 0.20: self.state = 'walk'; self.direction = random.choice([1, -1])

        elif self.state == 'walk':
            self.walk_step = (self.walk_step + 1) % len(self.img_walk); self.update_image(self.img_walk[self.walk_step])
            new_x = self.x() + (self.direction * 10)
            if new_x <= 0 or new_x >= screen_geo.width() - self.width(): 
                self._start_climb_process(new_x <= 0)
            else: self.move(new_x, self.y())
            if random.random() < 0.15: self.state = 'stand'

        elif self.state == 'alert_walk':
            new_x = self.x() + (self.direction * 14)
            if new_x <= 0 or new_x >= screen_geo.width() - self.width():
                self._start_climb_process(new_x <= 0)
            else:
                self.move(new_x, self.y())
            if random.random() < 0.1: self.state = 'stand'; self.state_cooldown = 10

        elif self.state == 'sleep':
            if self.sleep_step < len(self.img_sleep_seq) - 1:
                self.update_image(self.img_sleep_seq[self.sleep_step])
                self.sleep_step += 1
            else:
                self.update_image(self.img_sleep_seq[-1])
                self.sleep_timer += 1
                if self.sleep_timer > 50 and random.random() < 0.05:
                    self.state = 'stand'; self.state_cooldown = 20

        elif self.state == 'sit':
            if self.sit_step < len(self.img_sit_seq):
                self.update_image(self.img_sit_seq[self.sit_step]); self.sit_step += 1
            else:
                self.sit_timer += 1
                if self.sit_timer > 10 and random.random() < 0.2:
                    self.state = 'stand'; self.state_cooldown = 5 

        elif self.state == 'swing':
            self.action_timer += 1
            if self.action_timer > 12: self.state = 'stand'; self.state_cooldown = 5

        elif self.state == 'crawl':
            self.move(self.x() + (self.direction * 4), self.y())
            if self.x() <= 0 or self.x() >= screen_geo.width() - self.width(): 
                self._start_climb_process(self.x() <= 0)
            elif random.random() < 0.1: self.state = 'stand'; self.state_cooldown = 5

    def check_mouse_proximity(self):
        if self.state in ['dragging', 'fall', 'climb', 'top_climb', 'stop']:
            return
        cursor_pos = QCursor.pos() 
        pet_center = self.geometry().center()
        distance = math.hypot(cursor_pos.x() - pet_center.x(), cursor_pos.y() - pet_center.y())
        if distance < self.detect_range:
            if self.state != 'alert_walk':
                self.direction = 1 if cursor_pos.x() < pet_center.x() else -1
                self.state = 'alert_walk'
                self.alert_step = 0
        else:
            if self.state == 'alert_walk' and random.random() < 0.2:
                self.state = 'stand'

    def handle_physics(self):
        if self.state != 'fall': return
        self.speed_y += self.gravity
        new_x, new_y = self.x() + int(self.speed_x), self.y() + int(self.speed_y)
        screen = QApplication.primaryScreen().geometry()
        if not self.fall_lock:
            if new_x <= 0 or new_x >= screen.width() - self.width():
                self._start_climb_process(new_x <= 0); self.physics_timer.stop(); return
        ground_y = screen.height() - self.height() - 30
        if new_y >= ground_y:
            new_y = ground_y
            if abs(self.speed_y) > 5:
                self.speed_y *= self.bounce_factor; self.speed_x *= 0.6
            else:
                self.speed_x = self.speed_y = 0; self.state = 'stand'; self.update_image(self.img_stand); self.physics_timer.stop()
        self.move(new_x, new_y)

    def _start_climb_process(self, on_left):
        screen = QApplication.primaryScreen().geometry()
        self.move(0 if on_left else screen.width()-self.width(), self.y())
        self.direction = -1 if on_left else 1
        self.state = 'climb'; self.climb_step = 0; self.climb_plan = random.choice(['top', 'fall']); self.physics_timer.stop()

    def _trigger_fall(self):
        self.state = 'fall'; self.fall_lock = True; self.update_image(self.img_fall)
        self.speed_y = 5; self.speed_x = 0; self.physics_timer.start(30)
        QTimer.singleShot(1000, lambda: setattr(self, 'fall_lock', False))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True; self.state = 'dragging'
            self.old_pos = self.last_pos = event.globalPos(); self.physics_timer.stop()

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            delta = QPoint(event.globalPos() - self.old_pos)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.speed_x = (event.globalPos().x() - self.last_pos.x()) * 0.9
            self.direction = 1 if delta.x() > 0 else -1 if delta.x() < 0 else self.direction
            self.old_pos = self.last_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False; self.state = 'fall'; self.update_image(self.img_fall)
            self.speed_y = -22; self.physics_timer.start(30)

    def mouseDoubleClickEvent(self, event):
        self.state = 'stop'; self.update_image(self.img_click)
        QTimer.singleShot(1500, lambda: setattr(self, 'state', 'stand'))

if __name__ == '__main__':
    app = QApplication(sys.argv); app.setAttribute(Qt.AA_UseHighDpiPixmaps)
    pet = YuanTouPet(); sys.exit(app.exec_())
