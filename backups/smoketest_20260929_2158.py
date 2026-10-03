# -*- coding: utf-8 -*-
import sys, os, time
import motto_qt as M
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
M.S["cfg"] = M.load_cfg()
win = M.MottoWindow(M.S["cfg"])
win.show()
app.processEvents()
win.apply_display_mode()


def pump(ms=400, step=40):
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(step / 1000.0)


def grab(widget, name, margin=60):
    """抓真实屏幕（Mica 是 DWM 合成层，widget.grab() 抓不到）"""
    pump(500)
    g = widget.frameGeometry()
    app.primaryScreen().grabWindow(
        0, max(0, g.x() - margin), max(0, g.y() - margin),
        g.width() + margin * 2, g.height() + margin * 2).save(name)


def shot_settings(theme, name):
    M.S["cfg"]["theme"] = theme
    dlg = M.SettingsDialog(win)
    dlg.show()
    pump()
    for row in (0, 1, 2):
        dlg.nav.setCurrentRow(row)
        pump(80)
    dlg.nav.setCurrentRow(1)
    pump(200)
    grab(dlg, name)
    dlg.close()
    pump(100)


shot_settings("light", "shot_settings.png")
shot_settings("dark", "shot_settings_dark.png")

fp = M.FontPickerDialog("Microsoft YaHei", 32, False, False, win)
fp.show()
pump()
fp.lst.setCurrentRow(3)
pump(200)
grab(fp, "shot_font.png", 30)
fp.close()

cp = M.ColorPickerDialog("#4F8CFF", win, "test")
cp.show()
pump(400)
grab(cp, "shot_picker.png", 30)
cp.close()

win.finish_edit()
print("SMOKE_OK mica_build:", M.win_build())
