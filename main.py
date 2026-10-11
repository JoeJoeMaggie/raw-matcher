#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAW原图查找复制工具

根据 JPG 文件夹中的文件名，在 RAW 文件夹中查找同名 RAW 原图，
并复制到 JPG 文件夹下的 "raw原图" 子文件夹中。

跨平台（macOS / Windows / Linux），纯标准库，无第三方运行依赖。

界面说明：
  * macOS 上使用系统原生标题栏（真的红黄绿三键），窗口仍可自由缩放；
  * Windows / Linux 上用 overrideredirect 去掉系统标题栏，自绘一套 macOS 风格
    红黄绿按钮 + 拖动移动 + 右下角缩放，视觉上与 Mac 保持一致；
  * 启动时开启高 DPI 感知并按屏幕缩放所有像素尺寸，避免系统拉伸导致的模糊。
"""

from __future__ import annotations

import queue
import shutil
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox

try:  # 拖拽为可选依赖：没装 tkinterdnd2 时程序照常运行，只是不能用拖拽
    from tkinterdnd2 import DND_FILES, TkinterDnD

    DND_AVAILABLE = True
except Exception:  # ImportError / OSError（tkdnd 二进制缺失）
    DND_AVAILABLE = False

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

# ---------------------------------------------------------------- 常量配置

APP_TITLE = "RAW文件查找复制工具"
HEADING = "RAW原图查找复制工具"
SUBTITLE = "按 JPG 文件名，在 RAW 文件夹中查找同名原图并复制到「raw原图」文件夹"

JPG_EXTS = {".jpg", ".jpeg"}
RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".raf", ".dng", ".rw2", ".orf", ".pef", ".srw"}
OUT_DIR_NAME = "raw原图"  # 输出子文件夹名

JPG_PLACEHOLDER = "请选择包含 JPG 图片的文件夹（将在其中创建 raw原图 文件夹）"
RAW_PLACEHOLDER = "请选择包含 RAW 原图的文件夹"
DROP_HINT = "支持从 Finder 拖拽文件夹到此框"

# 配色
BG = "#f4f5f7"          # 窗口底色
CARD = "#ffffff"        # 卡片/输入框底色
BORDER = "#e2e5ea"      # 边框
TEXT = "#1f2329"        # 主文字
MUTED = "#98a0ab"       # 次要文字 / 占位符
GREEN = "#2fa84f"
GREEN_HOVER = "#289245"
GREEN_OFF = "#b6dcc2"
NEUTRAL = "#eef0f3"
NEUTRAL_HOVER = "#e3e7ec"
LOG_OK = "#1f8a3b"
LOG_BAD = "#c0392b"
LOG_SKIP = "#8a9099"

# macOS 红黄绿三键：底色 / 符号颜色 / 悬停符号
LIGHTS = (
    ("#ff5f57", "#7a2b26", "✕"),   # 关闭
    ("#febc2e", "#8a5a00", "−"),   # 最小化
    ("#28c840", "#0b5d1e", "+"),   # 最大化
)


def enable_hidpi() -> None:
    """Windows 下声明高 DPI 感知，否则系统按位图拉伸窗口，字和线条都会发糊。"""
    if not IS_WIN:
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # 旧系统回退
        except Exception:
            pass


def asset_path(name: str) -> Path | None:
    """定位随程序分发的资源（PyInstaller 打包后在 _MEIPASS 里）。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    path = base / name
    return path if path.exists() else None


def _cursor(name_mac: str, name_win: str) -> str:
    """macOS 与其它平台的鼠标指针名称不同，避免 TclError。"""
    return name_mac if IS_MAC else name_win


def clean_drop_path(raw: str) -> Path:
    """把拖拽传来的路径清理成 Path。

    macOS 上路径含空格时会被花括号包起来（如 {/Users/me/My Photos}），
    这里统一去掉外层花括号和首尾空白。
    """
    text = raw.strip()
    while len(text) >= 2 and text.startswith("{") and text.endswith("}"):
        text = text[1:-1].strip()
    return Path(text)


# ---------------------------------------------------------------- 核心逻辑（与界面无关，便于测试）


