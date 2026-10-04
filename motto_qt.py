# -*- coding: utf-8 -*-
# 念 ToMe - 桌面座右铭：贴壁纸层 + 点击穿透 + 托盘编辑
# v3: 实时渲染+即时保存 / 界面主题跟随系统 / 全中文界面+语言切换
import ctypes
import json
import os
import sys
import time
import winreg

from PySide6.QtCore import Qt, QRectF, QTimer, Signal, QPointF
from PySide6.QtGui import (QPainter, QColor, QPen, QFont, QFontMetrics, QIcon,
                           QPixmap, QAction, QLinearGradient, QFontDatabase,
                           QGuiApplication)
from PySide6.QtWidgets import (QApplication, QWidget, QDialog, QVBoxLayout,
                               QHBoxLayout, QLabel, QTextEdit, QPushButton,
                               QSlider, QComboBox, QCheckBox, QSystemTrayIcon,
                               QMenu, QFrame, QGridLayout, QListWidget,
                               QListWidgetItem, QStackedWidget, QLineEdit,
                               QMessageBox, QFileDialog, QSizePolicy)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

# ---- 单实例唤起 Event ----
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0
ACT_EVENT_NAME = "ToMe_v9_ActivateEvent"
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_wchar_p]
kernel32.CreateEventW.restype = ctypes.c_void_p
kernel32.OpenEventW.argtypes = [ctypes.c_uint32, ctypes.c_int,
                                ctypes.c_wchar_p]
kernel32.OpenEventW.restype = ctypes.c_void_p
kernel32.SetEvent.argtypes = [ctypes.c_void_p]
kernel32.SetEvent.restype = ctypes.c_int
kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
kernel32.WaitForSingleObject.restype = ctypes.c_uint32

