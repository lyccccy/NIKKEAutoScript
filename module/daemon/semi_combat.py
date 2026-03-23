import cv2
import numpy as np

from module.base.timer import Timer
from module.daemon.assets import (
    MAIN_STORY_MAP_CLOSE,
    MAIN_STORY_MARK_IN,
    MAIN_STORY_MARK_OUT,
    MAIN_STORY_NORMAL,
    MINIMAP_ENEMY_CIRCLE,
    MINIMAP_ENEMY_TRIANGLE,
    MINIMAP_MAP_POINTER,
    MINIMAP_ZOOM_ICON,
    TEMPLATE_ENEMY_TARGET,
)
from module.daemon.daemon_base import DaemonBase
from module.event.assets import FIELD_CHANGE
from module.logger import logger
from module.simulation_room.assets import AUTO_BURST, AUTO_SHOOT, END_FIGHTING, FIGHT, PAUSE
from module.tribe_tower.assets import NEXT_STAGE
from module.ui.assets import FIGHT_QUICKLY_ENABLE, SKIP
from module.ui.ui import UI

class NoEnemyFoundError(Exception):
    pass

class SemiCombat(UI, DaemonBase):
    _minimap_enemy_search_rect_ratio = (0.326, 0.253, 0.666, 0.859)

    def _select_story_target(self, candidates):
        """
        Pick one candidate per round to avoid repeatedly clicking the same marker
        when multiple story markers exist at the same time.
        """
        if not candidates:
            return None

        if not hasattr(self, '_story_target_round'):
            self._story_target_round = 0

        h, w = self.device.image.shape[:2]
        cx, cy = w // 2, h // 2

        ranked = sorted(candidates, key=lambda c: (abs(c['location'][0] - cx) + abs(c['location'][1] - cy)))
        target = ranked[self._story_target_round % len(ranked)]
        self._story_target_round += 1
        return target

    def _click_story_mark_targets(self):
        # Main-story marker out of viewport: click the marker directly.
        out_targets = MAIN_STORY_MARK_OUT.match_several(
            self.device.image,
            offset=30,
            threshold=0.85,
            static=False
        )
        target = self._select_story_target(out_targets)
        if target is not None:
            x, y = target['location']
            self.device.click_minitouch(x, y)
            logger.info(f'Click MAIN_STORY_MARK_OUT @ ({x}, {y})')
            return True

        # Main-story marker in viewport: click a little below marker (same as old click_offset=(0, 130)).
        if not self.appear(FIGHT_QUICKLY_ENABLE, threshold=20) and not self.appear(FIGHT, threshold=20):
            in_targets = MAIN_STORY_MARK_IN.match_several(
                self.device.image,
                offset=30,
                threshold=0.85,
                static=False
            )
            target = self._select_story_target(in_targets)
            if target is not None:
                x, y = target['location']
                y = min(y + 130, self.device.image.shape[0] - 1)
                self.device.click_minitouch(x, y)
                logger.info(f'Click MAIN_STORY_MARK_IN(offset) @ ({x}, {y})')
                return True

            # Keep old scale-matching behavior as last fallback for MAIN_STORY_MARK_IN.
            if self.appear_with_scale_then_click(
                MAIN_STORY_MARK_IN, click_offset=(0, 130), scale_range=(0.7, 1.2), interval=5
            ):
                return True

        return False

    def _find_minimap_enemy_target(self):
        target = self._find_minimap_enemy_target_by_template()
        if target is not None:
            return target
        return self._find_minimap_enemy_target_by_color()

    def _find_minimap_enemy_target_by_template(self):
        h, w = self.device.image.shape[:2]
        rx1, ry1, rx2, ry2 = self._minimap_enemy_search_rect_ratio
        x1, y1, x2, y2 = int(w * rx1), int(h * ry1), int(w * rx2), int(h * ry2)
        if x2 <= x1 or y2 <= y1:
            return None

        roi = self.device.image[y1:y2, x1:x2]
        if roi.size == 0:
            return None

        triangle_buttons = MINIMAP_ENEMY_TRIANGLE.match_multi(roi, similarity=0.75, threshold=6, name='MINIMAP_TRI')
        if triangle_buttons:
            candidates = [{'location': (b.location[0] + x1, b.location[1] + y1)} for b in triangle_buttons]
            selected = self._select_story_target(candidates)
            if selected is not None:
                x, y = selected['location']
                logger.info('Find minimap enemy by template: triangle')
                return x, y

        circle_buttons = MINIMAP_ENEMY_CIRCLE.match_multi(roi, similarity=0.75, threshold=6, name='MINIMAP_CIRCLE')
        if circle_buttons:
            candidates = [{'location': (b.location[0] + x1, b.location[1] + y1)} for b in circle_buttons]
            selected = self._select_story_target(candidates)
            if selected is not None:
                x, y = selected['location']
                logger.info('Find minimap enemy by template: circle')
                return x, y

        return None

    def _find_minimap_enemy_target_by_color(self):
        """
        Color fallback inspired by DoroHelper:
        search red targets in minimap area and prefer triangle-like targets.
        """
        h, w = self.device.image.shape[:2]
        rx1, ry1, rx2, ry2 = self._minimap_enemy_search_rect_ratio
        x1, y1, x2, y2 = int(w * rx1), int(h * ry1), int(w * rx2), int(h * ry2)
        if x2 <= x1 or y2 <= y1:
            return None

        roi = self.device.image[y1:y2, x1:x2]
        if roi.size == 0:
            return None

        # Compatible with either RGB/BGR ordering.
        ch0 = roi[:, :, 0].astype(np.int16)
        ch1 = roi[:, :, 1].astype(np.int16)
        ch2 = roi[:, :, 2].astype(np.int16)
        red_like = (
            ((ch0 > 160) & ((ch0 - ch1) > 35) & ((ch0 - ch2) > 35))
            | ((ch2 > 160) & ((ch2 - ch1) > 35) & ((ch2 - ch0) > 35))
        )
        mask = (red_like.astype(np.uint8)) * 255
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.dilate(mask, kernel, iterations=1)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        triangle_like = []
        circle_like = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 20:
                continue

            peri = cv2.arcLength(contour, True)
            if peri <= 1:
                continue
            approx = cv2.approxPolyDP(contour, 0.04 * peri, True)
            m = cv2.moments(contour)
            if m['m00'] == 0:
                continue
            cx = int(m['m10'] / m['m00']) + x1
            cy = int(m['m01'] / m['m00']) + y1

            circularity = 4.0 * np.pi * area / (peri * peri)
            if len(approx) <= 4 and circularity < 0.72:
                triangle_like.append((cx, cy, area))
            elif circularity >= 0.72:
                circle_like.append((cx, cy, area))

        # Priority: red triangle > red circle.
        picked = None
        if triangle_like:
            picked = max(triangle_like, key=lambda p: p[2])
        elif circle_like:
            picked = max(circle_like, key=lambda p: p[2])

        if picked is None:
            return None

        return picked[0], picked[1]

    def _click_minimap_enemy_target(self):
        target = self._find_minimap_enemy_target()
        if target is None:
            return False

        x, y = target
        self.device.click_minitouch(x, y)
        logger.info(f'Click minimap target @ ({x}, {y})')
        return True

    def run(self):
        #应该是先打开地图，开始找人，找到后点击位置，战斗。
        timeout = Timer(600, count=10)
        click_timer = Timer(0.3)
        k=0
        
        while 1:
            self.device.screenshot()
            while 1:
                if(self.appear_then_click(button=MINIMAP_ZOOM_ICON) #打开地图
                and click_timer.reached()):
                    click_timer.reset()
                    continue
                while 1:#找怪
                    enemies_locs=TEMPLATE_ENEMY_TARGET.match_multi(self.device.image, similarity=0.75, threshold=6, name='MINIMAP_TRI')
                    if(len(enemies_locs)==0):#没有敌人
                        logger.error(NoEnemyFoundError)
                    else:
                        enemies_locs = sorted(enemies_locs, key=lambda b: (b.location[1], b.location[0]))
                        target_index=k%len(enemies_locs)
                        k+=2
                        if(k>=len(enemies_locs)):
                            k=k-len(enemies_locs)
                        target_location=enemies_locs[target_index].location#TODO 这里可能需要缩放。
                        #TODO 关闭地图
                        break
                #移动后进入战斗
                if target_location:
                    self.device.click_minitouch(target_location[0], target_location[1])

                else:
                    continue











            # 快速战斗
            if (
                self.config.SemiCombat_FightQuickly
                and click_timer.reached()
                and self.appear_then_click(FIGHT_QUICKLY_ENABLE, threshold=20, interval=2)
            ):
                click_timer.reset()
                continue

            # 进入战斗
            if click_timer.reached() and self.appear_then_click(FIGHT, threshold=20, interval=2):
                click_timer.reset()
                continue

            # 主线剧情图标跟随：支持多目标轮选 + 颜色兜底
            if (
                self.config.SemiCombat_MainStoryMark
                and click_timer.reached()
                and self.appear(MAIN_STORY_NORMAL, offset=30)
            ):
                if self._click_story_mark_targets():
                    click_timer.reset()
                    continue
                if self._click_minimap_enemy_target():
                    click_timer.reset()
                    continue

            # 跳过剧情
            if (
                self.config.SemiCombat_SkipStory
                and click_timer.reached()
                and self.appear_then_click(SKIP, offset=(150, 10), interval=1)
            ):
                click_timer.reset()
                continue

            # 下一关卡
            if click_timer.reached() and self.appear_then_click(NEXT_STAGE, offset=(100, 30), interval=2):
                click_timer.reset()
                continue

            if click_timer.reached() and self.appear_then_click(END_FIGHTING, offset=30):
                click_timer.reset()
                continue

            # 前往区域
            if click_timer.reached() and self.appear_then_click(FIELD_CHANGE, offset=30, interval=1):
                click_timer.reset()
                continue

            # 自动射击
            if click_timer.reached() and self.appear_then_click(AUTO_SHOOT, offset=10, threshold=0.9, interval=5):
                click_timer.reset()
                continue
            if click_timer.reached() and self.appear_then_click(AUTO_BURST, offset=10, threshold=0.9, interval=5):
                click_timer.reset()
                continue

            # 红圈
            if self.config.Optimization_AutoRedCircle and self.appear(PAUSE, offset=10):
                if self.handle_red_circles():
                    click_timer.reset()
                    continue

            if not timeout.started():
                timeout.start()
            if timeout.reached():
                break
            else:
                timeout.clear()


if __name__ == '__main__':
    b = SemiCombat('nkas', task='SemiCombat')
    b.run()
