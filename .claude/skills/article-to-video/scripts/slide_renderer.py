#!/usr/bin/env python3
"""SlideRenderer — 区块高亮（Block Highlight）风格幻灯片渲染模块

所有项目的 generate_ppt.py 都应调用本模块，而非手写 Pillow 代码。

设计风格参考抖音创作者"慢学AI"：
- PPT 分成清晰的区块卡片，每个区块讲一个要点
- 语音讲到哪个区块，该区块微微发亮（subtle glow）
- 其他区块保持正常亮度，不做变暗处理
- 所有区块始终可见，不做渐进揭示
"""

from PIL import Image, ImageDraw, ImageFont
from dataclasses import dataclass
import os
import re


# ═══════════════════════════════════════════════════════
# 色板
# ═══════════════════════════════════════════════════════

@dataclass(frozen=True)
class ColorPalette:
    """色板定义 — 所有颜色在此集中管理"""
    # 背景 & 卡片
    BG:          tuple = (22, 26, 36)
    CARD:        tuple = (32, 38, 52)
    CARD_ACTIVE: tuple = (42, 48, 62)

    # 文字
    WHITE:      tuple = (255, 255, 255)
    OFF_WHITE:  tuple = (225, 225, 230)
    SOFT_WHITE: tuple = (180, 180, 195)
    DIM_TEXT:   tuple = (140, 140, 155)
    FAINT:      tuple = (65, 68, 78)

    # 强调色
    BLUE:   tuple = (60, 130, 255)
    GREEN:  tuple = (40, 215, 150)
    PURPLE: tuple = (150, 90, 255)
    AMBER:  tuple = (255, 185, 50)
    RED:    tuple = (255, 80, 80)
    TEAL:   tuple = (40, 210, 210)

    # 字幕背景
    SUB_BG: tuple = (0, 0, 0, 160)

    # 字幕金色
    SUBTITLE_GOLD: tuple = (255, 210, 60)


# ═══════════════════════════════════════════════════════
# SlideRenderer
# ═══════════════════════════════════════════════════════

