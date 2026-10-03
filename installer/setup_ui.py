# -*- coding: utf-8 -*-
"""念 ToMe 安装程序（自带安装器，不依赖 Inno Setup）。

用法：
    ToMe-Setup-1.0.0.exe             安装（图形向导）
    ToMe-Setup-1.0.0.exe --uninstall 卸载
    ToMe-Setup-1.0.0.exe --silent    静默安装（默认选项，供自动化调用）

安装内容：
    %LOCALAPPDATA%\\Programs\\ToMe\\ToMe.exe
    %LOCALAPPDATA%\\Programs\\ToMe\\unins000.exe   （卸载器 = 本程序副本）
    开始菜单 / 桌面快捷方式（可选）
    HKCU\\...\\Run\\ToMe                            （可选：开机自启）
    HKCU\\...\\Uninstall\\ToMe                      （「应用和功能」里的卸载项）
"""
import os
import shutil
import subprocess
import sys
import threading

APP_NAME = "念 ToMe"
APP_NAME_EN = "ToMe"
APP_VERSION = "1.1.0"
APP_EXE = "ToMe.exe"
UNINST_EXE = "unins000.exe"
PUBLISHER = "ToMe"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ToMe"
RUN_VALUE = "ToMe"

LOCALAPPDATA = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
DEFAULT_DIR = os.path.join(LOCALAPPDATA, "Programs", "ToMe")

CREATE_NO_WINDOW = 0x08000000


def app_dir():
    return os.path.join(LOCALAPPDATA, "Programs", "ToMe")


def start_menu_dir():
    return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                        "Start Menu", "Programs")


def desktop_dir():
    return os.path.join(os.path.expanduser("~"), "Desktop")


