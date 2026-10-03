# -*- coding: utf-8 -*-
# 念 ToMe - 桌面座右铭：贴壁纸层 + 点击穿透 + 托盘编辑
# v3: 实时渲染+即时保存 / 界面主题跟随系统 / 全中文界面+语言切换
import ctypes
import json
import os
import sys
import winreg

from PySide6.QtCore import Qt, QRectF, QTimer, Signal, QPointF
from PySide6.QtGui import (QPainter, QColor, QPen, QFont, QFontMetrics, QIcon,
                           QPixmap, QAction, QLinearGradient, QFontDatabase)
from PySide6.QtWidgets import (QApplication, QWidget, QDialog, QVBoxLayout,
                               QHBoxLayout, QLabel, QTextEdit, QPushButton,
                               QSlider, QComboBox, QCheckBox, QSystemTrayIcon,
                               QMenu, QFrame, QGridLayout, QListWidget,
                               QListWidgetItem, QStackedWidget)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
HWND_TOPMOST, HWND_NOTOPMOST, HWND_BOTTOM = -1, -2, 1
WM_SETTINGCHANGE = 0x001A
MAX_LINES = 10
PAD = 14

user32.GetParent.argtypes = [ctypes.c_void_p]
user32.GetParent.restype = ctypes.c_void_p

APPDATA_DIR = os.path.join(os.environ.get("APPDATA", "."), "ToMe")
CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")

DEFAULT_CFG = {
    "text": "此刻专注\n只做最重要的事",
    "font_family": "Microsoft YaHei",
    "font_pt": 32.0,
    "bold": False,
    "italic": False,
    "text_color": 0xFFFFFF,
    "border_color": 0xFFFFFF,
    "border_alpha": 0,        # 0=隐形 100=实线
    "line_gap": 10,
    "align": 1,               # 0左 1中 2右
    "x": 80, "y": 80, "w": 700, "h": 240,
    "first_run": False,
    "lang": "zh",             # zh / en
    "theme": "auto",          # auto / dark / light
}

user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetParent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_uint]
user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.FindWindowW.restype = ctypes.c_void_p
user32.FindWindowExW.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_wchar_p, ctypes.c_wchar_p]
user32.FindWindowExW.restype = ctypes.c_void_p
user32.SendMessageTimeoutW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                       ctypes.c_size_t, ctypes.c_ssize_t,
                                       ctypes.c_uint, ctypes.c_uint,
                                       ctypes.POINTER(ctypes.c_size_t)]

# ---- DWM / Mica（Win11 Fluent 材质）----
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMSBT_MAINWINDOW = 2      # Mica
DWMWCP_ROUND = 2


class _MARGINS(ctypes.Structure):
    _fields_ = [("cxLeftWidth", ctypes.c_int),
                ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int),
                ("cyBottomHeight", ctypes.c_int)]


dwmapi.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                         ctypes.c_void_p, ctypes.c_uint]
dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
dwmapi.DwmExtendFrameIntoClientArea.argtypes = [ctypes.c_void_p,
                                                ctypes.POINTER(_MARGINS)]
dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long


def win_build():
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0


def enable_mica(widget, dark):
    """给无边框对话框开 Win11 Mica 材质 + 圆角 + DWM 阴影。
    成功返回 True（QSS 需把窗口背景设 transparent 让 Mica 透出）；
    Win10 / 失败返回 False，调用方回退纯色 Mica 替身底。"""
    if win_build() < 22000:
        return False
    try:
        hwnd = int(widget.winId())
        v = ctypes.c_int(1 if dark else 0)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                                     ctypes.byref(v), ctypes.sizeof(v))
        v = ctypes.c_int(DWMSBT_MAINWINDOW)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
                                     ctypes.byref(v), ctypes.sizeof(v))
        v = ctypes.c_int(DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                     ctypes.byref(v), ctypes.sizeof(v))
        m = _MARGINS(-1, -1, -1, -1)   # 帧扩展进客户区：Mica 透出 + 恢复阴影
        if dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m)) != 0:
            return False
        return True
    except (OSError, ValueError):
        return False

# ---------------- 多语言文案 ----------------
STR = {
    "zh": {
        "app": "念",
        "brand": "念",
        "title": "念 · 设置",
        "text_label": "文字（最多 %d 行）",
        "font": "字体…",
        "text_color": "文字颜色…",
        "border_color": "边框颜色…",
        "border_alpha": "边框透明度",
        "line_gap": "行间距 (px)",
        "align": "对齐",
        "aligns": ["左对齐", "居中", "右对齐"],
        "autorun": "开机自动启动",
        "done": "完成",
        "ok": "确定",
        "lang_label": "界面语言",
        "theme_label": "界面主题",
        "themes": ["跟随系统", "深色", "浅色"],
        "langs": ["中文", "English"],
        "sec_text": "文字内容",
        "sec_style": "字体样式",
        "sec_misc": "其他设置",
        "font_size": "字号 (pt)",
        "tip": "念 — 桌面座右铭",
        "balloon_t": "念已就位",
        "balloon_b": "文字已贴在桌面。右键（或双击）托盘图标即可编辑。",
        "menu_edit": "编辑文字 / 位置",
        "menu_exit": "退出",
        "font_dlg": "选择字体",
        "fp_family": "字体",
        "fp_size": "字号",
        "fp_bold": "粗体",
        "fp_italic": "斜体",
        "cancel": "取消",
        "tc_dlg": "选择文字颜色",
        "bc_dlg": "选择边框颜色",
    },
    "en": {
        "app": "ToMe",
        "brand": "T",
        "title": "ToMe · Settings",
        "text_label": "Text (max %d lines)",
        "font": "Font…",
        "text_color": "Text color…",
        "border_color": "Border color…",
        "border_alpha": "Border opacity",
        "line_gap": "Line spacing (px)",
        "align": "Align",
        "aligns": ["Left", "Center", "Right"],
        "autorun": "Start with Windows",
        "done": "Done",
        "ok": "OK",
        "lang_label": "Language",
        "theme_label": "Theme",
        "themes": ["Follow system", "Dark", "Light"],
        "langs": ["中文", "English"],
        "sec_text": "Text",
        "sec_style": "Font style",
        "sec_misc": "General",
        "font_size": "Font size (pt)",
        "tip": "ToMe — desktop motto",
        "balloon_t": "ToMe is ready",
        "balloon_b": "Text pinned to desktop. Right-click (or double-click) the tray icon to edit.",
        "menu_edit": "Edit text / position",
        "menu_exit": "Exit",
        "font_dlg": "Choose font",
        "fp_family": "Font",
        "fp_size": "Size",
        "fp_bold": "Bold",
        "fp_italic": "Italic",
        "cancel": "Cancel",
        "tc_dlg": "Choose text color",
        "bc_dlg": "Choose border color",
    },
}


def tr(key):
    return STR[S["cfg"].get("lang", "zh")][key]


