# -*- coding: utf-8 -*-
"""开关修复验证：QTest 模拟点击 + OS 真实输入，覆盖轨道多个位置"""
import sys, time, ctypes
import motto_qt as M
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QPoint

app = QApplication(sys.argv)
user32 = ctypes.windll.user32


def pump(ms=200):
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


# 1) 裸开关多位置点击
t = M.ToggleSwitch()
t.setChecked(True)
t.show()
app.processEvents()
for x, y in ((5, 5), (20, 10), (35, 15), (39, 19), (2, 18)):
    before = t.isChecked()
    QTest.mouseClick(t, Qt.LeftButton, pos=QPoint(x, y))
    app.processEvents()
    ok = t.isChecked() != before
    print("bare click(%d,%d): %s" % (x, y, "FLIP" if ok else "NO-FLIP"))
    assert ok, "位置 (%d,%d) 点击无效" % (x, y)
    QTest.mouseClick(t, Qt.LeftButton, pos=QPoint(x, y))
    app.processEvents()

# 2) OS 真实输入点击（和用户手点完全同路径）
t.setChecked(False)
g = t.mapToGlobal(QPoint(t.width() // 2, t.height() // 2))
user32.SetCursorPos(int(g.x()), int(g.y()))
pump(150)
user32.mouse_event(2, 0, 0, 0, 0)
time.sleep(0.05)
user32.mouse_event(4, 0, 0, 0, 0)
pump(400)
print("real OS click center: %s" % ("FLIP" if t.isChecked() else "NO-FLIP"))
assert t.isChecked(), "真实输入点击无效"
t.close()

# 3) 完整 App 内三个开关逐一验证
M.S["cfg"] = M.load_cfg()
win = M.MottoWindow(M.S["cfg"])
win.show()
app.processEvents()
win.start_edit()
dlg = win.dlg
app.processEvents()


def click_center(w):
    QTest.mouseClick(w, Qt.LeftButton,
                     pos=QPoint(w.width() // 2, w.height() // 2))
    pump()


def click_switch(w, name, cfgkey):
    before = w.isChecked()
    click_center(w)
    after = w.isChecked()
    cfgv = bool(M.S["cfg"].get(cfgkey))
    print("%s: %s -> %s (cfg=%s) %s" %
          (name, before, after, cfgv,
           "OK" if (before != after and cfgv == after) else "FAIL"))
    assert before != after and cfgv == after
    click_center(w)


dlg.nav.setCurrentRow(1)
pump()
click_switch(dlg.tgl_shadow, "SHADOW", "shadow_on")

dlg.nav.setCurrentRow(2)
pump()
click_switch(dlg.tgl_fs, "FS_HIDE", "fs_hide")

r_before = dlg.tgl_run.isChecked()
click_center(dlg.tgl_run)
pump(600)
print("AUTORUN: %s -> %s (registry=%s)" %
      (r_before, dlg.tgl_run.isChecked(), M.is_autorun()))
assert dlg.tgl_run.isChecked() != r_before
assert M.is_autorun() == dlg.tgl_run.isChecked()
click_center(dlg.tgl_run)
pump(600)
assert M.is_autorun() == r_before

win.finish_edit()
pump()
print("SWITCH_TEST_ALL_OK")
