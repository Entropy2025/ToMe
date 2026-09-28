# -*- coding: utf-8 -*-
import sys, os
import motto_qt as M
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
M.S["cfg"] = M.load_cfg()
win = M.MottoWindow(M.S["cfg"])
win.show()
app.processEvents()
win.apply_display_mode()

dlg = M.SettingsDialog(win)
dlg.show()
app.processEvents()
for row in (0, 1, 2):
    dlg.nav.setCurrentRow(row)
    app.processEvents()
dlg.nav.setCurrentRow(1)
app.processEvents()
dlg.grab().save("shot_settings.png")

fp = M.FontPickerDialog("Microsoft YaHei", 32, False, False, dlg)
fp.show()
app.processEvents()
fp.lst.setCurrentRow(3)
app.processEvents()
fp.grab().save("shot_font.png")
fp.close()
dlg.close()
win.finish_edit()
print("SMOKE_OK")