# ---- 全屏免打扰 ----
QUNS_RUNNING_D3D_FULL_SCREEN = 3
shell32.SHQueryUserNotificationState.argtypes = [ctypes.POINTER(ctypes.c_int)]
shell32.SHQueryUserNotificationState.restype = ctypes.c_long

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
    "text_alpha": 100,       # 文字不透明度 0-100
    "shadow_on": True,       # 文字投影（保证花哨壁纸上的可读性）
    "border_color": 0xFFFFFF,
    "border_alpha": 0,        # 0=隐形 100=实线
    "line_gap": 10,
    "align": 1,               # 0左 1中 2右
    "x": 80, "y": 80, "w": 700, "h": 240,
    "first_run": False,
    "lang": "zh",             # zh / en
    "theme": "auto",          # auto / dark / light
    "fs_hide": True,          # 前台全屏（游戏/视频）时自动隐藏
    "recent_colors": [],      # 取色器最近使用的自定义色（最多 8）
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
        "title": "念 · 设置",
        "font": "字体…",
        "text_color": "文字颜色…",
        "border_color": "边框颜色…",
        "border_alpha": "边框透明度",
        "text_alpha": "文字不透明度",
        "shadow": "文字投影",
        "line_gap": "行间距 (px)",
        "align": "对齐",
        "aligns": ["左对齐", "居中", "右对齐"],
        "autorun": "开机自动启动",
        "autorun_fail_t": "开机自启设置失败",
        "autorun_fail_b": "无法写入注册表启动项，请检查系统权限后重试。",
        "fs_hide": "全屏时自动隐藏（游戏/视频）",
        "reset_pos": "重置位置和大小",
        "done": "完成",
        "ok": "确定",
        "lang_label": "界面语言",
        "theme_label": "界面主题",
        "themes": ["跟随系统", "深色", "浅色"],
        "langs": ["中文", "English"],
        "sec_text": "文字内容",
        "sec_style": "字体样式",
        "sec_misc": "其他设置",
        "sec_history": "历史记录",
        "hist_restore": "恢复到桌面",
        "hist_pin": "置顶",
        "hist_unpin": "取消置顶",
        "hist_delete": "删除",
        "hist_copy": "复制文字",
        "hist_export": "导出…",
        "hist_clear": "清空",
        "hist_empty": "还没有历史记录。\n关闭设置窗口时，文字和样式会自动存成一条。",
        "hist_tip": "选中一条，点「恢复到桌面」放回桌面（双击也行）。置顶的不会被 100 条上限淘汰。",
        "hist_applied": "✓ 已恢复到桌面，关掉这个窗口就能看到",
        "hist_applied_more": "（恢复前的状态也存成了一条历史）",
        "hist_nogeo": "无位置(旧记录)",
        "hist_clear_q": "确定清空未置顶的历史记录吗？\n置顶的记录会保留。",
        "hist_clear_t": "清空历史",
        "hist_clear_ok": "已清空未置顶的历史记录。",
        "hist_copied_t": "已复制",
        "hist_copied_b": "该条文字已复制到剪贴板。",
        "hist_restored_t": "已恢复",
        "hist_restored_b": "已恢复到所选版本；恢复前的状态也已存成一条历史。",
        "hist_export_t": "导出完成",
        "hist_export_b": "历史记录已导出到：\n%s",
        "hist_export_fail": "导出失败：%s",
        "hist_export_filter": "文本文件 (*.txt);;JSON 文件 (*.json)",
        "hist_export_name": "ToMe-编辑历史",
        "hist_pick_first": "请先在上面的列表里选一条历史。",
        "hist_pick_t": "未选择",
        "hist_count": "共 %d 条 · 置顶 %d 条",
        "font_size": "字号 (pt)",
        "tip": "念 — 桌面座右铭",
        "balloon_t": "念已就位",
        "balloon_b": "文字已贴在桌面。右键（或双击）托盘图标即可编辑。",
        "menu_edit": "编辑文字 / 位置",
        "menu_exit": "退出",
        "fp_search": "搜索字体…",
        "fp_family": "字体",
        "fp_size": "字号",
        "fp_bold": "粗体",
        "fp_italic": "斜体",
        "cancel": "取消",
        "tc_dlg": "选择文字颜色",
        "bc_dlg": "选择边框颜色",
    },
    "en": {
        "title": "ToMe · Settings",
        "font": "Font…",
        "text_color": "Text color…",
        "border_color": "Border color…",
        "border_alpha": "Border opacity",
        "text_alpha": "Text opacity",
        "shadow": "Text shadow",
        "line_gap": "Line spacing (px)",
        "align": "Align",
        "aligns": ["Left", "Center", "Right"],
        "autorun": "Start with Windows",
        "autorun_fail_t": "Could not change startup setting",
        "autorun_fail_b": "Writing the Windows startup entry failed. Check your permissions and try again.",
        "fs_hide": "Hide when a fullscreen app is active",
        "reset_pos": "Reset position & size",
        "done": "Done",
        "ok": "OK",
        "lang_label": "Language",
        "theme_label": "Theme",
        "themes": ["Follow system", "Dark", "Light"],
        "langs": ["中文", "English"],
        "sec_text": "Text",
        "sec_style": "Font style",
        "sec_misc": "General",
        "sec_history": "History",
        "hist_restore": "Restore",
        "hist_pin": "Pin",
        "hist_unpin": "Unpin",
        "hist_delete": "Delete",
        "hist_copy": "Copy text",
        "hist_export": "Export…",
        "hist_clear": "Clear",
        "hist_empty": "No history yet.\nClosing the settings window saves the current text and style as one entry.",
        "hist_tip": "Select an entry, then click \"Restore\" to put it back on the desktop (double-click works too). Pinned entries are never dropped by the 100-entry limit.",
        "hist_applied": "✓ Restored to the desktop — close this window to see it",
        "hist_applied_more": "(the previous state was saved as a new entry)",
        "hist_nogeo": "no position (legacy)",
        "hist_clear_q": "Clear all unpinned history?\nPinned entries will be kept.",
        "hist_clear_t": "Clear history",
        "hist_clear_ok": "Unpinned history cleared.",
        "hist_copied_t": "Copied",
        "hist_copied_b": "This entry's text has been copied to the clipboard.",
        "hist_restored_t": "Restored",
        "hist_restored_b": "Restored to the selected version. The previous state was saved as a new entry.",
        "hist_export_t": "Export complete",
        "hist_export_b": "History exported to:\n%s",
        "hist_export_fail": "Export failed: %s",
        "hist_export_filter": "Text file (*.txt);;JSON file (*.json)",
        "hist_export_name": "ToMe-history",
        "hist_pick_first": "Please select a history entry first.",
        "hist_pick_t": "Nothing selected",
        "hist_count": "%d entries · %d pinned",
        "font_size": "Font size (pt)",
        "tip": "ToMe — desktop motto",
        "balloon_t": "ToMe is ready",
        "balloon_b": "Text pinned to desktop. Right-click (or double-click) the tray icon to edit.",
        "menu_edit": "Edit text / position",
        "menu_exit": "Exit",
        "fp_search": "Search fonts…",
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
    # S["cfg"] 在 main() 之前为 None（例如单元测试或早期调用），
    # 此时退回中文文案，而不是抛 AttributeError。
    cfg = S.get("cfg") or {}
    return STR[cfg.get("lang", "zh")][key]


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
        tmp = CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
        os.replace(tmp, CONFIG_FILE)   # 原子替换，避免写一半损坏配置
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
RUN_VALUE = "ToMe"          # 注册表启动项名称：HKCU\...\Run\ToMe


def autorun_command():
    """开机自启要登记的命令行。
    打包成单文件 exe 后 sys.executable 就是 exe 自身；源码直跑时是
    python.exe，此时补上脚本路径，保证开发态切换自启也是真的能启动。"""
    if getattr(sys, "frozen", False):
        return '"%s"' % sys.executable
    return '"%s" "%s"' % (sys.executable, os.path.abspath(__file__))


def autorun_entry():
    """读取已登记的开机自启命令；没有登记返回 None。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            val, _ = winreg.QueryValueEx(k, RUN_VALUE)
            return val
    except OSError:
        return None


def is_autorun():
    return autorun_entry() is not None


def set_autorun(on):
    """开启/关闭开机自启。返回 True 表示注册表确实写成功（UI 据此回滚）。"""
    try:
        if on:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                    winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ,
                                  autorun_command())
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                try:
                    winreg.DeleteValue(k, RUN_VALUE)
                except FileNotFoundError:
                    pass
        dbg("autorun -> %s" % on)
        return True
    except OSError as e:
        dbg("autorun set(%s) failed: %s" % (on, e))
        return False


def sync_autorun():
    """启动时自愈：登记的那个 exe 已经不存在了，才改写为当前路径。

    为什么不是「路径不等于自己就改」：用户可能同时有安装版和便携版，
    那样谁最后启动谁就把自启项抢走，安装版的自启会莫名其妙失效
    （打包时跑一次 dist 下的 --selftest 就会触发）。
    真正需要修的场景只有「程序被移动或卸载，旧路径已经没了」。"""
    cur = autorun_entry()
    if cur is None:
        return
    registered = cur.strip().strip('"')
    if os.path.exists(registered):
        return
    if registered.lower() != autorun_command().strip('"').lower():
        dbg("autorun target missing (%s), repairing" % registered)
        set_autorun(True)


# ---------------- 编辑历史 ----------------
# 每次关闭设置窗口时，把「文字 + 外观样式」落成一条历史，可随时回滚。
# 存 %APPDATA%\ToMe\history.json，与 config.json 同目录；卸载不删。
HISTORY_FILE = os.path.join(APPDATA_DIR, "history.json")
HISTORY_MAX = 100          # 未置顶记录的条数上限（置顶的永久保留）
HISTORY_FIELDS = ("text", "font_family", "font_pt", "bold", "italic",
                  "text_color", "text_alpha", "shadow_on", "border_color",
                  "border_alpha", "line_gap", "align",
                  "x", "y", "w", "h")   # 位置尺寸一起存，恢复时挪回原处


def history_snapshot(cfg):
    """抽一份快照：文字 + 全部外观样式 + 位置尺寸。"""
    return {k: cfg.get(k, DEFAULT_CFG.get(k)) for k in HISTORY_FIELDS}


def load_history():
    """读历史；文件缺失或损坏一律当作空历史，绝不阻塞启动。"""
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict)]


def save_history(items):
    """原子写入，避免异常退出写坏历史文件。"""
    try:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        tmp = HISTORY_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
        os.replace(tmp, HISTORY_FILE)
    except OSError:
        pass


def trim_history(items):
    """按时间升序整理；只淘汰最旧的未置顶记录，置顶的永远保留。"""
    items = sorted(items, key=lambda e: e.get("ts", 0))
    pinned = [e for e in items if e.get("pinned")]
    plain = [e for e in items if not e.get("pinned")]
    if len(plain) > HISTORY_MAX:
        plain = plain[-HISTORY_MAX:]
    return sorted(pinned + plain, key=lambda e: e.get("ts", 0))


def history_display_order(items):
    """列表顺序：置顶的在前，各自按时间从新到旧。"""
    def key(e):
        return e.get("ts", 0)
    pinned = sorted([e for e in items if e.get("pinned")],
                    key=key, reverse=True)
    plain = sorted([e for e in items if not e.get("pinned")],
                   key=key, reverse=True)
    return pinned + plain


def push_history(cfg):
    """落一条历史。与最近一条完全相同则不重复记，返回是否新增。"""
    snap = history_snapshot(cfg)
    items = load_history()
    if items:
        last = max(items, key=lambda e: e.get("ts", 0))
        if all(last.get(k) == snap[k] for k in HISTORY_FIELDS):
            return False
    snap["ts"] = int(time.time())
    snap["pinned"] = False
    items.append(snap)
    save_history(trim_history(items))
    return True


def history_time_str(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts)))
    except (ValueError, OSError, TypeError):
        return "?"


def hist_style_line(e):
    """一行样式摘要：字号 / 字体 / 对齐 / 不透明度 / 粗斜 / 投影 / 边框。"""
    aligns = tr("aligns")
    a = int(e.get("align", 1) or 0)
    a = aligns[a] if 0 <= a < len(aligns) else aligns[1]
    try:
        pt = int(round(float(e.get("font_pt", 0) or 0)))
    except (TypeError, ValueError):
        pt = 0
    parts = ["%s %dpt" % (e.get("font_family") or "-", pt), a,
             "%d%%" % int(e.get("text_alpha", 100) or 0)]
    if e.get("bold"):
        parts.append(tr("fp_bold"))
    if e.get("italic"):
        parts.append(tr("fp_italic"))
    if e.get("shadow_on"):
        parts.append(tr("shadow"))
    ba = int(e.get("border_alpha", 0) or 0)
    if ba > 0:
        parts.append("%s %d%%" % (tr("border_alpha"), ba))
    # 标明这条含不含位置：旧版本的历史没记录位置，恢复时不会挪窗口，
    # 直接写在预览里，免得用户以为是坏的。
    if all(isinstance(e.get(k), (int, float)) for k in ("x", "y", "w", "h")):
        parts.append("位置 %d,%d" % (int(e["x"]), int(e["y"])))
    else:
        parts.append(tr("hist_nogeo"))
    return " · ".join(parts)


def history_export_text(items):
    """导出成人类可读的 txt。"""
    out = ["念 ToMe — 编辑历史",
           "导出时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"),
           "共 %d 条" % len(items), ""]
    for i, e in enumerate(history_display_order(items), 1):
        out.append("=" * 56)
        out.append("[%d] %s%s" % (i, history_time_str(e.get("ts", 0)),
                                  "  [置顶]" if e.get("pinned") else ""))
        out.append(hist_style_line(e))
        out.append("-" * 56)
        out.append(e.get("text") or "")
        out.append("")
    return "\n".join(out)


def system_is_dark():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return v == 0
    except OSError:
        return True


def current_dark():
    t = (S["cfg"] or {}).get("theme", "auto")
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
    QTextEdit, QComboBox, QLineEdit { background: @INPUTBG; color: @TXT;
        border: 1px solid @INPUTSTROKE; border-bottom: 2px solid @INPUTSTROKE2;
        border-radius: 4px; padding: 7px 9px; font-size: 13px;
        selection-background-color: @SELBG; selection-color: @TXT; }
    QTextEdit:focus, QComboBox:focus, QLineEdit:focus {
        border-bottom: 2px solid @ACCINT; }
    QLineEdit:disabled { color: @TXT3; }
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

    /* ---- 编辑历史 ---- */
    QListWidget#hist { background: @INPUTBG; color: @TXT;
        border: 1px solid @INPUTSTROKE; border-radius: 4px; padding: 4px;
        font-size: 12px; outline: none; }
    QListWidget#hist::item { padding: 5px 8px; border-radius: 4px;
        color: @TXT2; min-height: 22px; }
    QListWidget#hist::item:hover { background: @SUBTLE; }
    QListWidget#hist::item:selected { background: @SELBG; color: @TXT; }
    QLabel#histprev { background: @INPUTBG; border: 1px solid @INPUTSTROKE;
        border-radius: 4px; color: @TXT; font-size: 12px; padding: 8px; }
    /* 「恢复到桌面」是这一页的主操作，给个 accent 描边让它跳出来 */
    QPushButton#hist_primary { border: 1px solid @ACCINT; color: @ACCINT;
        font-weight: 600; }
    QPushButton#hist_primary:hover { background: @SELBG; border-color: @ACCINT; }
    QPushButton#hist_primary:disabled { border-color: @BTNSTROKE; color: @TXT3; }

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
        self.user_hidden = False   # 用户通过托盘手动隐藏
        self.auto_hidden = False   # 全屏免打扰自动隐藏

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(int(cfg["x"]), int(cfg["y"]),
                         int(cfg["w"]), int(cfg["h"]))
        self.setMinimumSize(120, 60)
        # 恢复历史时置 True：让 auto_fit 别重算尺寸、更别挪窗口，
        # 否则刚设好的历史几何会被它覆盖掉（位置就是这么丢的）。
        self.suppress_autofit = False

        # 心跳自愈：每 20 秒确认窗口仍在壁纸层，丢失则重新挂（Explorer 重启等）
        self._hb = QTimer(self)
        self._hb.setInterval(20000)
        self._hb.timeout.connect(self.check_attach)

    def check_attach(self):
        if self.editing or not self.isVisible() or self.user_hidden \
                or self.auto_hidden:
            return
        # 周期性重申：沉底 + 穿透（防止其他程序扰动 z 序或样式漂移）
        attach_wallpaper(int(self.winId()))
        hwnd = int(self.winId())
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        if not (ex & WS_EX_TRANSPARENT):
            ex |= WS_EX_TRANSPARENT
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
        self.ensure_on_screen()

    # ---- 显隐（手动隐藏 / 全屏自动隐藏）----
    def toggle_visibility(self):
        if self.user_hidden or self.auto_hidden:
            self.show_text()
        else:
            self.hide_text(user=True)

    def hide_text(self, user=False, auto=False):
        if self.editing:
            return
        if user:
            self.user_hidden = True
        if auto:
            self.auto_hidden = True
        self.hide()

    def show_text(self, auto=False):
        if auto:
            self.auto_hidden = False
        else:
            self.user_hidden = False
            self.auto_hidden = False
        if self.user_hidden or self.auto_hidden:
            return
        self.show()
        self.repaint()
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
        """多屏纠偏：窗口与任一屏幕可用区域相交不足 60px 则拉回主屏。"""
        g = self.frameGeometry()
        for s in QGuiApplication.screens():
            ag = s.availableGeometry()
            inter = g.intersected(ag)
            if inter.width() >= 60 and inter.height() >= 60:
                return  # 已在某个屏幕内
        ag = QApplication.primaryScreen().availableGeometry()
        self.move(ag.x() + 80, ag.y() + 80)
        if self.width() > ag.width():
            self.resize(ag.width(), self.height())
        if self.height() > ag.height():
            self.resize(self.width(), ag.height())

    def auto_fit(self):
        """字号/行距/字体变化后，窗口贴合文字尺寸（可扩可缩，不裁字）。"""
        if not self.editing:
            return
        if self.suppress_autofit:
            return   # 正在恢复历史：几何以历史记录为准，不许重算
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
        # 以窗口当前所在屏幕为上限（多屏分辨率/缩放不同）
        screen = QApplication.screenAt(self.frameGeometry().center()) \
            or QApplication.primaryScreen()
        ag = screen.availableGeometry()
        need_w = max(120, min(need_w, ag.width()))
        need_h = max(60, min(need_h, ag.height()))
        # 拖拽缩放中不回缩（避免与手动操作打架）
        if not self.resizing:
            self.resize(need_w, need_h)
        # 注意：这里**故意不移动窗口**。曾经有过「底部出屏就整体上移」，
        # 结果是用户摆好的位置会被程序自己挪走，而且恢复历史时刚设好的
        # 位置也会被覆盖。位置归用户管，程序只负责贴合尺寸。

    def start_edit(self):
        if self.editing:
            if self.dlg:
                self.dlg.raise_()
                self.dlg.activateWindow()
            return
        # 被（手动/全屏）隐藏时，进入编辑先恢复显示
        if self.user_hidden or self.auto_hidden:
            self.user_hidden = self.auto_hidden = False
            self.show()
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
        ta = max(0, min(100, int(cfg.get("text_alpha", 100)))) * 255 // 100
        base = QColor((cfg["text_color"] >> 16) & 0xFF,
                      (cfg["text_color"] >> 8) & 0xFF,
                      cfg["text_color"] & 0xFF, ta)
        flags = align | Qt.AlignVCenter | Qt.TextSingleLine
        y = PAD
        for i, line in enumerate(lines):
            if i >= MAX_LINES:
                break
            rect = QRectF(PAD, y, W - 2 * PAD, fm.height())
            if line:
                # 1) 柔影：8 方向半透明黑字，保证花哨壁纸上可读
                if cfg.get("shadow_on", True) and ta > 0:
                    p.setPen(QColor(0, 0, 0, int(ta * 0.5)))
                    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2),
                                   (-1.4, -1.4), (1.4, -1.4),
                                   (-1.4, 1.4), (1.4, 1.4)):
                        p.drawText(rect.translated(dx, dy), flags, line)
                # 2) 正文
                p.setPen(base)
                p.drawText(rect, flags, line)
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
            dbg("drag/resize saved -> x=%d y=%d %dx%d"
                % (self.x(), self.y(), self.width(), self.height()))
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

    def hitButton(self, pos):
        """整个 40x20 轨道都可点（默认只命中左上角 ~16px 复选框指示区）"""
        return self.rect().contains(pos)

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
    """现代取色器：SV 面板 + 色相条 + HEX 手输 + 最近色 + 预设色板"""
    def __init__(self, initial, recent, parent, title):
        super().__init__(parent)
        self._mica = False
        self._recent = list(recent or [])[:8]
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
        self.edt_hex = QLineEdit()
        self.edt_hex.setFixedWidth(108)
        self.edt_hex.setMaxLength(7)
        self.edt_hex.editingFinished.connect(self.on_hex_edited)
        rowp.addWidget(self.edt_hex)
        rowp.addStretch(1)
        v0.addLayout(rowp)

        # 最近使用的自定义色（可空）
        self.recent_grid = QGridLayout()
        self.recent_grid.setSpacing(6)
        self.recent_grid.setColumnStretch(8, 1)   # 不足 8 个时左对齐
        v0.addLayout(self.recent_grid)
        self.build_recent()

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

    def build_recent(self):
        while self.recent_grid.count():
            it = self.recent_grid.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        if not self._recent:
            return
        edge = ("rgba(255,255,255,0.22)" if current_dark()
                else "rgba(0,0,0,0.18)")
        hov = "#4cc2ff" if current_dark() else "#0067c0"
        for i, hexc in enumerate(self._recent[:8]):
            b = QPushButton()
            b.setFixedSize(30, 30)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton { background: %s; border: 1px solid %s;"
                " border-radius: 4px; min-width: 30px; max-width: 30px; }"
                "QPushButton:hover { border: 2px solid %s; }"
                % (hexc, edge, hov))
            b.clicked.connect(lambda _=False, hx=hexc: self.set_hex(hx))
            self.recent_grid.addWidget(b, i // 8, i % 8)

    def on_hex_edited(self):
        t = self.edt_hex.text().strip().lstrip("#")
        if len(t) == 6:
            c = QColor("#" + t)
            if c.isValid():
                self.set_hex("#" + t.upper())
                return
        self.sync_ui()   # 非法输入：还原为当前色

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
        self.edt_hex.setText(self._color.name().upper())

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
        col1.setSpacing(8)
        self.lbl_family = QLabel(tr("fp_family"))
        self.edt_search = QLineEdit()
        self.edt_search.setPlaceholderText(tr("fp_search"))
        self.edt_search.setClearButtonEnabled(True)
        self.edt_search.textChanged.connect(self.populate_fonts)
        self.lst = QListWidget()
        self.lst.setObjectName("fp_list")
        self.lst.setFixedWidth(216)
        self.lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._fams = sorted(QFontDatabase().families(), key=str.lower)
        self._cur_family = family
        self.populate_fonts("")
        self.lst.currentRowChanged.connect(self.on_family)
        col1.addWidget(self.lbl_family)
        col1.addWidget(self.edt_search)
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
    def populate_fonts(self, text):
        kw = text.strip().lower()
        self.lst.blockSignals(True)
        self.lst.clear()
        cur = -1
        for f in self._fams:
            if kw and kw not in f.lower():
                continue
            it = QListWidgetItem(f)
            it.setFont(QFont(f, 10))   # 每个字体名用它自己渲染
            self.lst.addItem(it)
            if f == self._cur_family:
                cur = self.lst.count() - 1
        if cur >= 0:
            self.lst.setCurrentRow(cur)
        self.lst.blockSignals(False)

    def on_family(self, row):
        it = self.lst.item(row)
        if it:
            self._family = it.text()
            self._cur_family = self._family
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
        for _i in range(4):
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
        self.b_tc.clicked.connect(lambda: self.pick_color_for("text_color", "tc_dlg"))
        self.b_bc.clicked.connect(lambda: self.pick_color_for("border_color", "bc_dlg"))
        row_btns.addWidget(self.b_font)
        row_btns.addWidget(self.b_tc)
        row_btns.addWidget(self.b_bc)
        v2.addLayout(row_btns)

        row_alpha = QHBoxLayout()
        self.lbl_alpha = QLabel()
        self.sl_alpha = QSlider(Qt.Horizontal)
        self.sl_alpha.setRange(10, 100)
        self.lbl_aval = QLabel()
        self.lbl_aval.setObjectName("value")
        self.lbl_aval.setAlignment(Qt.AlignCenter)
        row_alpha.addWidget(self.lbl_alpha)
        row_alpha.addWidget(self.sl_alpha, 1)
        row_alpha.addWidget(self.lbl_aval)
        self.sl_alpha.valueChanged.connect(self.on_changed)
        v2.addLayout(row_alpha)

        row_sh = QHBoxLayout()
        self.lbl_shadow = QLabel()
        self.tgl_shadow = ToggleSwitch()
        self.tgl_shadow.toggled.connect(self.on_changed)
        row_sh.addWidget(self.lbl_shadow)
        row_sh.addStretch(1)
        row_sh.addWidget(self.tgl_shadow)
        v2.addLayout(row_sh)

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
        self.tgl_run.toggled.connect(self.on_autorun_toggled)
        row5.addWidget(self.lbl_run)
        row5.addStretch(1)
        row5.addWidget(self.tgl_run)
        v3.addLayout(row5)

        row6 = QHBoxLayout()
        self.lbl_fs = QLabel()
        self.tgl_fs = ToggleSwitch()
        self.tgl_fs.toggled.connect(self.on_fs_toggled)
        row6.addWidget(self.lbl_fs)
        row6.addStretch(1)
        row6.addWidget(self.tgl_fs)
        v3.addLayout(row6)

        v3.addSpacing(4)
        row7 = QHBoxLayout()
        self.btn_reset = QPushButton()
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self.reset_position)
        row7.addWidget(self.btn_reset)
        row7.addStretch(1)
        v3.addLayout(row7)
        self.stack.addWidget(self._wrap(card3))

        # ---------- 页4：编辑历史 ----------
        card4 = QFrame()
        card4.setObjectName("card")
        v4 = QVBoxLayout(card4)
        v4.setContentsMargins(18, 16, 18, 16)
        v4.setSpacing(8)
        self.lbl_sec4 = QLabel()
        self.lbl_sec4.setObjectName("sec")
        v4.addWidget(self.lbl_sec4)

        self.lbl_hist_tip = QLabel()
        self.lbl_hist_tip.setWordWrap(True)
        v4.addWidget(self.lbl_hist_tip)

        self.hist = load_history()          # 内存里的历史副本
        self.hist_view = []                 # 当前列表的展示顺序

        self.lst_hist = QListWidget()
        self.lst_hist.setObjectName("hist")
        self.lst_hist.setFixedHeight(146)
        self.lst_hist.currentRowChanged.connect(self.on_hist_select)
        self.lst_hist.itemDoubleClicked.connect(self.on_hist_double)
        v4.addWidget(self.lst_hist)

        self.lbl_hist_prev = QLabel()
        self.lbl_hist_prev.setObjectName("histprev")
        self.lbl_hist_prev.setFixedHeight(64)
        self.lbl_hist_prev.setWordWrap(True)
        self.lbl_hist_prev.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        v4.addWidget(self.lbl_hist_prev)

        # 六个按钮排成 3×2 网格，列宽均分。
        # 踩过的坑：先前按最长文案给固定宽度 99px，但这一页可用宽度只有
        # ~356px（对话框 560 − 导航 112 − 两侧内边距），一行塞 4 个要 414px，
        # 直接横向挤到一起。网格均分列宽既保证等宽，又不会溢出，中英文都稳。
        self.b_hist_restore = QPushButton()
        self.b_hist_restore.setObjectName("hist_primary")
        self.b_hist_pin = QPushButton()
        self.b_hist_del = QPushButton()
        self.b_hist_copy = QPushButton()
        self.b_hist_export = QPushButton()
        self.b_hist_clear = QPushButton()
        gb = QGridLayout()
        gb.setSpacing(6)
        for _r, _row in enumerate((
                (self.b_hist_restore, self.b_hist_pin, self.b_hist_del),
                (self.b_hist_copy, self.b_hist_export, self.b_hist_clear))):
            for _c, _b in enumerate(_row):
                _b.setCursor(Qt.PointingHandCursor)
                _b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                gb.addWidget(_b, _r, _c)
        for _c in range(3):
            gb.setColumnStretch(_c, 1)
        self.b_hist_restore.clicked.connect(self.hist_restore)
        self.b_hist_pin.clicked.connect(self.hist_toggle_pin)
        self.b_hist_del.clicked.connect(self.hist_delete)
        self.b_hist_copy.clicked.connect(self.hist_copy)
        self.b_hist_export.clicked.connect(self.hist_export)
        self.b_hist_clear.clicked.connect(self.hist_clear)
        v4.addLayout(gb)

        self.stack.addWidget(self._wrap(card4))

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

        # 固定整体高度：按最高一页计算，避免切页时窗口跳动
        page_h = max(self.stack.widget(i).sizeHint().height()
                     for i in range(self.stack.count()))
        self.setFixedHeight(6 + 32 + 6 + page_h + 12 + 36 + 20)

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
        self.sl_alpha.setValue(max(10, min(100, int(self.cfg.get("text_alpha", 100)))))
        self.tgl_shadow.setChecked(bool(self.cfg.get("shadow_on", True)))
        self.tgl_fs.setChecked(bool(self.cfg.get("fs_hide", True)))
        self.cb_align.setCurrentIndex(max(0, min(2, int(self.cfg["align"]))))
        self.lbl_fval.setText(str(self.sl_font.value()))
        self.lbl_bval.setText("%d%%" % self.sl_border.value())
        self.lbl_gval.setText(str(self.sl_gap.value()))
        self.lbl_aval.setText("%d%%" % self.sl_alpha.value())
        self.guard = False
        self.sync_enabled()

    def sync_enabled(self):
        """边框透明度 0 → 禁用边框色按钮"""
        self.b_bc.setEnabled(self.sl_border.value() > 0)

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
        self.lbl_alpha.setText(tr("text_alpha"))
        self.lbl_shadow.setText(tr("shadow"))
        self.lbl_gap.setText(tr("line_gap"))
        self.lbl_align.setText(tr("align"))
        self.lbl_lang.setText(tr("lang_label"))
        self.lbl_theme.setText(tr("theme_label"))
        self.lbl_run.setText(tr("autorun"))
        self.lbl_fs.setText(tr("fs_hide"))
        self.btn_reset.setText(tr("reset_pos"))
        # ---- 编辑历史页 ----
        self.lbl_sec4.setText(tr("sec_history"))
        self.lbl_hist_tip.setText(tr("hist_tip"))
        self.b_hist_restore.setText(tr("hist_restore"))
        self.b_hist_del.setText(tr("hist_delete"))
        self.b_hist_copy.setText(tr("hist_copy"))
        self.b_hist_export.setText(tr("hist_export"))
        self.b_hist_clear.setText(tr("hist_clear"))
        self.rebuild_hist()
        for _i, _k in enumerate(("sec_text", "sec_style", "sec_misc",
                                 "sec_history")):
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

    def on_autorun_toggled(self, on):
        """开机自启：注册表写失败时把开关拨回原位并提示，不让界面说谎。"""
        if self.guard:
            return
        if set_autorun(on):
            return
        self.guard = True
        self.tgl_run.setChecked(not on)
        self.guard = False
        if self.win.tray:
            self.win.tray.showMessage(tr("autorun_fail_t"),
                                      tr("autorun_fail_b"),
                                      QSystemTrayIcon.Warning, 5000)

    def on_fs_toggled(self, on):
        if self.guard:
            return
        self.cfg["fs_hide"] = bool(on)
        save_cfg(self.cfg)
        if not on and self.win.auto_hidden:
            self.win.show_text(auto=True)

    def reset_position(self):
        self.win.setGeometry(80, 80, 700, 240)
        self.cfg.update({"x": 80, "y": 80, "w": 700, "h": 240})
        self.win.repaint()
        save_cfg(self.cfg)
        dbg("position reset")

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
        cfg["text_alpha"] = self.sl_alpha.value()
        cfg["shadow_on"] = self.tgl_shadow.isChecked()
        cfg["align"] = self.cb_align.currentIndex()
        self.lbl_fval.setText(str(int(round(cfg["font_pt"]))))
        self.lbl_bval.setText("%d%%" % cfg["border_alpha"])
        self.lbl_gval.setText(str(cfg["line_gap"]))
        self.lbl_aval.setText("%d%%" % cfg["text_alpha"])
        self.sync_enabled()
        self.win.auto_fit()  # 字号变化时窗口自动贴合，不裁字
        self.win.repaint()   # 同步强制重绘
        save_cfg(cfg)        # 实时保存
        dbg("change pt=%s alpha=%s shadow=%s align=%s" %
            (cfg["font_pt"], cfg["text_alpha"], cfg["shadow_on"],
             cfg["align"]))

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

    def pick_color_for(self, key, title_key):
        cfg = self.cfg
        recent = list(cfg.get("recent_colors", []))
        dlg = ColorPickerDialog("#%06X" % cfg[key], recent, self, tr(title_key))
        if dlg.exec() == QDialog.Accepted:
            c = dlg.picked_color()
            hexc = c.name().upper()
            cfg[key] = (c.red() << 16) | (c.green() << 8) | c.blue()
            # 最近色：去重置顶，最多 8 个（预设色不入列）
            recent = [x for x in recent if x.upper() != hexc]
            recent.insert(0, hexc)
            cfg["recent_colors"] = recent[:8]
            self.sync_enabled()
            self.win.repaint()
            save_cfg(cfg)
            dbg("color %s -> %06X" % (key, cfg[key]))

    # ---- 编辑历史 ----
    def hist_item(self, row=None):
        """取列表里选中的那条历史（dict 或 None）。"""
        if row is None:
            row = self.lst_hist.currentRow()
        if row is None or row < 0 or row >= len(self.hist_view):
            return None
        return self.hist_view[row]

    def rebuild_hist(self, keep_ts=None):
        """重建列表：置顶在前，各自按时间从新到旧。"""
        self.hist_view = history_display_order(self.hist)
        self.lst_hist.blockSignals(True)
        self.lst_hist.clear()
        for e in self.hist_view:
            when = history_time_str(e.get("ts", 0))
            first = (e.get("text") or "").strip().split("\n")[0][:14]
            if not first:
                first = "(空)"
            mark = "📌 " if e.get("pinned") else ""
            # 位置直接显示在行上：很多条历史文字完全一样，只靠文字根本分不清
            # 哪条是「上面那版」哪条是「下面那版」，只能靠它来挑。
            if all(isinstance(e.get(k), (int, float))
                   for k in ("x", "y", "w", "h")):
                pos = "y%d" % int(e["y"])
            else:
                pos = tr("hist_nogeo")
            it = QListWidgetItem("%s%s  %s  %s" % (mark, when, pos, first))
            f = it.font()
            f.setBold(bool(e.get("pinned")))
            it.setFont(f)
            it.setToolTip(hist_style_line(e))
            self.lst_hist.addItem(it)
        self.lst_hist.blockSignals(False)

        want = 0 if self.hist_view else -1
        if keep_ts is not None:
            for i, e in enumerate(self.hist_view):
                if e.get("ts") == keep_ts:
                    want = i
                    break
        self.lst_hist.setCurrentRow(want)
        self.on_hist_select(self.lst_hist.currentRow())

    def on_hist_select(self, row):
        # 只要换了选中项，就把上次「已恢复」的提示收回，避免误导
        self.lbl_hist_tip.setText(tr("hist_tip"))
        e = self.hist_item(row)
        has = e is not None
        for b in (self.b_hist_restore, self.b_hist_pin,
                  self.b_hist_del, self.b_hist_copy):
            b.setEnabled(has)
        if not has:
            self.b_hist_pin.setText(tr("hist_pin"))
            self.lbl_hist_prev.setText(
                tr("hist_empty") if not self.hist_view else tr("hist_pick_first"))
            return
        self.b_hist_pin.setText(tr("hist_unpin") if e.get("pinned")
                                else tr("hist_pin"))
        txt = truncate_lines(e.get("text") or "") or "(空)"
        self.lbl_hist_prev.setText("%s\n%s" % (txt, hist_style_line(e)))

    def on_hist_double(self, _item):
        """双击一条历史 = 恢复到桌面（比去点按钮顺手）。"""
        self.hist_restore()

    def hist_write(self):
        """内存 → 磁盘（顺带做上限淘汰）。"""
        self.hist = trim_history(self.hist)
        save_history(self.hist)

    def hist_restore(self):
        e = self.hist_item()
        if e is None:
            return
        cfg = self.cfg
        push_history(cfg)              # 先把恢复前的状态存一条，来回切换不丢内容
        self.guard = True
        for k in HISTORY_FIELDS:
            if k in e:
                cfg[k] = e[k]
        cfg["text"] = e.get("text", cfg.get("text", ""))
        self.txt.setPlainText(truncate_lines(cfg["text"]))
        self.prev_text = self.txt.toPlainText()
        self.guard = False
        # 位置尺寸一起还原（旧版本的历史没有 x/y/w/h，那就保持当前位置不动）。
        # 关键：整个恢复过程必须屏蔽 auto_fit —— 它会按文字重算尺寸，
        # 并且曾经会在底部出屏时 move() 窗口，把刚设好的历史位置冲掉。
        # 之前「文字/字体变了但位置没变」就是被它覆盖的。
        geo = [e.get(k) for k in ("x", "y", "w", "h")]
        has_geo = all(isinstance(v, (int, float)) for v in geo)
        self.win.suppress_autofit = has_geo
        try:
            if has_geo:
                self.win.setGeometry(int(geo[0]), int(geo[1]),
                                     int(geo[2]), int(geo[3]))
                self.win.ensure_on_screen()
                dbg("hist restore geometry -> %s" % (geo,))
            self.apply_values()        # 滑杆/开关/对齐同步到恢复后的值
            self.on_changed()          # 落盘 + 桌面重绘
        finally:
            self.win.suppress_autofit = False
        save_cfg(cfg)                  # 以实际窗口几何为准再落一次盘
        self.hist = load_history()
        self.rebuild_hist(keep_ts=e.get("ts"))
        # 给一个看得见的确认：设置窗挡着桌面，不提示的话用户以为没生效
        self.lbl_hist_tip.setText(tr("hist_applied"))
        if self.win.tray:
            self.win.tray.showMessage(tr("hist_restored_t"),
                                      tr("hist_restored_b"),
                                      QSystemTrayIcon.Information, 4000)

    def hist_toggle_pin(self):
        e = self.hist_item()
        if e is None:
            return
        e["pinned"] = not e.get("pinned")
        self.hist_write()
        self.rebuild_hist(keep_ts=e.get("ts"))

    def hist_delete(self):
        e = self.hist_item()
        if e is None:
            return
        ts = e.get("ts")
        self.hist = [x for x in self.hist if x.get("ts") != ts]
        self.hist_write()
        self.rebuild_hist()

    def hist_copy(self):
        e = self.hist_item()
        if e is None:
            return
        QApplication.clipboard().setText(e.get("text") or "")
        if self.win.tray:
            self.win.tray.showMessage(tr("hist_copied_t"), tr("hist_copied_b"),
                                      QSystemTrayIcon.Information, 3000)

    def hist_clear(self):
        if QMessageBox.question(self, tr("hist_clear_t"),
                                tr("hist_clear_q")) != QMessageBox.Yes:
            return
        self.hist = [x for x in self.hist if x.get("pinned")]
        self.hist_write()
        self.rebuild_hist()
        if self.win.tray:
            self.win.tray.showMessage(tr("hist_clear_t"), tr("hist_clear_ok"),
                                      QSystemTrayIcon.Information, 3000)

    def hist_export(self):
        if not self.hist:
            QMessageBox.information(self, tr("hist_export_t"),
                                    tr("hist_pick_first"))
            return
        default = "%s-%s" % (tr("hist_export_name"), time.strftime("%Y%m%d"))
        path, _sel = QFileDialog.getSaveFileName(
            self, tr("hist_export"),
            os.path.join(os.path.expanduser("~"), "Desktop", default),
            tr("hist_export_filter"))
        if not path:
            return
        try:
            if path.lower().endswith(".json"):
                payload = {
                    "app": "ToMe",
                    "format": 1,
                    "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "count": len(self.hist),
                    "entries": history_display_order(self.hist),
                }
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(history_export_text(self.hist))
        except OSError as ex:
            QMessageBox.warning(self, tr("hist_export_t"),
                                tr("hist_export_fail") % ex)
            return
        QMessageBox.information(self, tr("hist_export_t"),
                                tr("hist_export_b") % path)

    def closeEvent(self, ev):
        self.on_changed()
        push_history(self.cfg)         # 关闭设置窗口 = 一次编辑，落一条历史
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
        # 左键单击=切换显隐；用短延时判定，给双击（进编辑）让路
        self._left_t = QTimer(self)
        self._left_t.setSingleShot(True)
        self._left_t.setInterval(280)
        self._left_t.timeout.connect(win.toggle_visibility)
        self.retranslate()

    def retranslate(self):
        self.setToolTip(tr("tip"))
        self.a_edit.setText(tr("menu_edit"))
        self.a_exit.setText(tr("menu_exit"))

    def on_activated(self, reason):
        if reason == self.DoubleClick:
            self._left_t.stop()       # 取消左键的单击动作
            self.win.start_edit()
        elif reason == self.Trigger:
            # 延时区分单击与双击：双击会在延时内到来
            self._left_t.start()
        elif reason == self.MiddleClick:
            self.win.toggle_visibility()

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
        # 第二实例：通知已运行实例进入编辑后退出（找不到事件则静默退出兜底）
        ev = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, ACT_EVENT_NAME)
        if ev:
            kernel32.SetEvent(ev)
        return 0

    act_event = kernel32.CreateEventW(None, False, False, ACT_EVENT_NAME)

    S["cfg"] = load_cfg()
    sync_autorun()   # 已开机自启但 exe 路径变了（重装/移动）→ 自动改写
    app = QApplication(sys.argv)
    # Fluent 排版：Segoe UI Variable（Win11）+ 雅黑 UI 中文回退
    _f = QFont()
    _f.setFamilies(["Segoe UI Variable Text", "Segoe UI",
                    "Microsoft YaHei UI", "Microsoft YaHei"])
    _f.setPointSize(10)
    app.setFont(_f)
    app.setWindowIcon(make_tray_icon())
    dbg("qapp ok")
    app.setQuitOnLastWindowClosed(False)

    win = MottoWindow(S["cfg"])
    S["win"] = win
    win.show()
    app.processEvents()  # 确保 winId 已创建
    win.apply_display_mode()
    win.ensure_on_screen()
    dbg("display mode done")

    tray = Tray(win)
    win.tray = tray
    tray.show()
    if not S["cfg"].get("first_run") and not selftest:
        S["cfg"]["first_run"] = True
        save_cfg(S["cfg"])
        tray.showMessage(tr("balloon_t"), tr("balloon_b"),
                         QSystemTrayIcon.Information, 5000)

    # 第二实例唤起：1s 轮询命名 Event（避免引入 QtWinExtras）
    def poll_activate():
        if act_event and \
                kernel32.WaitForSingleObject(act_event, 0) == WAIT_OBJECT_0:
            dbg("activate event received")
            win.start_edit()

    t_act = QTimer()
    t_act.setInterval(1000)
    t_act.timeout.connect(poll_activate)
    t_act.start()

    # 全屏免打扰：5s 查询前台是否 D3D 全屏
    def poll_fullscreen():
        if win.editing or not S["cfg"].get("fs_hide", True):
            if win.auto_hidden and not win.user_hidden:
                win.show_text(auto=True)
            return
        st = ctypes.c_int(0)
        try:
            hr = shell32.SHQueryUserNotificationState(ctypes.byref(st))
        except OSError:
            return
        if hr != 0:
            return
        if st.value == QUNS_RUNNING_D3D_FULL_SCREEN:
            if win.isVisible() and not win.user_hidden:
                dbg("fullscreen detected -> hide")
                win.hide_text(auto=True)
        elif win.auto_hidden and not win.user_hidden:
            dbg("fullscreen ended -> show")
            win.show_text(auto=True)

    t_fs = QTimer()
    t_fs.setInterval(5000)
    t_fs.timeout.connect(poll_fullscreen)
    t_fs.start()

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