def build_raw_map(raw_dir: Path) -> dict[str, Path]:
    """扫描 RAW 文件夹，返回 {文件名小写（不含扩展名）: 完整路径} 映射。"""
    mapping: dict[str, Path] = {}
    for item in sorted(raw_dir.iterdir()):
        try:
            if item.is_file() and item.suffix.lower() in RAW_EXTS:
                # 同一文件名存在多种 RAW 格式（如 CR2+CR3）时保留第一个，避免互相覆盖
                mapping.setdefault(item.stem.lower(), item)
        except OSError as exc:  # 个别文件读不到时跳过，不影响整体
            print(f"跳过无法访问的文件 {item}: {exc}", file=sys.stderr)
    return mapping


def process(jpg_dir: Path, raw_dir: Path, log) -> dict[str, int]:
    """
    执行一次完整的查找复制流程。

    :param jpg_dir: JPG 所在文件夹
    :param raw_dir: RAW 所在文件夹
    :param log: 接收日志字符串的回调（线程安全由调用方保证）
    :return: 统计字典 {"total","copied","missing","skipped"}
    """
    stats = {"total": 0, "copied": 0, "missing": 0, "skipped": 0}

    out_dir = jpg_dir / OUT_DIR_NAME
    try:
        out_dir.mkdir(exist_ok=True)
    except OSError as exc:
        log(f"✗ 无法创建输出文件夹 {out_dir}：{exc}")
        return stats
    log(f"输出文件夹：{out_dir}")

    # 建立 RAW 映射
    try:
        raw_map = build_raw_map(raw_dir)
    except OSError as exc:
        log(f"✗ 无法读取 RAW 文件夹：{exc}")
        return stats
    log(f"RAW 文件夹中共有 {len(raw_map)} 个 RAW 文件")

    # 遍历 JPG（只取顶层文件，输出文件夹是子目录所以不会被遍历到）
    try:
        jpg_files = sorted(
            (p for p in jpg_dir.iterdir() if p.is_file() and p.suffix.lower() in JPG_EXTS),
            key=lambda p: p.name.lower(),
        )
    except OSError as exc:
        log(f"✗ 无法读取 JPG 文件夹：{exc}")
        return stats

    log(f"开始处理，共 {len(jpg_files)} 个 JPG 文件...")

    for jpg in jpg_files:
        stats["total"] += 1
        target = raw_map.get(jpg.stem.lower())

        if target is None:
            stats["missing"] += 1
            log(f"✗ 未找到：{jpg.name} 对应的 RAW 文件")
            continue

        dest = out_dir / target.name
        if dest.exists():
            stats["skipped"] += 1
            log(f"⊘ 已跳过（已存在）：{target.name}")
            continue

        try:
            # copy2 保留原始修改时间 / 权限等元数据
            shutil.copy2(target, dest)
            stats["copied"] += 1
            log(f"✓ 已复制：{target.name}")
        except OSError as exc:
            log(f"✗ 复制失败：{target.name}（{exc}）")

    log(
        f"处理完成：共 {stats['total']} 个 JPG，成功复制 {stats['copied']} 个，"
        f"未找到 {stats['missing']} 个，跳过 {stats['skipped']} 个"
    )
    return stats


# ---------------------------------------------------------------- 自绘控件


class RoundButton(tk.Canvas):
    """扁平圆角按钮。Tk 原生按钮在 macOS 上无法自定义背景色，故用 Canvas 自绘。"""

    def __init__(self, master, text, command, *, bg, fg, hover, off=None,
                 width=120, height=38, radius=9, font=None) -> None:
        super().__init__(master, width=width, height=height, bg=master["bg"],
                         highlightthickness=0, bd=0, cursor=_cursor("pointinghand", "hand2"))
        self.text = text
        self.command = command
        self.color_base = bg
        self.color_hover = hover
        self.color_off = off or bg
        self.fg = fg
        self.font = font
        self.radius = radius
        self.width = width
        self.height = height
        self.enabled = True
        self._draw(bg)

        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", lambda _e: self.enabled and self._draw(self.color_hover))
        self.bind("<Leave>", lambda _e: self.enabled and self._draw(self.color_base))
        self.bind("<Button-1>", self._on_click)

    def _on_configure(self, event) -> None:
        if abs(event.width - self.width) > 1:  # 跟随父容器伸缩
            self.width = event.width
            self._draw(self.color_base if self.enabled else self.color_off)

    def _draw(self, color: str) -> None:
        self.delete("all")
        w, h, r = self.width, self.height, self.radius
        # 用平滑多边形近似圆角矩形（纯 Tk 没有原生圆角）
        self.create_polygon(
            [r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h, w - r, h,
             r, h, 0, h, 0, h - r, 0, r, 0, 0],
            smooth=True, splinesteps=36, fill=color, outline=color,
        )
        self.create_text(w / 2, h / 2, text=self.text, fill=self.fg, font=self.font)

    def _on_click(self, _event) -> None:
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.configure(cursor=_cursor("pointinghand", "hand2") if enabled else "arrow")
        self._draw(self.color_base if enabled else self.color_off)