class SlideRenderer:
    """区块高亮风格幻灯片渲染器

    高亮效果（关键设计）：
    ┌────────────┬─────────────────────┬─────────────────────┐
    │ 属性       │ 普通状态            │ 高亮状态（active）   │
    ├────────────┼─────────────────────┼─────────────────────┤
    │ 卡片填充   │ CARD (32,38,52)     │ CARD_ACTIVE+10      │
    │ 标题颜色   │ OFF_WHITE           │ WHITE               │
    │ 描述颜色   │ DIM_TEXT            │ SOFT_WHITE           │
    │ 边框       │ 无                  │ accent×40%, 2px     │
    │ 左侧色条   │ accent 100%         │ 不变                │
    └────────────┴─────────────────────┴─────────────────────┘

    绝对禁止：
    - 不用 focus_ring（双层高亮环太重）
    - 不变暗非活跃卡片
    - 不改变非活跃卡片大小/位置
    - 不做渐进揭示 — 所有区块始终可见
    """

    W = 1080
    H = 1920
    PAD = 80
    FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"
    colors = ColorPalette()

    def __init__(self, output_dir="slides/"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    # ── 内部工具 ──────────────────────────────────────

    def _font(self, size):
        return ImageFont.truetype(self.FONT_PATH, size)

    def _new_slide(self):
        img = Image.new("RGB", (self.W, self.H), self.colors.BG)
        return img, ImageDraw.Draw(img)

    def _wrap_text(self, draw, text, f, max_w):
        """逐字符换行（中文友好）"""
        lines, cur = [], ""
        for ch in text:
            t = cur + ch
            if draw.textbbox((0, 0), t, font=f)[2] > max_w:
                lines.append(cur)
                cur = ch
            else:
                cur = t
        if cur:
            lines.append(cur)
        return lines

    def _draw_subtitle(self, img, text):
        """底部字幕区：金色文字 + 微弱阴影，无黑底"""
        overlay = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        f = self._font(34)
        lines = self._wrap_text(od, text, f, self.W - 120)
        lh = 54
        total_h = len(lines) * lh + 44
        sy = self.H - total_h - 60
        ty = sy + 22
        shadow_color = (0, 0, 0, 180)
        gold = self.colors.SUBTITLE_GOLD + (255,)
        for line in lines:
            bbox = od.textbbox((0, 0), line, font=f)
            tw = bbox[2] - bbox[0]
            cx = (self.W - tw) // 2
            # 阴影（偏移 2,2）
            od.text((cx + 2, ty + 2), line, fill=shadow_color, font=f)
            # 金色文字
            od.text((cx, ty), line, fill=gold, font=f)
            ty += lh
        return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    def _save(self, img, seg_index, subtitle_text):
        """保存 PNG：叠加字幕后输出"""
        out = self._draw_subtitle(img, subtitle_text)
        fname = f"slide_{seg_index + 1:02d}.png"
        path = os.path.join(self.output_dir, fname)
        out.save(path, "PNG")
        print(f"  {fname}")
        return path

    def _card(self, draw, xy, fill=None, radius=16):
        if fill is None:
            fill = self.colors.CARD
        draw.rounded_rectangle(xy, radius=radius, fill=fill)

    def _left_bar(self, draw, x, y, h, color):
        """左侧色条（始终 100% accent_color）"""
        draw.rectangle([x, y, x + 8, y + h], fill=color)

    def _accent_line(self, draw, x, y, w, color, h=4):
        """标题下方装饰线"""
        draw.rectangle([x, y, x + w, y + h], fill=color)

    def _active_border(self, draw, xy, accent_color, radius=16):
        """高亮边框：accent_color × 40% 透明度, 2px"""
        r, g, b = accent_color[:3]
        bg_r, bg_g, bg_b = self.colors.CARD_ACTIVE
        mixed = (
            int(r * 0.4 + bg_r * 0.6),
            int(g * 0.4 + bg_g * 0.6),
            int(b * 0.4 + bg_b * 0.6),
        )
        draw.rounded_rectangle(xy, radius=radius, outline=mixed, width=2)

    def _render_rich_line(self, draw, x_start, y, line, font,
                          normal_color, highlight_color):
        """渲染带 **高亮** 标记的单行文字"""
        parts = re.split(r'\*\*', line)
        x = x_start
        for i, part in enumerate(parts):
            if not part:
                continue
            color = highlight_color if i % 2 == 1 else normal_color
            draw.text((x, y), part, fill=color, font=font)
            bbox = draw.textbbox((0, 0), part, font=font)
            x += bbox[2] - bbox[0]
        return x

    def _wrap_rich_text(self, draw, text, font, max_w):
        """对带 **标记** 的文字做逐字符换行，标记不占宽度"""
        plain = text.replace("**", "")
        lines = self._wrap_text(draw, plain, font, max_w)
        marked_lines = []
        pos = 0
        for line in lines:
            ml = ""
            count = 0
            while count < len(line) and pos < len(text):
                if text[pos:pos + 2] == "**":
                    ml += "**"
                    pos += 2
                else:
                    ml += text[pos]
                    pos += 1
                    count += 1
            marked_lines.append(ml)
        return marked_lines

    def _pill(self, draw, cx, cy, text, font, text_color, bg_color,
              pad_x=20, pad_y=10, radius=18):
        """渲染胶囊标签（圆角矩形 + 居中文字）"""
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x0 = cx - tw // 2 - pad_x
        y0 = cy - th // 2 - pad_y
        x1 = cx + tw // 2 + pad_x
        y1 = cy + th // 2 + pad_y
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=bg_color)
        draw.text((cx, cy), text, fill=text_color, font=font, anchor="mm")
        return x1 + 12

    # ── 公共 API ──────────────────────────────────────

    def render_cover(self, title, subtitle, source, seg_index, subtitle_text,
                     brand_line=None, tag_pills=None):
        """渲染封面页

        Args:
            title: 主标题（如"超越速率限制"）
            subtitle: 副标题（如"扩大 Codex 和 Sora 的访问规模"）
            source: 来源标注（如"OpenAI Engineering"）
            seg_index: 音频段编号（0-based）
            subtitle_text: 字幕文本
            brand_line: 顶部品牌文字（可选，如"● 慢学AI · 精读系列"）
            tag_pills: 底部标签列表（可选，如["🏛 OpenAI Codex", "</> 0行手写代码"]）
        Returns:
            str: 保存的 PNG 文件路径
        """
        img, dr = self._new_slide()

        # 品牌徽章（顶部居中圆角矩形背景）
        if brand_line:
            bf = self._font(28)
            bbox = dr.textbbox((0, 0), brand_line, font=bf)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            bx = self.W // 2
            by = 180
            pad_x, pad_y = 28, 14
            dr.rounded_rectangle(
                [bx - tw // 2 - pad_x, by - th // 2 - pad_y,
                 bx + tw // 2 + pad_x, by + th // 2 + pad_y],
                radius=22, fill=self.colors.CARD)
            dr.text((bx, by), brand_line,
                    fill=self.colors.OFF_WHITE, font=bf, anchor="mm")

        # 主标题
        dr.text((self.W // 2, self.H // 2 - 100), title,
                fill=self.colors.WHITE, font=self._font(72), anchor="mm")
        self._accent_line(dr, self.W // 2 - 60, self.H // 2 - 35,
                          120, self.colors.BLUE, 3)

        # 副标题
        if subtitle:
            dr.text((self.W // 2, self.H // 2 + 40), subtitle,
                    fill=self.colors.BLUE, font=self._font(34), anchor="mm")

        # 来源
        if source:
            dr.text((self.W // 2, self.H // 2 + 140), source,
                    fill=self.colors.DIM_TEXT, font=self._font(24), anchor="mm")

        # 底部标签胶囊
        if tag_pills:
            pill_font = self._font(24)
            pill_bg = self.colors.CARD
            pill_y = self.H // 2 + 280
            # 计算各胶囊宽度
            widths = []
            gap = 16
            for t in tag_pills:
                bbox = dr.textbbox((0, 0), t, font=pill_font)
                widths.append(bbox[2] - bbox[0] + 40)
            total_w = sum(widths) + gap * (len(widths) - 1)
            px = (self.W - total_w) // 2
            for i, t in enumerate(tag_pills):
                pw = widths[i]
                cx = px + pw // 2
                self._pill(dr, cx, pill_y, t, pill_font,
                           self.colors.OFF_WHITE, pill_bg, pad_x=20, pad_y=10)
                px += pw + gap

        return self._save(img, seg_index, subtitle_text)

    def render_block_slide(self, title, blocks, accent_color, focus_index,
                           seg_index, subtitle_text, section_label=None,
                           page_num=None):
        """渲染区块内容页（核心方法）

        Args:
            title: 页面标题（如"问题背景"）
            blocks: 区块列表，每个元素为 {"title": "...", "desc": "...", "icon": "..."}，最多 5 个
            accent_color: 强调色 tuple，如 self.colors.BLUE
            focus_index: 高亮第几个 block（0-based）
                         -1 = 无高亮（focus:none）
                         999 = 全部高亮（focus:all）
            seg_index: 音频段编号（0-based）
            subtitle_text: 字幕文本
            section_label: 英文分类标签（可选，如"CORE RESPONSIBILITIES"）
            page_num: 大号淡色页码（可选，int，如 2 → "02"）
        Returns:
            str: 保存的 PNG 文件路径
        """
        img, dr = self._new_slide()
        PAD = self.PAD

        # 英文分类标签（标题上方小号英文）
        title_y = 140
        if section_label:
            dr.text((PAD, 100), section_label.upper(),
                    fill=accent_color, font=self._font(22))
            title_y = 155

        # 大号淡色页码（右上角）
        if page_num is not None:
            dr.text((self.W - PAD - 20, 100), f"{page_num:02d}",
                    fill=self.colors.FAINT, font=self._font(80),
                    anchor="rt")

        # 页面标题
        dr.text((PAD, title_y), title,
                fill=self.colors.WHITE, font=self._font(52))
        self._accent_line(dr, PAD, title_y + 70, 120, accent_color)

        # 卡片布局计算
        n = len(blocks)
        card_gap = 20
        top_y = title_y + 140    # 可用区域顶部（跟随标题位置）
        bottom_y = 1560          # 可用区域底部（字幕区上方留 360px）
        available_h = bottom_y - top_y

        # 根据 block 数量设定最大卡片高度
        max_h_map = {1: 500, 2: 350, 3: 280, 4: 230, 5: 190}
        max_h = max_h_map.get(n, 190)

        if n == 2:
            # ── 双列并排布局 ──
            col_gap = 24
            card_w = (self.W - PAD * 2 - col_gap) // 2
            card_h = min(500, available_h)
            # 垂直居中
            start_y = top_y + (available_h - card_h) // 2
            x_positions = [PAD, PAD + card_w + col_gap]

            for i, block in enumerate(blocks):
                is_active = (focus_index == i) or (focus_index == 999)
                cx = x_positions[i]

                # ── 卡片填充 ──
                fill = self.colors.CARD_ACTIVE if is_active else self.colors.CARD
                box = [cx, start_y, cx + card_w, start_y + card_h]
                self._card(dr, box, fill=fill)

                # ── 左侧色条 ──
                self._left_bar(dr, cx, start_y, card_h, accent_color)

                # ── 高亮边框 ──
                if is_active:
                    self._active_border(dr, box, accent_color)

                # ── 图标 + 编号标题 ──
                icon = block.get("icon", "")
                num_str = f"{icon} {i + 1}. " if icon else f"{i + 1}. "
                title_font = self._font(34)
                num_bbox = dr.textbbox((0, 0), num_str, font=title_font)
                num_w = num_bbox[2] - num_bbox[0]
                tx = cx + 28
                ty = start_y + 18
                dr.text((tx, ty), num_str,
                        fill=accent_color, font=title_font)
                title_color = self.colors.WHITE if is_active else self.colors.OFF_WHITE
                dr.text((tx + num_w, ty), block["title"],
                        fill=title_color, font=title_font)

                # ── 圆点描述 ──
                desc = block.get("desc", "")
                if desc:
                    desc_color = (self.colors.SOFT_WHITE if is_active
                                  else self.colors.DIM_TEXT)
                    desc_font = self._font(26)
                    bullet = "● "
                    bullet_bbox = dr.textbbox((0, 0), bullet, font=desc_font)
                    bullet_w = bullet_bbox[2] - bullet_bbox[0]
                    lines = self._wrap_text(
                        dr, desc, desc_font, card_w - 56 - bullet_w)
                    dy = start_y + 65
                    for li, line in enumerate(lines):
                        if dy + 35 > start_y + card_h - 10:
                            break
                        if li == 0:
                            dr.text((tx, dy), bullet,
                                    fill=accent_color, font=desc_font)
                            dr.text((tx + bullet_w, dy), line,
                                    fill=desc_color, font=desc_font)
                        else:
                            dr.text((tx + bullet_w, dy), line,
                                    fill=desc_color, font=desc_font)
                        dy += 38
        else:
            # ── 垂直堆叠布局（1, 3, 4, 5 blocks）──
            card_h = min(max_h, (available_h - card_gap * (n - 1)) // n)
            total_cards_h = card_h * n + card_gap * (n - 1)
            start_y = top_y + (available_h - total_cards_h) // 2

            y = start_y
            for i, block in enumerate(blocks):
                is_active = (focus_index == i) or (focus_index == 999)

                # ── 卡片填充 ──
                fill = self.colors.CARD_ACTIVE if is_active else self.colors.CARD
                box = [PAD, y, self.W - PAD, y + card_h]
                self._card(dr, box, fill=fill)

                # ── 左侧色条 ──
                self._left_bar(dr, PAD, y, card_h, accent_color)

                # ── 高亮边框 ──
                if is_active:
                    self._active_border(dr, box, accent_color)

                # ── 图标 + 编号标题 ──
                icon = block.get("icon", "")
                num_str = f"{icon} {i + 1}. " if icon else f"{i + 1}. "
                title_font = self._font(34)
                num_bbox = dr.textbbox((0, 0), num_str, font=title_font)
                num_w = num_bbox[2] - num_bbox[0]
                tx = PAD + 28
                ty = y + 18
                dr.text((tx, ty), num_str,
                        fill=accent_color, font=title_font)
                title_color = self.colors.WHITE if is_active else self.colors.OFF_WHITE
                dr.text((tx + num_w, ty), block["title"],
                        fill=title_color, font=title_font)

                # ── 圆点描述 ──
                desc = block.get("desc", "")
                if desc:
                    desc_color = (self.colors.SOFT_WHITE if is_active
                                  else self.colors.DIM_TEXT)
                    desc_font = self._font(26)
                    bullet = "● "
                    bullet_bbox = dr.textbbox((0, 0), bullet, font=desc_font)
                    bullet_w = bullet_bbox[2] - bullet_bbox[0]
                    lines = self._wrap_text(
                        dr, desc, desc_font, self.W - PAD * 2 - 56 - bullet_w)
                    dy = y + 65
                    for li, line in enumerate(lines):
                        if dy + 35 > y + card_h - 10:
                            break
                        if li == 0:
                            dr.text((tx, dy), bullet,
                                    fill=accent_color, font=desc_font)
                            dr.text((tx + bullet_w, dy), line,
                                    fill=desc_color, font=desc_font)
                        else:
                            dr.text((tx + bullet_w, dy), line,
                                    fill=desc_color, font=desc_font)
                        dy += 38

                y += card_h + card_gap

        return self._save(img, seg_index, subtitle_text)

    def render_closing(self, title, quote, sub_text, seg_index, subtitle_text,
                       section_label=None):
        """渲染结尾页

        Args:
            title: 页面标题（如"核心启示"）
            quote: 核心引用/金句（支持 **关键词** 高亮标记）
            sub_text: 次级文本
            seg_index: 音频段编号（0-based）
            subtitle_text: 字幕文本
            section_label: 英文分类标签（可选，如"CORE TAKEAWAY"）
        Returns:
            str: 保存的 PNG 文件路径
        """
        img, dr = self._new_slide()
        PAD = self.PAD

        # 英文分类标签
        title_y = 140
        if section_label:
            dr.text((PAD, 100), section_label.upper(),
                    fill=self.colors.BLUE, font=self._font(22))
            title_y = 155

        # 标题
        dr.text((PAD, title_y), title,
                fill=self.colors.WHITE, font=self._font(52))
        self._accent_line(dr, PAD, title_y + 70, 80, self.colors.BLUE)

        # 居中大字金句（支持 **关键词** 高亮）
        if quote:
            box = [PAD, 400, self.W - PAD, 750]
            self._card(dr, box, fill=(28, 36, 52))
            self._active_border(dr, box, self.colors.BLUE)
            f = self._font(42)
            max_w = self.W - PAD * 2 - 80
            lh = 60
            if "**" in quote:
                marked_lines = self._wrap_rich_text(dr, quote, f, max_w)
                total_h = len(marked_lines) * lh
                qy = 400 + (350 - total_h) // 2
                for ml in marked_lines:
                    plain_line = ml.replace("**", "")
                    bbox = dr.textbbox((0, 0), plain_line, font=f)
                    tw = bbox[2] - bbox[0]
                    lx = (self.W - tw) // 2
                    self._render_rich_line(dr, lx, qy, ml, f,
                                           self.colors.WHITE,
                                           self.colors.BLUE)
                    qy += lh
            else:
                lines = self._wrap_text(dr, quote, f, max_w)
                total_h = len(lines) * lh
                qy = 400 + (350 - total_h) // 2
                for line in lines:
                    bbox = dr.textbbox((0, 0), line, font=f)
                    tw = bbox[2] - bbox[0]
                    dr.text(((self.W - tw) // 2, qy), line,
                            fill=self.colors.WHITE, font=f)
                    qy += lh

        # 次级文本
        if sub_text:
            dr.text((self.W // 2, 830), sub_text,
                    fill=self.colors.DIM_TEXT, font=self._font(28),
                    anchor="mm")

        # 分隔线
        dr.rectangle([PAD + 200, 900, self.W - PAD - 200, 902],
                     fill=self.colors.FAINT)

        # "谢谢观看"
        dr.text((self.W // 2, 980), "谢谢观看",
                fill=self.colors.WHITE, font=self._font(56), anchor="mm")

        return self._save(img, seg_index, subtitle_text)

    # ── 映射解析 ──────────────────────────────────────

    @staticmethod
    def parse_block_focus_mapping(narration_path):
        """解析 narration.txt 末尾的区块聚焦映射

        映射格式示例：
        # slide:2  | seg:02 | focus:block_1 | title:问题背景 | section:DIAGNOSIS | block_1:使用量远超预期 | icon_1:⚠️ | block_2:核心矛盾

        Returns:
            list[dict]: 每个 dict 包含:
                - slide: int（视觉编号）
                - seg: int（音频段编号，0-based）
                - focus: str（"block_1", "none", "all"）
                - title: str（页面标题）
                - blocks: list[str]（区块标题列表，有序）
                - section: str|None（英文分类标签）
                - icons: list[str|None]（区块图标列表，与 blocks 对齐）
        """
        results = []
        with open(narration_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("# slide:"):
                    continue

                parts = {}
                for part in line[2:].split("|"):
                    part = part.strip()
                    if ":" in part:
                        k, v = part.split(":", 1)
                        parts[k.strip()] = v.strip()

                # 按 block_1, block_2, ... 顺序收集区块标题和图标
                blocks = []
                icons = []
                bi = 1
                while f"block_{bi}" in parts:
                    blocks.append(parts[f"block_{bi}"])
                    icons.append(parts.get(f"icon_{bi}"))
                    bi += 1

                seg_str = parts.get("seg", "01")
                seg_num = int(seg_str)  # 文件中 1-based

                results.append({
                    "slide": int(parts.get("slide", "0")),
                    "seg": seg_num - 1,  # 转 0-based
                    "focus": parts.get("focus", "none"),
                    "title": parts.get("title", ""),
                    "blocks": blocks,
                    "section": parts.get("section"),
                    "icons": icons,
                })
        return results