# ---------------- 配置 ----------------
def load_cfg():
    cfg = dict(DEFAULT_CFG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_cfg(cfg=None):
    c = cfg if cfg is not None else S["cfg"]
    if S["win"]:
        g = S["win"].geometry()
        c["x"], c["y"], c["w"], c["h"] = g.x(), g.y(), g.width(), g.height()
    try:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def dbg(msg):
    """诊断日志：排查渲染/层级问题用"""
    try:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        p = os.path.join(APPDATA_DIR, "debug.log")
        if os.path.exists(p) and os.path.getsize(p) > 200000:
            os.remove(p)
        from time import strftime
        with open(p, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (strftime("%H:%M:%S"), msg))
    except OSError:
        pass


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_autorun():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "ToMe")
            return True
    except OSError:
        return False


def set_autorun(on):
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            if on:
                winreg.SetValueEx(k, "ToMe", 0, winreg.REG_SZ,
                                  '"%s"' % sys.executable)
            else:
                try:
                    winreg.DeleteValue(k, "ToMe")
                except FileNotFoundError:
                    pass
    except OSError:
        pass


def system_is_dark():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return v == 0
    except OSError:
        return True


def current_dark():
    t = S["cfg"].get("theme", "auto")
    if t == "dark":
        return True
    if t == "light":
        return False
    return system_is_dark()


def attach_wallpaper(hwnd):
    """压到 Z 序最底层（独立顶层窗口方案）。
    注：曾尝试 SetParent 进 WorkerW 壁纸层，但 Qt 透明窗口挂进去后不渲染，
    故放弃；HWND_BOTTOM 垫底效果等价且渲染正常。"""
    # 确保没有残留的置顶状态
    ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TOPMOST:
        ex &= ~WS_EX_TOPMOST
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0,
                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
    dbg("attach -> bottom")
    return "bottom"


def truncate_lines(s, maxl=MAX_LINES):
    if s is None:
        return ""
    parts = s.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(parts) <= maxl:
        return s
    return "\n".join(parts[:maxl])


ALIGN_FLAGS = {0: Qt.AlignLeft, 1: Qt.AlignHCenter, 2: Qt.AlignRight}


# ---------------- QSS ----------------
def make_qss(dark, for_picker=False, mica=False):
    """Win11 Fluent 2：Mica 材质底 + Layer/Card 分层 + 8/4 圆角阶 + 单一 accent。
    色值取自 Fluent 主题 token（Text/Card/Fill/Accent 系列）。
    mica=True 时窗口背景透明，让 DWM Mica 透出；否则用纯色 Mica 替身底。"""
    if dark:
        V = dict(
            WINBG="#202020",
            CARDBG="#2b2b2b", CARDSTROKE="rgba(255,255,255,0.08)",
            INPUTBG="#333334",
            INPUTSTROKE="rgba(255,255,255,0.09)",
            INPUTSTROKE2="rgba(255,255,255,0.16)",
            BTNSTROKE="rgba(255,255,255,0.12)",
            TXT="#ffffff", TXT2="#c8c8c8", TXT3="#9e9e9e",
            SUBTLE="rgba(255,255,255,0.056)",
            PRESSED="rgba(255,255,255,0.032)",
            NAVSEL="rgba(255,255,255,0.06)",
            ACC="#0078d4", ACC_HOV="#2890e3", ACC_PRESS="#006cbd",
            ACCINT="#4cc2ff",
            SELBG="rgba(76,194,255,0.14)",
            TRACK="rgba(255,255,255,0.16)",
            SCROLL="rgba(255,255,255,0.28)", SCROLL_HOV="rgba(255,255,255,0.42)",
            CLOSE_HOV="#c42b1c",
        )
    else:
        V = dict(
            WINBG="#f3f3f3",
            CARDBG="#ffffff", CARDSTROKE="rgba(0,0,0,0.058)",
            INPUTBG="#ffffff",
            INPUTSTROKE="rgba(0,0,0,0.10)",
            INPUTSTROKE2="rgba(0,0,0,0.16)",
            BTNSTROKE="rgba(0,0,0,0.13)",
            TXT="#1b1b1b", TXT2="#5e5e5e", TXT3="#707070",
            SUBTLE="rgba(0,0,0,0.056)",
            PRESSED="rgba(0,0,0,0.032)",
            NAVSEL="rgba(0,0,0,0.046)",
            ACC="#0067c0", ACC_HOV="#1975c5", ACC_PRESS="#004c94",
            ACCINT="#0067c0",
            SELBG="rgba(0,103,192,0.12)",
            TRACK="rgba(0,0,0,0.16)",
            SCROLL="rgba(0,0,0,0.24)", SCROLL_HOV="rgba(0,0,0,0.40)",
            CLOSE_HOV="#c42b1c",
        )
    winbg = "transparent" if mica else "@WINBG"
    t = """
    QDialog { background: %s; }
    QStackedWidget { background: transparent; }
    QWidget#page { background: transparent; }
    QLabel { color: @TXT2; font-size: 13px; background: transparent; }
    QLabel#sec { color: @TXT; font-size: 13px; font-weight: 600; }
    QLabel#value { color: @TXT2; font-size: 13px;
        min-width: 34px; qproperty-alignment: AlignCenter; }

    QFrame#card { background: @CARDBG; border: 1px solid @CARDSTROKE;
        border-radius: 8px; }

    /* ---- NavigationView ---- */
    QListWidget#nav { background: transparent; border: none; outline: none;
        font-size: 13px; padding-top: 4px; }
    QListWidget#nav::item { color: @TXT2; padding: 9px 12px 9px 14px;
        border-radius: 6px; margin: 2px 8px 2px 0;
        border-left: 3px solid transparent; }
    QListWidget#nav::item:hover { background: @SUBTLE; }
    QListWidget#nav::item:selected { background: @NAVSEL; color: @TXT;
        border-left: 3px solid @ACCINT; }

    /* ---- 输入控件（TextBox / ComboBox）---- */
    QTextEdit, QComboBox { background: @INPUTBG; color: @TXT;
        border: 1px solid @INPUTSTROKE; border-bottom: 2px solid @INPUTSTROKE2;
        border-radius: 4px; padding: 7px 9px; font-size: 13px;
        selection-background-color: @SELBG; }
    QTextEdit:focus, QComboBox:focus { border-bottom: 2px solid @ACCINT; }
    QComboBox QAbstractItemView { background: @CARDBG; color: @TXT;
        border: 1px solid @CARDSTROKE; border-radius: 8px; padding: 4px;
        outline: none; }
    QComboBox QAbstractItemView::item { min-height: 30px; border-radius: 4px;
        padding: 4px 10px; }
    QComboBox QAbstractItemView::item:hover { background: @SUBTLE; }
    QComboBox QAbstractItemView::item:selected { background: @SELBG; color: @TXT; }
    QComboBox::drop-down { border: none; width: 26px; }
    QComboBox::down-arrow { width: 10px; height: 10px; }

    /* ---- Button（标准/强调/标题栏关闭）---- */
    QPushButton { background: @CARDBG; color: @TXT;
        border: 1px solid @BTNSTROKE; border-radius: 4px;
        padding: 7px 16px; font-size: 13px; }
    QPushButton:hover { background: @SUBTLE; border-color: @BTNSTROKE; }
    QPushButton:pressed { background: @PRESSED; }
    QPushButton:disabled { color: @TXT3; }
    QPushButton#done { background: @ACC; border: none; color: #ffffff;
        font-size: 14px; font-weight: 600; padding: 8px 0;
        border-radius: 4px; }
    QPushButton#done:hover { background: @ACC_HOV; }
    QPushButton#done:pressed { background: @ACC_PRESS; }
    QPushButton#close { background: transparent; border: none; color: @TXT3;
        font-size: 14px; padding: 0; min-width: 0; border-radius: 4px; }
    QPushButton#close:hover { background: @CLOSE_HOV; color: #ffffff; }

    /* ---- Slider ---- */
    QSlider { background: transparent; height: 24px; }
    QSlider::groove:horizontal { height: 4px; background: @TRACK;
        border-radius: 2px; }
    QSlider::sub-page:horizontal { background: @ACCINT; border-radius: 2px; }
    QSlider::handle:horizontal { width: 12px; height: 12px; margin: -4px 0;
        border-radius: 6px; background: @ACCINT; border: none; }
    QSlider::handle:horizontal:hover { width: 14px; height: 14px;
        margin: -5px 0; border-radius: 7px; }

    /* ---- 字体选择器 ---- */
    QListWidget#fp_list { background: @INPUTBG; color: @TXT;
        border: 1px solid @INPUTSTROKE; border-radius: 4px; padding: 4px;
        font-size: 12px; outline: none; }
    QListWidget#fp_list::item { padding: 5px 10px; border-radius: 4px;
        color: @TXT2; min-height: 22px; }
    QListWidget#fp_list::item:hover { background: @SUBTLE; }
    QListWidget#fp_list::item:selected { background: @SELBG; color: @TXT; }
    QLabel#fp_preview { background: @INPUTBG; border: 1px solid @INPUTSTROKE;
        border-radius: 4px; color: @TXT; font-size: 14px; padding: 10px; }
    QLabel#swatch { border: 1px solid @INPUTSTROKE; }

    /* ---- ScrollBar ---- */
    QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
    QScrollBar::handle:vertical { background: @SCROLL; border-radius: 4px;
        min-height: 32px; }
    QScrollBar::handle:vertical:hover { background: @SCROLL_HOV; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
    """ % winbg
    for k in sorted(V, key=len, reverse=True):  # 长键先替换，避免 @ACC 抢了 @ACC_HOV
        t = t.replace("@" + k, V[k])
    return t