class PathField(tk.Frame):
    """带边框的只读路径输入框，空值时显示灰色占位提示。"""

    def __init__(self, master, placeholder: str, font, pad: int) -> None:
        super().__init__(master, bg=CARD, highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=BORDER)
        self.placeholder = placeholder
        self.var = tk.StringVar(value=placeholder)
        self.entry = tk.Entry(
            self, textvariable=self.var, state="readonly", bd=0, highlightthickness=0,
            bg=CARD, readonlybackground=CARD, fg=MUTED, font=font,
        )
        self.entry.pack(fill="both", expand=True, padx=pad, pady=max(4, pad // 2))

    def set_path(self, path: Path) -> None:
        self.var.set(str(path))
        self.entry.configure(fg=TEXT)

    def clear(self) -> None:
        self.var.set(self.placeholder)
        self.entry.configure(fg=MUTED)

    def enable_drop(self, handler) -> None:
        """注册拖拽目标。输入框和它的外框都要注册，因为拖动时指针通常落在输入框上。"""
        if not DND_AVAILABLE:
            return
        for widget in (self, self.entry):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", handler)


# ---------------------------------------------------------------- 图形界面


class RawMatcherApp:
    """主窗口。只负责界面与线程调度，业务逻辑在 process() 中。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.jpg_dir: Path | None = None
        self.raw_dir: Path | None = None

        # 工作线程 -> 主线程 的日志队列，避免跨线程直接操作 Tk 控件
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.running = False
        self._zoomed = False
        self._saved_geom = ""
        self._drag_origin = (0, 0)
        self._size_origin = (0, 0)

        # 缩放系数：Mac 上 Tk 自己处理 Retina，其它平台按屏幕 DPI 手动缩放像素尺寸
        self.scale = 1.0 if IS_MAC else max(1.0, root.winfo_fpixels("1i") / 96.0)

        self._setup_fonts()
        self._build_ui()
        self._set_window_icon()
        self._log_startup_hint()
        self._poll_log_queue()  # 启动日志轮询

    # -------------------------------------------------------- 工具

    def px(self, value: float) -> int:
        """把设计稿上的像素值换算成当前屏幕的物理像素。"""
        return int(round(value * self.scale))

    # -------------------------------------------------------- 字体与图标

    def _setup_fonts(self) -> None:
        """挑选系统里可用的中文字体，避免方框乱码。"""
        available = set(tkfont.families(self.root))
        for family in ("PingFang SC", "Hiragino Sans GB", "Microsoft YaHei UI",
                       "Microsoft YaHei", "Noto Sans CJK SC", "Helvetica"):
            if family in available:
                break
        else:
            family = "TkDefaultFont"
        self.ui_font = family
        # 字号用「磅」指定，Tk 会按 DPI 自动换算成像素，天然高清
        self.f_title = (family, 22, "bold")
        self.f_sub = (family, 11)
        self.f_label = (family, 11, "bold")
        self.f_body = (family, 11)
        self.f_btn = (family, 12, "bold")
        self.f_small = (family, 10)
        self.f_glyph = (family, 8, "bold")
        self.f_mono = ("Menlo", 11) if IS_MAC else ("Consolas", 10)

    def _log_startup_hint(self) -> None:
        """启动时说明拖拽是否可用，避免用户拖半天以为程序坏了。"""
        if DND_AVAILABLE:
            self._append("提示：可直接把文件夹拖到上方输入框，或点「浏览」选择。", "head")
        else:
            self._append("提示：未安装 tkinterdnd2，拖拽不可用，请用「浏览」选择文件夹。", "head")

    def _set_window_icon(self) -> None:
        """设置窗口/任务栏图标，缺图标文件时静默跳过。"""
        png = asset_path("icon.png")
        try:
            if png:
                self._icon_image = tk.PhotoImage(file=str(png))  # 必须保持引用，否则被回收
                self.root.iconphoto(True, self._icon_image)
        except tk.TclError:
            pass
        if IS_WIN:
            ico = asset_path("icon.ico")
            try:
                if ico:
                    self.root.iconbitmap(str(ico))
            except tk.TclError:
                pass

    # -------------------------------------------------------- 界面构建

    def _build_ui(self) -> None:
        self.root.title(APP_TITLE)
        self.root.geometry(f"{self.px(840)}x{self.px(680)}")
        self.root.minsize(self.px(720), self.px(580))
        self.root.configure(bg=BG)

        outer = tk.Frame(self.root, bg=BG, padx=self.px(14), pady=self.px(14))
        outer.pack(fill="both", expand=True)

        # Windows/Linux 上自绘 macOS 风格标题栏；macOS 用系统原生标题栏
        if not IS_MAC:
            self.root.overrideredirect(True)
            self._build_titlebar(outer)

        card = tk.Frame(outer, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="both", expand=True)

        body = tk.Frame(card, bg=CARD, padx=self.px(26), pady=self.px(22))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(9, weight=1)  # 日志区吃掉剩余高度

        # 标题区
        tk.Label(body, text=HEADING, font=self.f_title, bg=CARD, fg=TEXT).grid(
            row=0, column=0, sticky="w")
        tk.Label(body, text=SUBTITLE, font=self.f_sub, bg=CARD, fg=MUTED).grid(
            row=1, column=0, sticky="w", pady=(self.px(4), self.px(20)))

        # JPG 文件夹
        self._add_label_row(body, 2, "JPG 文件夹", pady=(0, self.px(6)))
        self.jpg_field = PathField(body, JPG_PLACEHOLDER, self.f_body, self.px(10))
        self.jpg_field.grid(row=3, column=0, sticky="ew")
        self._attach_browse(self.jpg_field, "jpg")
        self.jpg_field.entry.bind("<Button-1>", lambda _e: self._choose_dir("jpg"))

        # RAW 文件夹
        self._add_label_row(body, 4, "RAW 文件夹", pady=(self.px(16), self.px(6)))
        self.raw_field = PathField(body, RAW_PLACEHOLDER, self.f_body, self.px(10))
        self.raw_field.grid(row=5, column=0, sticky="ew")
        self._attach_browse(self.raw_field, "raw")
        self.raw_field.entry.bind("<Button-1>", lambda _e: self._choose_dir("raw"))

        # 拖拽支持：把 Finder / 资源管理器里的文件夹直接拖到输入框上
        self.jpg_field.enable_drop(lambda event: self._on_drop("jpg", event))
        self.raw_field.enable_drop(lambda event: self._on_drop("raw", event))

        # 操作按钮行
        btn_row = tk.Frame(body, bg=CARD)
        btn_row.grid(row=6, column=0, sticky="ew", pady=(self.px(24), self.px(22)))
        btn_row.columnconfigure(0, weight=3)
        btn_row.columnconfigure(1, weight=2)

        self.start_btn = RoundButton(
            btn_row, "开始处理", self._on_start, bg=GREEN, hover=GREEN_HOVER,
            fg="white", off=GREEN_OFF, height=self.px(42), radius=self.px(9), font=self.f_btn,
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, self.px(8)))

        self.clear_btn = RoundButton(
            btn_row, "清空日志", self._clear_log, bg=NEUTRAL, hover=NEUTRAL_HOVER,
            fg=TEXT, height=self.px(42), radius=self.px(9), font=self.f_btn,
        )
        self.clear_btn.grid(row=0, column=1, sticky="ew", padx=(self.px(8), 0))

        # 日志区
        tk.Label(body, text="处理日志", font=self.f_label, bg=CARD, fg=TEXT).grid(
            row=8, column=0, sticky="w", pady=(0, self.px(6)))

        log_wrap = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        log_wrap.grid(row=9, column=0, sticky="nsew")
        log_wrap.rowconfigure(0, weight=1)
        log_wrap.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_wrap, wrap="word", state="disabled", bg="#fbfcfd", fg=TEXT,
            relief="flat", bd=0, padx=self.px(10), pady=self.px(8),
            spacing1=self.px(2), spacing3=self.px(2),
            font=self.f_mono, insertbackground=TEXT,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        for tag, color in (("ok", LOG_OK), ("bad", LOG_BAD), ("skip", LOG_SKIP),
                           ("head", MUTED), ("stat", TEXT)):
            self.log_text.tag_configure(tag, foreground=color)
        self.log_text.tag_configure("stat", font=(self.f_mono[0], self.f_mono[1], "bold"))

        scroll = tk.Scrollbar(log_wrap, command=self.log_text.yview, bd=0,
                              highlightthickness=0, width=self.px(12))
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

        # 状态栏（小圆点 + 文字）
        status_frame = tk.Frame(body, bg=CARD)
        status_frame.grid(row=10, column=0, sticky="ew", pady=(self.px(12), 0))
        self.status_dot = tk.Label(status_frame, text="●", font=self.f_small, bg=CARD, fg=MUTED)
        self.status_dot.pack(side="left")
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(status_frame, textvariable=self.status_var, font=self.f_small,
                 bg=CARD, fg=MUTED).pack(side="left", padx=(self.px(6), 0))

        if not IS_MAC:
            self._build_resize_grip()

    def _add_label_row(self, parent, row: int, text: str, pady) -> None:
        """标签行：左边是字段名，右边一行小字提示可以拖拽。"""
        line = tk.Frame(parent, bg=CARD)
        line.grid(row=row, column=0, sticky="ew", pady=pady)
        tk.Label(line, text=text, font=self.f_label, bg=CARD, fg=TEXT).pack(side="left")
        tk.Label(line, text=DROP_HINT, font=self.f_small, bg=CARD, fg=MUTED).pack(side="right")

    def _attach_browse(self, field: PathField, which: str) -> None:
        """在路径框右侧放一个「浏览」按钮，跟随输入框一同伸缩。"""
        parent = field.master
        btn = RoundButton(parent, "浏览", lambda: self._choose_dir(which),
                          bg=CARD, fg=TEXT, hover=NEUTRAL, width=self.px(74),
                          height=self.px(32), radius=self.px(7), font=self.f_body)
        btn.configure(highlightthickness=1, highlightbackground=BORDER)
        row = field.grid_info()["row"]
        parent.columnconfigure(0, weight=1)
        field.grid_configure(row=row, column=0, sticky="ew")
        btn.grid(row=row, column=1, sticky="w", padx=(self.px(8), 0))

    # -------------------------------------------------------- 自绘标题栏（非 macOS）

    def _build_titlebar(self, parent) -> None:
        """macOS 风格标题栏：红黄绿三键 + 居中标题 + 拖动移动。"""
        bar = tk.Frame(parent, bg=BG, height=self.px(34))
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        lights = tk.Canvas(bar, bg=BG, highlightthickness=0, bd=0,
                           width=self.px(78), height=self.px(34))
        lights.pack(side="left", padx=(self.px(4), 0))

        radius, cy = self.px(6), self.px(17)
        for index, (color, ink, glyph) in enumerate(LIGHTS):
            tag = ("close", "min", "zoom")[index]
            cx = self.px(16 + index * 22)
            lights.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                               fill=color, outline="", tags=(tag,))
            # 悬停时才显示符号，与 macOS 一致
            lights.create_text(cx, cy, text=glyph, fill=ink, state="hidden",
                               font=self.f_glyph, tags=(tag, tag + "_g"))
            lights.tag_bind(tag, "<Button-1>", lambda _e, i=index: self._traffic(i))
            lights.tag_bind(tag, "<Enter>",
                            lambda _e, t=tag: lights.itemconfigure(t + "_g", state="normal"))
            lights.tag_bind(tag, "<Leave>",
                            lambda _e, t=tag: lights.itemconfigure(t + "_g", state="hidden"))
            lights.tag_bind(tag, "<B1-Motion>", self._on_drag)

        title = tk.Label(bar, text=APP_TITLE, font=self.f_small, bg=BG, fg=MUTED)
        title.place(relx=0.5, rely=0.5, anchor="center")

        # 拖动窗口：标题栏空白处、标题文字、三键背景都算拖动区
        for widget in (bar, title, lights):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)
            widget.bind("<Double-Button-1>", lambda _e: self._toggle_zoom())

    def _build_resize_grip(self) -> None:
        """overrideredirect 窗口没有系统边框，右下角补一个缩放手柄。"""
        grip = tk.Canvas(self.root, bg=BG, highlightthickness=0, bd=0,
                         width=self.px(18), height=self.px(18),
                         cursor=_cursor("pointinghand", "size_nw_se"))
        grip.place(relx=1.0, rely=1.0, anchor="se")
        for offset in (self.px(14), self.px(9), self.px(4)):  # 三道斜线表示可缩放
            grip.create_line(self.px(18) - offset, self.px(16),
                             self.px(16), self.px(18) - offset,
                             fill="#c9cdd4", width=1)
        grip.bind("<Button-1>", self._start_resize)
        grip.bind("<B1-Motion>", self._on_resize)

    # -------------------------------------------------------- 窗口控制（自绘标题栏用）

    def _traffic(self, index: int) -> None:
        if index == 0:
            self.root.destroy()
        elif index == 1:
            self._minimize()
        else:
            self._toggle_zoom()

    def _start_drag(self, event) -> None:
        self._drag_origin = (event.x_root - self.root.winfo_x(),
                             event.y_root - self.root.winfo_y())

    def _on_drag(self, event) -> None:
        x = event.x_root - self._drag_origin[0]
        y = event.y_root - self._drag_origin[1]
        self.root.geometry(f"+{x}+{y}")

    def _start_resize(self, event) -> None:
        self._drag_origin = (event.x_root, event.y_root)
        self._size_origin = (self.root.winfo_width(), self.root.winfo_height())

    def _on_resize(self, event) -> None:
        width = max(self.px(720), self._size_origin[0] + event.x_root - self._drag_origin[0])
        height = max(self.px(580), self._size_origin[1] + event.y_root - self._drag_origin[1])
        self.root.geometry(f"{width}x{height}")

    def _toggle_zoom(self) -> None:
        if self._zoomed:
            self.root.geometry(self._saved_geom)
        else:
            self._saved_geom = self.root.geometry()
            self.root.geometry(f"{self.root.winfo_screenwidth()}x"
                               f"{self.root.winfo_screenheight()}+0+0")
        self._zoomed = not self._zoomed

    def _minimize(self) -> None:
        """overrideredirect 窗口无法直接最小化：先临时恢复系统边框再 iconify，
        恢复显示后再去掉边框，否则会永久丢掉自绘标题栏。"""
        try:
            self.root.overrideredirect(False)
            self.root.iconify()
            self.root.after(300, lambda: self.root.bind("<Map>", self._on_restore))
        except tk.TclError:
            pass

    def _on_restore(self, _event=None) -> None:
        self.root.unbind("<Map>")
        self.root.overrideredirect(True)

    # -------------------------------------------------------- 交互事件

    def _choose_dir(self, which: str) -> None:
        """弹出文件夹选择框（输入框只读，真实值存在 self.xxx_dir）。"""
        title = "选择 JPG 文件夹" if which == "jpg" else "选择 RAW 文件夹"
        chosen = filedialog.askdirectory(title=title, mustexist=True)
        if chosen:
            self._set_dir(which, Path(chosen))

    def _on_drop(self, which: str, event) -> None:
        """处理拖入的路径：去花括号 -> 校验是不是文件夹 -> 无效则提示并清空。"""
        # tkdnd 传来的是一段 Tcl 列表，splitlist 能正确处理含空格/花括号的路径
        try:
            items = self.root.tk.splitlist(event.data)
        except tk.TclError:
            items = [event.data]
        if not items:
            return

        path = clean_drop_path(items[0])
        if not path.is_dir():
            messagebox.showerror(
                "无效路径",
                f"拖入的路径不是有效的文件夹：\n{path}\n\n请拖入一个文件夹。",
                parent=self.root,
            )
            self._clear_field(which)
            return
        self._set_dir(which, path)

    def _set_dir(self, which: str, path: Path) -> None:
        """统一入口：浏览按钮和拖拽都走这里，保证两边行为一致。"""
        if which == "jpg":
            self.jpg_dir = path
            self.jpg_field.set_path(path)
        else:
            self.raw_dir = path
            self.raw_field.set_path(path)

    def _clear_field(self, which: str) -> None:
        if which == "jpg":
            self.jpg_dir = None
            self.jpg_field.clear()
        else:
            self.raw_dir = None
            self.raw_field.clear()

    def _set_status(self, text: str, color: str = MUTED) -> None:
        self.status_var.set(text)
        self.status_dot.configure(fg=color)

    def _on_start(self) -> None:
        if self.running:
            return
        # 校验：两个文件夹都必须已选择
        if self.jpg_dir is None or self.raw_dir is None:
            messagebox.showwarning("提示", "请先选择 JPG 文件夹和 RAW 文件夹！", parent=self.root)
            return
        if not self.jpg_dir.is_dir() or not self.raw_dir.is_dir():
            messagebox.showerror("错误", "所选文件夹不存在或无法访问，请重新选择。", parent=self.root)
            return

        self.running = True
        self.start_btn.set_enabled(False)
        self._set_status("处理中...", GREEN)
        self._append("─" * 52, "head")

        # 放到后台线程，界面不卡死
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        """后台线程：只调用纯逻辑 + 往队列塞日志，不直接碰 Tk 控件。"""
        try:
            process(self.jpg_dir, self.raw_dir, self._enqueue)
        except Exception as exc:  # 兜底：任何意外都不允许程序崩溃
            self._enqueue(f"✗ 发生未预期的错误：{exc!r}")
        finally:
            self._enqueue("__DONE__")

    def _enqueue(self, message: str) -> None:
        self.log_queue.put(message)

    def _poll_log_queue(self) -> None:
        """主线程定时消费日志队列，保证控件操作都在主线程。"""
        try:
            while True:
                message = self.log_queue.get_nowait()
                if message == "__DONE__":
                    self.running = False
                    self.start_btn.set_enabled(True)
                    self._set_status("完成", GREEN)
                else:
                    self._append(message, self._tag_for(message))
        except queue.Empty:
            pass
        self.root.after(80, self._poll_log_queue)

    @staticmethod
    def _tag_for(message: str) -> str:
        """按日志前缀上色，方便一眼扫出结果。"""
        if message.startswith("✓"):
            return "ok"
        if message.startswith("✗"):
            return "bad"
        if message.startswith("⊘"):
            return "skip"
        if message.startswith("处理完成"):
            return "stat"
        return "head"

    # -------------------------------------------------------- 日志

    def _append(self, message: str, tag: str = "head") -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._set_status("就绪", MUTED)


# ---------------------------------------------------------------- 自检


def _selftest() -> None:
    """最小可运行检查：python3 main.py --selftest（不需要图形界面）。"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jpg_dir, raw_dir = root / "jpg", root / "raw"
        jpg_dir.mkdir()
        raw_dir.mkdir()

        (jpg_dir / "a.JPG").write_bytes(b"x")
        (jpg_dir / "b.jpeg").write_bytes(b"x")
        (jpg_dir / "c.jpg").write_bytes(b"x")
        (raw_dir / "a.CR3").write_bytes(b"raw")
        (raw_dir / "b.NEF").write_bytes(b"raw")
        (raw_dir / "z.ARW").write_bytes(b"raw")

        stats = process(jpg_dir, raw_dir, lambda m: None)
        assert stats == {"total": 3, "copied": 2, "missing": 1, "skipped": 0}, stats
        assert (jpg_dir / OUT_DIR_NAME / "a.CR3").exists()

        # 第二次运行：已存在的应全部跳过
        stats = process(jpg_dir, raw_dir, lambda m: None)
        assert stats == {"total": 3, "copied": 0, "missing": 1, "skipped": 2}, stats

    # 拖拽路径清理：macOS 含空格路径会被花括号包裹，需去掉
    assert clean_drop_path("{/Users/me/My Photos}") == Path("/Users/me/My Photos")
    assert clean_drop_path("/Users/me/Pics") == Path("/Users/me/Pics")
    assert clean_drop_path("  {C:\\a b\\RAW}  ") == Path("C:\\a b\\RAW")

    print("selftest ok")


def main() -> None:
    if "--selftest" in sys.argv:
        _selftest()
        return
    enable_hidpi()
    # 装了 tkinterdnd2 才能接收拖拽；否则退回普通 Tk 窗口
    root = TkinterDnD.Tk() if DND_AVAILABLE else tk.Tk()
    RawMatcherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