def payload_path():
    """内嵌的 ToMe.exe：冻结后从 _MEIPASS 取，开发时取 dist 下的。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    cand = os.path.join(base, APP_EXE)
    if os.path.exists(cand):
        return cand
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, "..", "dist", APP_EXE)
    if os.path.exists(cand):
        return os.path.abspath(cand)
    return None


# ---------------- 注册表 ----------------
def reg_set_autorun(path):
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, '"%s"' % path)


def reg_del_autorun():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            try:
                winreg.DeleteValue(k, RUN_VALUE)
            except FileNotFoundError:
                pass
    except OSError:
        pass


def reg_register_uninstall(d, size_kb):
    import winreg
    uninst = os.path.join(d, UNINST_EXE)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINST_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
        vals = [
            ("DisplayName", "%s %s" % (APP_NAME, APP_VERSION)),
            ("DisplayVersion", APP_VERSION),
            ("Publisher", PUBLISHER),
            ("InstallLocation", d),
            ("DisplayIcon", "%s,0" % uninst),
            ("UninstallString", '"%s" --uninstall' % uninst),
            ("QuietUninstallString", '"%s" --uninstall --silent' % uninst),
            ("NoModify", 1),
            ("NoRepair", 1),
            ("EstimatedSize", int(size_kb)),
        ]
        for name, val in vals:
            winreg.SetValueEx(k, name, 0,
                              winreg.REG_DWORD if isinstance(val, int)
                              else winreg.REG_SZ, val)


def reg_delete_uninstall():
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINST_KEY)
    except OSError:
        pass


# ---------------- 快捷方式 ----------------
def make_shortcut(lnk_path, target, workdir, icon=None):
    """用系统自带的 WScript.Shell 建 .lnk，避免引入额外依赖。"""
    icon = icon or target
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
        "$s.TargetPath='%s';$s.WorkingDirectory='%s';"
        "$s.IconLocation='%s,0';$s.Description='%s';$s.Save()"
        % (lnk_path, target, workdir, icon, APP_NAME)
    )
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                   creationflags=CREATE_NO_WINDOW, capture_output=True)


def remove_shortcuts():
    for p in shortcut_paths():
        try:
            os.remove(p)
        except OSError:
            pass


def shortcut_paths():
    return [os.path.join(start_menu_dir(), "%s.lnk" % APP_NAME),
            os.path.join(desktop_dir(), "%s.lnk" % APP_NAME)]


# ---------------- 安装 / 卸载 ----------------
def do_install(target_dir, desktop_icon, autostart, log):
    src = payload_path()
    if not src:
        raise RuntimeError("安装包内没有找到 %s" % APP_EXE)

    log("正在创建安装目录…")
    os.makedirs(target_dir, exist_ok=True)

    dst = os.path.join(target_dir, APP_EXE)
    log("正在复制主程序…")
    # 目标可能正在运行，先结束它
    subprocess.run(["taskkill", "/IM", APP_EXE, "/F"],
                   creationflags=CREATE_NO_WINDOW, capture_output=True)
    shutil.copy2(src, dst)

    log("正在写入卸载程序…")
    if getattr(sys, "frozen", False):
        try:
            shutil.copy2(sys.executable, os.path.join(target_dir, UNINST_EXE))
        except OSError:
            pass

    log("正在创建快捷方式…")
    remove_shortcuts()
    make_shortcut(os.path.join(start_menu_dir(), "%s.lnk" % APP_NAME),
                  dst, target_dir, dst)
    if desktop_icon:
        make_shortcut(os.path.join(desktop_dir(), "%s.lnk" % APP_NAME),
                      dst, target_dir, dst)

    log("正在设置开机自启…")
    if autostart:
        reg_set_autorun(dst)
    else:
        reg_del_autorun()

    log("正在注册卸载信息…")
    size_kb = 0
    for root, _dirs, files in os.walk(target_dir):
        for f in files:
            try:
                size_kb += os.path.getsize(os.path.join(root, f)) // 1024
            except OSError:
                pass
    reg_register_uninstall(target_dir, size_kb)

    log("安装完成。")


def do_uninstall(target_dir, log):
    subprocess.run(["taskkill", "/IM", APP_EXE, "/F"],
                   creationflags=CREATE_NO_WINDOW, capture_output=True)
    log("正在删除快捷方式…")
    remove_shortcuts()
    log("正在清除开机自启…")
    reg_del_autorun()
    log("正在注销卸载信息…")
    reg_delete_uninstall()

    log("正在删除程序文件…")
    for name in os.listdir(target_dir) if os.path.isdir(target_dir) else []:
        p = os.path.join(target_dir, name)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif name.lower() != UNINST_EXE:
                os.remove(p)
        except OSError:
            pass
    # 自己（unins000.exe）还占着目录，交给 cmd 延迟删除
    subprocess.Popen(
        'cmd /c ping -n 3 127.0.0.1 >nul & rmdir /s /q "%s"' % target_dir,
        shell=True, creationflags=CREATE_NO_WINDOW)
    log("卸载完成。")


# ---------------- 图形界面 ----------------
def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("%s %s 安装程序" % (APP_NAME, APP_VERSION))
    root.resizable(False, False)

    frm = ttk.Frame(root, padding=16)
    frm.grid(sticky="nsew")

    ttk.Label(frm, text="%s — 桌面座右铭挂件" % APP_NAME,
              font=("Microsoft YaHei UI", 12, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(frm, text="把一段只属于自己的话，贴在桌面壁纸之上。").grid(
        row=1, column=0, columnspan=3, sticky="w", pady=(2, 12))

    ttk.Label(frm, text="安装位置：").grid(row=2, column=0, sticky="w")
    dir_var = tk.StringVar(value=app_dir())
    ttk.Entry(frm, textvariable=dir_var, width=44).grid(
        row=2, column=1, sticky="we", padx=(0, 6))

    def browse():
        p = filedialog.askdirectory(initialdir=dir_var.get() or LOCALAPPDATA)
        if p:
            dir_var.set(os.path.join(p, "ToMe"))
    ttk.Button(frm, text="浏览…", command=browse).grid(row=2, column=2)

    desk_var = tk.BooleanVar(value=True)
    run_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(frm, text="创建桌面快捷方式", variable=desk_var).grid(
        row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))
    ttk.Checkbutton(frm, text="开机自动启动（可随时在程序设置里切换）",
                    variable=run_var).grid(
        row=4, column=0, columnspan=3, sticky="w")

    bar = ttk.Progressbar(frm, mode="indeterminate", length=420)
    bar.grid(row=5, column=0, columnspan=3, sticky="we", pady=(14, 4))
    status = ttk.Label(frm, text="准备就绪，点击「开始安装」。")
    status.grid(row=6, column=0, columnspan=3, sticky="w")

    def log(msg):
        status.config(text=msg)
        root.update_idletasks()

    btns = ttk.Frame(frm)
    btns.grid(row=7, column=0, columnspan=3, sticky="e", pady=(14, 0))
    install_btn = ttk.Button(btns, text="开始安装")
    quit_btn = ttk.Button(btns, text="退出", command=root.destroy)
    install_btn.grid(row=0, column=0, padx=(0, 8))
    quit_btn.grid(row=0, column=1)

    def worker():
        bar.start(12)
        try:
            do_install(dir_var.get().strip() or app_dir(),
                       desk_var.get(), run_var.get(), log)
        except Exception as e:  # noqa: BLE001
            bar.stop()
            log("安装失败：%s" % e)
            messagebox.showerror("安装失败", str(e))
            install_btn.config(state="normal")
            return
        bar.stop()
        install_btn.config(state="disabled")
        if messagebox.askyesno("安装完成",
                               "%s 已安装完成。\n\n现在就启动它吗？" % APP_NAME):
            subprocess.Popen([os.path.join(dir_var.get().strip() or app_dir(),
                                           APP_EXE)],
                             creationflags=CREATE_NO_WINDOW)
        root.destroy()

    def start():
        install_btn.config(state="disabled")
        threading.Thread(target=worker, daemon=True).start()

    install_btn.config(command=start)
    root.mainloop()
    return 0


def main():
    args = sys.argv[1:]
    if "--uninstall" in args:
        silent = "--silent" in args
        if silent:
            do_uninstall(app_dir(), lambda _m: None)
            return 0
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        if messagebox.askyesno("卸载 %s" % APP_NAME,
                               "确定要卸载 %s 吗？" % APP_NAME):
            do_uninstall(app_dir(), lambda _m: None)
            messagebox.showinfo("卸载完成", "%s 已卸载。" % APP_NAME)
        r.destroy()
        return 0

    if "--silent" in args:
        do_install(app_dir(), True, True, lambda _m: None)
        return 0

    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