# ================= 主显示窗口 =================
class MottoWindow(QWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.editing = False
        self.dragging = False
        self.resizing = False
        self.press_global = None
        self.pos0 = None
        self.size0 = None
        self.dlg = None
        self.tray = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(int(cfg["x"]), int(cfg["y"]),
                         int(cfg["w"]), int(cfg["h"]))
        self.setMinimumSize(120, 60)

        # 心跳自愈：每 20 秒确认窗口仍在壁纸层，丢失则重新挂（Explorer 重启等）
        self._hb = QTimer(self)
        self._hb.setInterval(20000)
        self._hb.timeout.connect(self.check_attach)

    def check_attach(self):
        if self.editing or not self.isVisible():
            return
        # 周期性重申：沉底 + 穿透（防止其他程序扰动 z 序或样式漂移）
        attach_wallpaper(int(self.winId()))
        hwnd = int(self.winId())
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        if not (ex & WS_EX_TRANSPARENT):
            ex |= WS_EX_TRANSPARENT
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)

    # ---- 模式切换 ----
    def apply_display_mode(self):
        hwnd = int(self.winId())
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        ex |= WS_EX_TRANSPARENT
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
        mode = attach_wallpaper(hwnd)
        dbg("display_mode attached=%s" % mode)
        self._hb.start()  # 启动心跳自愈

    def set_edit_mode(self, on):
        self.editing = on
        hwnd = int(self.winId())
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        if on:
            ex &= ~WS_EX_TRANSPARENT
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE)
            self.setCursor(Qt.SizeAllCursor)
        else:
            # 显式取消置顶（v3 bug：TOPMOST 残留导致文字浮在所有窗口上）
            ex &= ~(WS_EX_TRANSPARENT | WS_EX_TOPMOST)
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            attach_wallpaper(hwnd)  # 沉底
            ex |= WS_EX_TRANSPARENT
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
            self.unsetCursor()
        self.repaint()  # 同步强制重绘
        dbg("edit_mode=%s" % on)

    def ensure_on_screen(self):
        scr = QApplication.primaryScreen().availableGeometry()
        p = self.pos()
        if p.x() < -self.width() + 60 or p.y() < -20 or \
           p.x() > scr.width() - 60 or p.y() > scr.height() - 60:
            self.move(80, 80)
        if self.width() > scr.width():
            self.resize(scr.width(), self.height())
        if self.height() > scr.height():
            self.resize(self.width(), scr.height())

    def auto_fit(self):
        """字号/行距/字体变大后，窗口自动撑大到刚好装下所有文字（不裁字）"""
        if not self.editing:
            return
        cfg = self.cfg
        font = QFont(cfg["font_family"], int(round(cfg["font_pt"])))
        font.setBold(bool(cfg["bold"]))
        font.setItalic(bool(cfg["italic"]))
        fm = QFontMetrics(font)
        lines = (cfg.get("text") or "").replace("\r\n", "\n") \
            .replace("\r", "\n").split("\n")[:MAX_LINES]
        lines = [l for l in lines] or [""]
        n = max(1, len(lines))
        gap = int(cfg.get("line_gap", 0))
        need_h = PAD * 2 + n * fm.height() + (n - 1) * gap
        need_w = 0
        for line in lines:
            need_w = max(need_w, fm.horizontalAdvance(line))
        need_w = int(need_w) + PAD * 2
        scr = QApplication.primaryScreen().availableGeometry()
        need_w = max(self.width(), min(need_w, scr.width()))
        need_h = max(self.height(), min(need_h, scr.height()))
        self.resize(need_w, need_h)
        # 高度撑大后若底部出屏，整体上移
        if self.y() + self.height() > scr.bottom():
            self.move(self.x(), max(0, scr.bottom() - self.height()))

    def start_edit(self):
        if self.editing:
            if self.dlg:
                self.dlg.raise_()
                self.dlg.activateWindow()
            return
        self.ensure_on_screen()
        self.set_edit_mode(True)
        self.dlg = SettingsDialog(self)
        self.dlg.show()

    def finish_edit(self):
        self.dlg = None
        save_cfg(self.cfg)
        if self.isVisible():
            self.set_edit_mode(False)

    # ---- 绘制 ----
    def paintEvent(self, ev):
        cfg = self.cfg
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        W, H = self.width(), self.height()

        font = QFont(cfg["font_family"], int(round(cfg["font_pt"])))
        font.setBold(bool(cfg["bold"]))
        font.setItalic(bool(cfg["italic"]))
        p.setFont(font)
        fm = QFontMetrics(font)

        lines = (cfg.get("text") or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        gap = int(cfg.get("line_gap", 0))
        align = ALIGN_FLAGS.get(int(cfg.get("align", 1)), Qt.AlignHCenter)
        p.setPen(QColor((cfg["text_color"] >> 16) & 0xFF,
                        (cfg["text_color"] >> 8) & 0xFF,
                        cfg["text_color"] & 0xFF))
        y = PAD
        for i, line in enumerate(lines):
            if i >= MAX_LINES:
                break
            if line:
                rect = QRectF(PAD, y, W - 2 * PAD, fm.height())
                p.drawText(rect, align | Qt.AlignVCenter | Qt.TextSingleLine, line)
            y += fm.height() + gap

        if self.editing:
            p.setPen(QPen(QColor(0, 174, 255, 230), 1.5, Qt.DashLine))
            p.drawRect(QRectF(0.75, 0.75, W - 1.5, H - 1.5))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 174, 255, 230))
            s, cx, cy = 6, W - 1, H - 1
            p.drawRect(cx - s, cy - s, s, s)
            p.drawRect(cx - s, cy - 2 * s, s, s)
            p.drawRect(cx - 2 * s, cy - 2 * s, s, s)
        elif int(cfg.get("border_alpha", 0)) > 0:
            a = int(cfg["border_alpha"]) * 255 // 100
            col = QColor((cfg["border_color"] >> 16) & 0xFF,
                         (cfg["border_color"] >> 8) & 0xFF,
                         cfg["border_color"] & 0xFF, a)
            p.setPen(QPen(col, 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(1, 1, W - 2, H - 2))

    # ---- 编辑态拖动 / 缩放 ----
    def mousePressEvent(self, ev):
        if self.editing and ev.button() == Qt.LeftButton:
            self.press_global = ev.globalPosition().toPoint()
            self.pos0, self.size0 = self.pos(), self.size()
            corner = (ev.position().x() >= self.width() - 22 and
                      ev.position().y() >= self.height() - 22)
            self.resizing = corner
            self.dragging = not corner
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self.editing:
            corner = (ev.position().x() >= self.width() - 22 and
                      ev.position().y() >= self.height() - 22)
            self.setCursor(Qt.SizeFDiagCursor if corner else Qt.SizeAllCursor)
            if self.dragging and self.press_global:
                delta = ev.globalPosition().toPoint() - self.press_global
                self.move(self.pos0 + delta)
                ev.accept()
                return
            if self.resizing and self.press_global:
                delta = ev.globalPosition().toPoint() - self.press_global
                self.resize(max(120, self.size0.width() + delta.x()),
                            max(60, self.size0.height() + delta.y()))
                ev.accept()
                return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self.editing and (self.dragging or self.resizing):
            save_cfg(self.cfg)  # 位置/大小改动立即保存
        self.dragging = self.resizing = False
        super().mouseReleaseEvent(ev)


# ================= Fluent 组件 =================
class ToggleSwitch(QCheckBox):
    """Fluent ToggleSwitch（自绘）：40x20 轨道 + 12 圆点。
    关=透明底+中性描边+灰圆点；开=accent 填充+白圆点。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 20)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False
        self.setText("")

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dark = current_dark()
        w, h = self.width(), self.height()
        r = h / 2
        d = h - 8          # 12px 圆点
        x = w - d - 4 if self.isChecked() else 4
        if self.isChecked():
            # Fluent：浅色 #0067C0 / 深色 SystemAccentColorLight1
            track = QColor("#0067c0") if not dark else QColor("#4cc2ff")
            if self._hover:
                track = track.lighter(110)
            p.setPen(Qt.NoPen)
            p.setBrush(track)
            p.drawRoundedRect(QRectF(0, 0, w, h), r, r)
            knob = QColor("#ffffff")
        else:
            if self._hover:
                fill = QColor(0, 0, 0, 14) if not dark else QColor(255, 255, 255, 14)
                edge = QColor("#5d5d5d") if not dark else QColor("#7d7d7d")
                knob = QColor("#5d5d5d") if not dark else QColor("#7d7d7d")
            else:
                fill = Qt.NoBrush
                edge = QColor("#838383") if not dark else QColor("#858585")
                knob = QColor("#707070") if not dark else QColor("#858585")
            p.setPen(QPen(edge, 1))
            p.setBrush(fill)
            p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r - 0.5, r - 0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(knob)
        p.drawEllipse(QRectF(x, 4, d, d))


class SVPanel(QWidget):
    """HSV 饱和度/明度二维取色面板"""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(320, 190)
        self.hue = 0.0
        self.s = 1.0
        self.v = 1.0

    def setHSV(self, h, s, v):
        self.hue, self.s, self.v = h, s, v
        self.update()

    def _pick(self, pos):
        self.s = min(1.0, max(0.0, pos.x() / self.width()))
        self.v = min(1.0, max(0.0, 1 - pos.y() / self.height()))
        self.changed.emit()
        self.update()

    def mousePressEvent(self, ev):
        self._pick(ev.position())

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.LeftButton:
            self._pick(ev.position())

    def paintEvent(self, e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor.fromHsvF(self.hue, 1, 1))
        g1 = QLinearGradient(0, 0, w, 0)
        g1.setColorAt(0, QColor(255, 255, 255))
        g1.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(self.rect(), g1)
        g2 = QLinearGradient(0, 0, 0, h)
        g2.setColorAt(0, QColor(0, 0, 0, 0))
        g2.setColorAt(1, QColor(0, 0, 0))
        p.fillRect(self.rect(), g2)
        cx, cy = self.s * w, (1 - self.v) * h
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 6, 6)
        p.setPen(QPen(QColor(0, 0, 0, 130), 1))
        p.drawEllipse(QPointF(cx, cy), 7, 7)


class HueBar(QWidget):
    """HSV 色相条"""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(320, 22)
        self.hue = 0.0

    def setHue(self, h):
        self.hue = h
        self.update()

    def _pick(self, pos):
        self.hue = min(0.9999, max(0.0, pos.x() / self.width()))
        self.changed.emit()
        self.update()

    def mousePressEvent(self, ev):
        self._pick(ev.position())

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.LeftButton:
            self._pick(ev.position())

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        g = QLinearGradient(0, 0, self.width(), 0)
        for i, c in enumerate([QColor(255, 0, 0), QColor(255, 255, 0),
                               QColor(0, 255, 0), QColor(0, 255, 255),
                               QColor(0, 0, 255), QColor(255, 0, 255),
                               QColor(255, 0, 0)]):
            g.setColorAt(i / 6.0, c)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(self.rect(), 8, 8)
        cx = self.hue * self.width()
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, self.height() / 2), 7, 7)
        p.setPen(QPen(QColor(0, 0, 0, 130), 1))
        p.drawEllipse(QPointF(cx, self.height() / 2), 8, 8)


PRESET_COLORS = ["#e81123", "#f7630c", "#ffb900", "#107c10", "#00b294",
                 "#0078d4", "#4f6bed", "#886ce4", "#e3008c", "#f763a8",
                 "#ffffff", "#c8ccd4", "#6b7280", "#2b2e37", "#000000",
                 "#4f8cff"]


class ColorPickerDialog(QDialog):
    """现代取色器：SV 面板 + 色相条 + 预设色板"""
    def __init__(self, initial, parent, title):
        super().__init__(parent)
        self._mica = False
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint |
                            Qt.WindowStaysOnTopHint)
        c = QColor(initial)
        h, s, v, _ = c.getHsvF()
        self._h = (h if h >= 0 else 0)
        self._s = s
        self._v = v
        self._color = c

        v0 = QVBoxLayout(self)
        v0.setContentsMargins(20, 8, 20, 16)
        v0.setSpacing(12)

        rowt = QHBoxLayout()
        rowt.addStretch(1)
        btn_close = QPushButton("✕")
        btn_close.setObjectName("close")
        btn_close.setFixedSize(32, 32)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.reject)
        rowt.addWidget(btn_close)
        v0.addLayout(rowt)

        self.sv = SVPanel()
        self.sv.setHSV(self._h, self._s, self._v)
        v0.addWidget(self.sv)
        self.bar = HueBar()
        self.bar.setHue(self._h)
        v0.addWidget(self.bar)

        rowp = QHBoxLayout()
        self.swatch = QLabel()
        self.swatch.setFixedSize(56, 34)
        self.swatch.setObjectName("swatch")
        self.swatch.setAlignment(Qt.AlignCenter)
        rowp.addWidget(self.swatch)
        self.hexlbl = QLabel()
        self.hexlbl.setObjectName("value")
        rowp.addWidget(self.hexlbl)
        rowp.addStretch(1)
        v0.addLayout(rowp)

        grid = QGridLayout()
        grid.setSpacing(6)
        edge = ("rgba(255,255,255,0.22)" if current_dark()
                else "rgba(0,0,0,0.18)")
        hov = "#4cc2ff" if current_dark() else "#0067c0"
        for i, hexc in enumerate(PRESET_COLORS):
            b = QPushButton()
            b.setFixedSize(30, 30)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton { background: %s; border: 1px solid %s;"
                " border-radius: 4px; min-width: 30px; max-width: 30px; }"
                "QPushButton:hover { border: 2px solid %s; }"
                % (hexc, edge, hov))
            b.clicked.connect(lambda _=False, hx=hexc: self.set_hex(hx))
            grid.addWidget(b, i // 8, i % 8)
        v0.addLayout(grid)

        rowb = QHBoxLayout()
        rowb.addStretch(1)
        ok = QPushButton(tr("ok"))
        ok.setObjectName("done")
        ok.setFixedWidth(120)
        ok.clicked.connect(self.accept)
        rowb.addWidget(ok)
        v0.addLayout(rowb)

        self.sv.changed.connect(self.sync_from_sv)
        self.bar.changed.connect(self.sync_from_hue)
        self.sync_ui()
        self.apply_picker_theme()

    def apply_picker_theme(self):
        dark = current_dark()
        self._mica = enable_mica(self, dark)
        self.setStyleSheet(make_qss(dark, False, self._mica) +
                           "QLabel#swatch { border-radius: 4px; }")

    def showEvent(self, ev):
        super().showEvent(ev)
        self.apply_picker_theme()

    # ---- 无边框拖拽 ----
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = ev.globalPosition().toPoint() - \
                self.frameGeometry().topLeft()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        d = getattr(self, "_drag", None)
        if d is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - d)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag = None
        super().mouseReleaseEvent(ev)

    def set_hex(self, hexc):
        c = QColor(hexc)
        h, s, v, _ = c.getHsvF()
        self._h = h if h >= 0 else 0
        self._s = s
        self._v = v
        self.sv.setHSV(self._h, self._s, self._v)
        self.bar.setHue(self._h)
        self.sync_ui()

    def sync_from_sv(self):
        self._h, self._s, self._v = self.sv.hue, self.sv.s, self.sv.v
        self.bar.setHue(self._h)
        self.sync_ui()

    def sync_from_hue(self):
        self._h = self.bar.hue
        self.sv.setHSV(self._h, self._s, self._v)
        self.sync_ui()

    def sync_ui(self):
        self._color = QColor.fromHsvF(self._h, self._s, self._v)
        self.swatch.setStyleSheet(
            "QLabel { background: %s; border-radius: 4px; }" % self._color.name())
        self.hexlbl.setText(self._color.name().upper())

    def picked_color(self):
        return self._color


# ================= 设置窗 =================
class MSGStruct(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                ("time", ctypes.c_uint), ("pt", ctypes.c_void_p)]


class FontPickerDialog(QDialog):
    """现代字体选择器：字体列表 + 字号滑杆 + 粗斜体开关 + 实时预览"""
    def __init__(self, family, pt, bold, italic, parent):
        super().__init__(parent)
        self._mica = False
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint |
                            Qt.WindowStaysOnTopHint)
        self._family = family
        self._pt = float(pt)
        self._bold = bool(bold)
        self._italic = bool(italic)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 8, 20, 16)
        root.setSpacing(12)

        rowt = QHBoxLayout()
        rowt.addStretch(1)
        btn_close = QPushButton("✕")
        btn_close.setObjectName("close")
        btn_close.setFixedSize(32, 32)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.reject)
        rowt.addWidget(btn_close)
        root.addLayout(rowt)

        body = QHBoxLayout()
        body.setSpacing(16)

        col1 = QVBoxLayout()
        self.lbl_family = QLabel(tr("fp_family"))
        self.lst = QListWidget()
        self.lst.setObjectName("fp_list")
        self.lst.setFixedWidth(216)
        self.lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        fams = sorted(QFontDatabase().families(), key=str.lower)
        cur = -1
        for i, f in enumerate(fams):
            it = QListWidgetItem(f)
            it.setFont(QFont(f, 10))   # 每个字体名用它自己渲染
            self.lst.addItem(it)
            if f == family:
                cur = i
        if cur >= 0:
            self.lst.setCurrentRow(cur)
        self.lst.currentRowChanged.connect(self.on_family)
        col1.addWidget(self.lbl_family)
        col1.addWidget(self.lst, 1)
        body.addLayout(col1)

        col2 = QVBoxLayout()
        row_size = QHBoxLayout()
        self.lbl_size = QLabel(tr("fp_size"))
        self.lbl_sval = QLabel()
        self.lbl_sval.setObjectName("value")
        self.sl_size = QSlider(Qt.Horizontal)
        self.sl_size.setRange(8, 96)
        self.sl_size.setValue(max(8, min(96, int(round(self._pt)))))
        self.lbl_sval.setText(str(self.sl_size.value()))
        self.sl_size.valueChanged.connect(self.on_size)
        row_size.addWidget(self.lbl_size)
        row_size.addStretch(1)
        row_size.addWidget(self.lbl_sval)
        col2.addLayout(row_size)
        col2.addWidget(self.sl_size)

        for key, attr, val in (("fp_bold", "tgl_bold", self._bold),
                               ("fp_italic", "tgl_italic", self._italic)):
            r = QHBoxLayout()
            lbl = QLabel(tr(key))
            tgl = ToggleSwitch()
            tgl.setChecked(val)
            tgl.toggled.connect(getattr(self, "on_" + attr[4:]))
            setattr(self, attr, tgl)
            setattr(self, "lbl_" + attr[4:], lbl)
            r.addWidget(lbl)
            r.addStretch(1)
            r.addWidget(tgl)
            col2.addLayout(r)
        col2.addStretch(1)
        body.addLayout(col2, 1)

        self.preview = QLabel()
        self.preview.setObjectName("fp_preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(76)
        self.preview.setWordWrap(True)

        rowb = QHBoxLayout()
        btn_cancel = QPushButton(tr("cancel"))
        btn_cancel.setFixedWidth(96)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton(tr("ok"))
        btn_ok.setObjectName("done")
        btn_ok.setFixedWidth(120)
        btn_ok.clicked.connect(self.accept)
        rowb.addStretch(1)
        rowb.addWidget(btn_cancel)
        rowb.addSpacing(10)
        rowb.addWidget(btn_ok)

        root.addLayout(body, 1)
        root.addWidget(self.preview)
        root.addLayout(rowb)
        self.sync_preview()
        self.apply_theme()

    def apply_theme(self):
        dark = current_dark()
        self._mica = enable_mica(self, dark)
        self.setStyleSheet(make_qss(dark, mica=self._mica))

    def showEvent(self, ev):
        super().showEvent(ev)
        self.apply_theme()

    # ---- 交互 ----
    def on_family(self, row):
        it = self.lst.item(row)
        if it:
            self._family = it.text()
            self.sync_preview()

    def on_size(self, v):
        self._pt = float(v)
        self.lbl_sval.setText(str(v))
        self.sync_preview()

    def on_bold(self, b):
        self._bold = bool(b)
        self.sync_preview()

    def on_italic(self, i):
        self._italic = bool(i)
        self.sync_preview()

    def sync_preview(self):
        f = QFont(self._family)
        f.setBold(self._bold)
        f.setItalic(self._italic)
        f.setPointSizeF(min(self._pt, 24))
        self.preview.setFont(f)
        self.preview.setText("%s　·　长风破浪会有时 AaBbCc 123" % self._family)

    def picked(self):
        return self._family, self._pt, self._bold, self._italic

    # ---- 无边框拖拽 ----
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = ev.globalPosition().toPoint() - \
                self.frameGeometry().topLeft()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        d = getattr(self, "_drag", None)
        if d is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - d)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag = None
        super().mouseReleaseEvent(ev)


class SettingsDialog(QDialog):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.cfg = win.cfg
        self.guard = False
        self._mica = False
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint |
                            Qt.WindowStaysOnTopHint)
        self.setFixedWidth(560)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶栏：仅右上角 ✕（无边框窗口拖动区 + 关闭）
        topbar = QHBoxLayout()
        topbar.setContentsMargins(0, 6, 12, 0)
        topbar.addStretch(1)
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("close")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)
        topbar.addWidget(self.btn_close)
        root.addLayout(topbar)

        # ---------- 左侧导航 + 分页 ----------
        body = QHBoxLayout()
        body.setContentsMargins(20, 6, 20, 0)
        body.setSpacing(16)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(112)
        for _i in range(3):
            self.nav.addItem(QListWidgetItem(""))
        self.nav.currentRowChanged.connect(self.on_nav)
        self.stack = QStackedWidget()
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)

        # ---------- 页1：文字内容 ----------
        card1 = QFrame()
        card1.setObjectName("card")
        v1 = QVBoxLayout(card1)
        v1.setContentsMargins(18, 16, 18, 16)
        v1.setSpacing(10)
        self.lbl_sec1 = QLabel()
        self.lbl_sec1.setObjectName("sec")
        v1.addWidget(self.lbl_sec1)
        self.txt = QTextEdit()
        self.txt.setFixedHeight(120)
        self.txt.setPlainText(truncate_lines(self.cfg["text"]))
        self.prev_text = self.txt.toPlainText()
        self.txt.textChanged.connect(self.on_text_changed)
        v1.addWidget(self.txt)
        self.stack.addWidget(self._wrap(card1))

        # ---------- 卡片2：字体样式 ----------
        card2 = QFrame()
        card2.setObjectName("card")
        v2 = QVBoxLayout(card2)
        v2.setContentsMargins(18, 16, 18, 16)
        v2.setSpacing(10)
        self.lbl_sec2 = QLabel()
        self.lbl_sec2.setObjectName("sec")
        v2.addWidget(self.lbl_sec2)

        row0 = QHBoxLayout()
        self.lbl_fontsize = QLabel()
        self.sl_font = QSlider(Qt.Horizontal)
        self.sl_font.setRange(8, 200)
        self.lbl_fval = QLabel()
        self.lbl_fval.setObjectName("value")
        self.lbl_fval.setAlignment(Qt.AlignCenter)
        row0.addWidget(self.lbl_fontsize)
        row0.addWidget(self.sl_font, 1)
        row0.addWidget(self.lbl_fval)
        self.sl_font.valueChanged.connect(self.on_changed)
        v2.addLayout(row0)

        row_btns = QHBoxLayout()
        row_btns.setSpacing(8)
        self.b_font = QPushButton()
        self.b_tc = QPushButton()
        self.b_bc = QPushButton()
        self.b_font.clicked.connect(self.pick_font)
        self.b_tc.clicked.connect(lambda: self.pick_color(True))
        self.b_bc.clicked.connect(lambda: self.pick_color(False))
        row_btns.addWidget(self.b_font)
        row_btns.addWidget(self.b_tc)
        row_btns.addWidget(self.b_bc)
        v2.addLayout(row_btns)

        row1 = QHBoxLayout()
        self.lbl_border = QLabel()
        self.sl_border = QSlider(Qt.Horizontal)
        self.sl_border.setRange(0, 100)
        self.lbl_bval = QLabel()
        self.lbl_bval.setObjectName("value")
        self.lbl_bval.setAlignment(Qt.AlignCenter)
        row1.addWidget(self.lbl_border)
        row1.addWidget(self.sl_border, 1)
        row1.addWidget(self.lbl_bval)
        self.sl_border.valueChanged.connect(self.on_changed)
        v2.addLayout(row1)

        row2 = QHBoxLayout()
        self.lbl_gap = QLabel()
        self.sl_gap = QSlider(Qt.Horizontal)
        self.sl_gap.setRange(0, 60)
        self.lbl_gval = QLabel()
        self.lbl_gval.setObjectName("value")
        self.lbl_gval.setAlignment(Qt.AlignCenter)
        row2.addWidget(self.lbl_gap)
        row2.addWidget(self.sl_gap, 1)
        row2.addWidget(self.lbl_gval)
        self.sl_gap.valueChanged.connect(self.on_changed)
        v2.addLayout(row2)

        row3 = QHBoxLayout()
        self.lbl_align = QLabel()
        self.cb_align = QComboBox()
        self.cb_align.currentIndexChanged.connect(self.on_changed)
        row3.addWidget(self.lbl_align)
        row3.addWidget(self.cb_align)
        row3.addStretch(1)
        v2.addLayout(row3)
        self.stack.addWidget(self._wrap(card2))

        # ---------- 页3：其他设置 ----------
        card3 = QFrame()
        card3.setObjectName("card")
        v3 = QVBoxLayout(card3)
        v3.setContentsMargins(18, 16, 18, 16)
        v3.setSpacing(10)
        self.lbl_sec3 = QLabel()
        self.lbl_sec3.setObjectName("sec")
        v3.addWidget(self.lbl_sec3)

        for is_lang in (True, False):
            r = QHBoxLayout()
            lbl = QLabel()
            cb = QComboBox()
            cb.setMinimumWidth(150)
            if is_lang:
                self.lbl_lang, self.cb_lang = lbl, cb
                cb.currentIndexChanged.connect(self.on_lang_changed)
            else:
                self.lbl_theme, self.cb_theme = lbl, cb
                cb.currentIndexChanged.connect(self.on_theme_changed)
            r.addWidget(lbl)
            r.addStretch(1)
            r.addWidget(cb)
            v3.addLayout(r)

        row5 = QHBoxLayout()
        self.lbl_run = QLabel()
        self.tgl_run = ToggleSwitch()
        self.tgl_run.setChecked(is_autorun())
        self.tgl_run.toggled.connect(set_autorun)
        row5.addWidget(self.lbl_run)
        row5.addStretch(1)
        row5.addWidget(self.tgl_run)
        v3.addLayout(row5)
        self.stack.addWidget(self._wrap(card3))

        root.addLayout(body, 1)

        self.btn_done = QPushButton()
        self.btn_done.setObjectName("done")
        self.btn_done.setFixedWidth(132)
        self.btn_done.setCursor(Qt.PointingHandCursor)
        self.btn_done.clicked.connect(self.close)
        footer = QHBoxLayout()
        footer.setContentsMargins(20, 12, 20, 20)
        footer.addStretch(1)
        footer.addWidget(self.btn_done)
        root.addLayout(footer)

        self.apply_qss()
        self.retranslate()
        self.apply_values()
        self.nav.setCurrentRow(0)

    def _wrap(self, card):
        """把卡片包进透明分页，供 QStackedWidget 使用"""
        page = QWidget()
        page.setObjectName("page")
        pv = QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(card)
        pv.addStretch(1)
        return page

    # ---- 导航 ----
    def on_nav(self, idx):
        self.stack.setCurrentIndex(idx)

    # ---- 无边框拖拽（按住头部/空白处拖动） ----
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = ev.globalPosition().toPoint() - \
                self.frameGeometry().topLeft()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        d = getattr(self, "_drag", None)
        if d is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - d)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag = None
        super().mouseReleaseEvent(ev)

    # ---- 主题 / 语言 ----
    def apply_qss(self):
        dark = current_dark()
        self._mica = enable_mica(self, dark)
        self.setStyleSheet(make_qss(dark, mica=self._mica))

    def showEvent(self, ev):
        super().showEvent(ev)
        self.apply_qss()   # HWND 已就位：开 Mica（含主题切换后重申）

    def apply_values(self):
        self.guard = True
        self.sl_font.setValue(max(8, min(200, int(round(self.cfg["font_pt"])))))
        self.sl_border.setValue(int(self.cfg["border_alpha"]))
        self.sl_gap.setValue(int(self.cfg["line_gap"]))
        self.cb_align.setCurrentIndex(max(0, min(2, int(self.cfg["align"]))))
        self.lbl_fval.setText(str(self.sl_font.value()))
        self.lbl_bval.setText("%d%%" % self.sl_border.value())
        self.lbl_gval.setText(str(self.sl_gap.value()))
        self.guard = False

    def retranslate(self):
        self.setWindowTitle(tr("title"))
        self.lbl_sec1.setText(tr("sec_text"))
        self.lbl_sec2.setText(tr("sec_style"))
        self.lbl_sec3.setText(tr("sec_misc"))
        self.lbl_fontsize.setText(tr("font_size"))
        self.b_font.setText(tr("font"))
        self.b_tc.setText(tr("text_color"))
        self.b_bc.setText(tr("border_color"))
        self.lbl_border.setText(tr("border_alpha"))
        self.lbl_gap.setText(tr("line_gap"))
        self.lbl_align.setText(tr("align"))
        self.lbl_lang.setText(tr("lang_label"))
        self.lbl_theme.setText(tr("theme_label"))
        self.lbl_run.setText(tr("autorun"))
        for _i, _k in enumerate(("sec_text", "sec_style", "sec_misc")):
            self.nav.item(_i).setText(tr(_k))
        self.btn_done.setText(tr("done"))
        self.cb_align.blockSignals(True)
        cur = self.cb_align.currentIndex()
        self.cb_align.clear()
        self.cb_align.addItems(tr("aligns"))
        self.cb_align.setCurrentIndex(cur if cur >= 0 else int(self.cfg["align"]))
        self.cb_align.blockSignals(False)
        self.cb_lang.blockSignals(True)
        self.cb_lang.clear()
        self.cb_lang.addItems(tr("langs"))
        self.cb_lang.setCurrentIndex(0 if S["cfg"].get("lang", "zh") == "zh" else 1)
        self.cb_lang.blockSignals(False)
        self.cb_theme.blockSignals(True)
        self.cb_theme.clear()
        self.cb_theme.addItems(tr("themes"))
        self.cb_theme.setCurrentIndex({"auto": 0, "dark": 1, "light": 2}
                                      .get(S["cfg"].get("theme", "auto"), 0))
        self.cb_theme.blockSignals(False)
        if self.win.tray:
            self.win.tray.retranslate()

    def on_lang_changed(self, idx):
        if self.guard:
            return
        self.cfg["lang"] = "zh" if idx == 0 else "en"
        save_cfg(self.cfg)
        self.retranslate()

    def on_theme_changed(self, idx):
        if self.guard:
            return
        self.cfg["theme"] = {0: "auto", 1: "dark", 2: "light"}.get(idx, "auto")
        save_cfg(self.cfg)
        self.apply_qss()

    # 跟随系统：监听系统主题设置变化
    def nativeEvent(self, eventType, message):
        try:
            if eventType == b"windows_generic_MSG":
                msg = ctypes.cast(int(message),
                                  ctypes.POINTER(MSGStruct)).contents
                if msg.message == WM_SETTINGCHANGE:
                    self.apply_qss()
        except Exception:
            pass
        return False, 0

    # ---- 数据 ----
    def on_text_changed(self):
        if self.guard:
            return
        t = self.txt.toPlainText()
        n = len(t.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
        if n > MAX_LINES:
            self.guard = True
            self.txt.setPlainText(self.prev_text)
            c = self.txt.textCursor()
            c.movePosition(c.MoveOperation.End)
            self.txt.setTextCursor(c)
            self.guard = False
            return
        self.prev_text = t
        self.on_changed()

    def on_changed(self):
        if self.guard:
            return
        cfg = self.cfg
        cfg["text"] = self.txt.toPlainText()
        cfg["font_pt"] = float(self.sl_font.value())
        cfg["border_alpha"] = self.sl_border.value()
        cfg["line_gap"] = self.sl_gap.value()
        cfg["align"] = self.cb_align.currentIndex()
        self.lbl_fval.setText(str(cfg["font_pt"]))
        self.lbl_bval.setText("%d%%" % cfg["border_alpha"])
        self.lbl_gval.setText(str(cfg["line_gap"]))
        self.win.auto_fit()  # 字号变大时窗口自动撑大，不裁字
        self.win.repaint()   # 同步强制重绘
        save_cfg(cfg)        # 实时保存
        dbg("change pt=%s color=%06X align=%s" %
            (cfg["font_pt"], cfg["text_color"], cfg["align"]))

    def pick_font(self):
        cfg = self.cfg
        dlg = FontPickerDialog(cfg["font_family"], cfg["font_pt"],
                               cfg["bold"], cfg["italic"], self)
        if dlg.exec() == QDialog.Accepted:
            fam, pt, b, i = dlg.picked()
            cfg["font_family"] = fam
            cfg["font_pt"] = float(pt)
            cfg["bold"] = b
            cfg["italic"] = i
            self.guard = True
            self.sl_font.setValue(max(8, min(200, int(round(cfg["font_pt"])))))
            self.lbl_fval.setText(str(self.sl_font.value()))
            self.guard = False
            self.win.auto_fit()
            self.win.repaint()
            save_cfg(cfg)
            dbg("font -> %s %spt" % (cfg["font_family"], cfg["font_pt"]))

    def pick_color(self, is_text):
        cfg = self.cfg
        key = "text_color" if is_text else "border_color"
        dlg = ColorPickerDialog("#%06X" % cfg[key], self,
                                tr("tc_dlg") if is_text else tr("bc_dlg"))
        if dlg.exec() == QDialog.Accepted:
            c = dlg.picked_color()
            cfg[key] = (c.red() << 16) | (c.green() << 8) | c.blue()
            self.win.repaint()
            save_cfg(cfg)
            dbg("color %s -> %06X" % (key, cfg[key]))

    def closeEvent(self, ev):
        self.on_changed()
        self.win.finish_edit()
        ev.accept()


# ================= 托盘 =================
def make_tray_icon():
    pm = QPixmap(64, 64)
    pm.fill(QColor(30, 31, 38))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    f = QFont("Microsoft YaHei", 34)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#e8eaef"))
    p.drawText(pm.rect(), Qt.AlignCenter, "念")
    p.end()
    return QIcon(pm)


class Tray(QSystemTrayIcon):
    def __init__(self, win):
        super().__init__(make_tray_icon())
        self.win = win
        self.menu = QMenu()
        self.a_edit = QAction(self.menu)
        self.a_exit = QAction(self.menu)
        self.a_edit.triggered.connect(win.start_edit)
        self.a_exit.triggered.connect(self.exit_app)
        self.menu.addAction(self.a_edit)
        self.menu.addSeparator()
        self.menu.addAction(self.a_exit)
        self.setContextMenu(self.menu)
        self.activated.connect(self.on_activated)
        self.retranslate()

    def retranslate(self):
        self.setToolTip(tr("tip"))
        self.a_edit.setText(tr("menu_edit"))
        self.a_exit.setText(tr("menu_exit"))

    def on_activated(self, reason):
        if reason in (self.Trigger, self.DoubleClick, self.MiddleClick):
            self.win.start_edit()

    def exit_app(self):
        save_cfg(self.win.cfg)
        self.hide()
        QApplication.quit()


# ================= main =================
S = {"cfg": None, "win": None, "attached_ok": False}


def main():
    selftest = "--selftest" in sys.argv
    dbg("main start selftest=%s" % selftest)

    kernel32.CreateMutexW(None, True, "ToMe_v9_SingleInstance")
    err = ctypes.get_last_error()
    dbg("mutex err=%s" % err)
    if err == 183:
        return 0

    S["cfg"] = load_cfg()
    app = QApplication(sys.argv)
    # Fluent 排版：Segoe UI Variable（Win11）+ 雅黑 UI 中文回退
    _f = QFont()
    _f.setFamilies(["Segoe UI Variable Text", "Segoe UI",
                    "Microsoft YaHei UI", "Microsoft YaHei"])
    _f.setPointSize(10)
    app.setFont(_f)
    dbg("qapp ok")
    app.setQuitOnLastWindowClosed(False)

    win = MottoWindow(S["cfg"])
    S["win"] = win
    win.show()
    app.processEvents()  # 确保 winId 已创建
    win.apply_display_mode()
    dbg("display mode done")

    tray = Tray(win)
    win.tray = tray
    tray.show()
    if not S["cfg"].get("first_run") and not selftest:
        S["cfg"]["first_run"] = True
        save_cfg(S["cfg"])
        tray.showMessage(tr("balloon_t"), tr("balloon_b"),
                         QSystemTrayIcon.Information, 5000)

    if selftest:
        log = os.path.join(APPDATA_DIR, "selftest.log")
        try:
            os.makedirs(APPDATA_DIR, exist_ok=True)
            with open(log, "w", encoding="utf-8") as f:
                f.write("hwnd=%s dark=%s lang=%s parent=%s\n" %
                        (int(win.winId()), current_dark(),
                         S["cfg"].get("lang", "zh"),
                         bool(user32.GetParent(int(win.winId())))))
        except OSError:
            pass
        QTimer.singleShot(800, app.quit)
        app.exec()
        return 0

    app.exec()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        try:
            os.makedirs(APPDATA_DIR, exist_ok=True)
            with open(os.path.join(APPDATA_DIR, "crash.log"), "a",
                      encoding="utf-8") as f:
                f.write(traceback.format_exc() + "\n")
        except OSError:
            pass
        raise
