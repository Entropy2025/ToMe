# 念 ToMe — 桌面座右铭挂件

**版本 1.1.0** · Windows 10 19041+ / 11 · 提供安装包

在桌面上放一段只属于自己的话。文字贴在壁纸层之上、所有窗口之下，点击穿透，不挡任何操作；托盘右键即可编辑。

## 功能

- 桌面常驻座右铭：贴底（贴壁纸层）+ 鼠标点击穿透 + 心跳自愈（20s 重申沉底与穿透）
- 编辑模式：虚线框可视化，可拖动位置、右下角拖拽缩放，间隔期间实时渲染、实时保存
- 文字设置：字体（自研字体选择器，每项用自身字体渲染 + 名称搜索 + 实时预览）、字号滑杆、粗斜体、行距、对齐
- 文字颜色：自研取色器（SV 面板 + 色相条 + HEX 手输 + 最近使用色 + 预设色板）
- 文字可读性：不透明度滑杆（10%–100%）+ 柔和投影（8 方向，花哨壁纸上也清晰）
- 边框：颜色 + 透明度（0% 时禁用取色按钮）
- 全屏免打扰：检测到游戏/视频 D3D 全屏时自动隐藏文字，退出全屏自动回来（可在设置中关闭）
- 多屏适配：窗口跨屏/分辨率变化时自动拉回屏幕内；字号自适应以所在屏幕为界，可扩可缩
- 托盘操作：左键单击 显/隐文字，双击直接进入编辑，中键切换显隐，右键菜单
- 单实例：重复启动会唤起已运行实例并直接弹出编辑窗
- 界面：Win11 Fluent 2 设计语言，Mica 材质（Win11 DWM，Win10 自动回退纯色）、8/4 圆角阶、NavigationView 选中竖条、无边框圆角窗口 + DWM 阴影，深浅色跟随系统，中文/English 可切换
- 编辑历史：关闭设置窗口就把「文字 + 全部外观样式」存成一条，随时回看/恢复；可置顶（置顶的不会被 100 条上限淘汰）、删除单条、清空未置顶、导出 txt/json
- 其他：开机自启动（Fluent 开关，含路径自愈）、一键重置位置和大小、配置存于 `%APPDATA%\ToMe`（原子写入防损坏）

## 环境与运行

- Windows 10 19041+
- Python 3.10+，PySide6

```bash
pip install PySide6
python motto_qt.py
```

## 打包

### 1. 主程序（单文件 exe）

```bash
pyinstaller ToMe.exe.spec --noconfirm --clean
# 产物：dist/ToMe.exe（含 version_info.txt 里的产品名与版本号）
```

### 2. 安装包

安装包是自带安装器 `installer/setup_ui.py`，用 PyInstaller 把 `dist/ToMe.exe`
内嵌进去，**不依赖 Inno Setup / NSIS**：

```bash
pyinstaller --onefile --noconsole --name ToMe-Setup-1.0.0 \
  --icon assets/tome.ico \
  --add-data "dist/ToMe.exe;." \
  --distpath dist --workpath build/setup --specpath build/setup \
  installer/setup_ui.py
# 产物：dist/ToMe-Setup-1.0.0.exe
```

安装包做的事：装到 `%LOCALAPPDATA%\Programs\ToMe`（按用户安装，不需要管理员）、
建开始菜单与可选桌面快捷方式、可选写入开机自启、在「应用和功能」里登记卸载项。
支持 `--silent` 静默安装、`--uninstall` 卸载。

> 也可以用 `installer/ToMe.iss` 走 Inno Setup 路线（脚本已写好，含中文向导、
> 开机自启任务、卸载时清理启动项），只是本机没有装 Inno Setup。

## 测试

```bash
# 开机自启：真实读写 HKCU\...\Run\ToMe，覆盖开启/关闭/旧路径自愈，跑完还原原状态
set PYTHONPATH=E:\AI\ToMe\.builddeps;%CD%
python test_autostart.py

# 编辑历史逻辑：快照字段、去重、100 条上限与置顶保留、导出（APPDATA 指向隔离目录）
python test_history.py

# 编辑历史界面：列表/置顶/恢复/删除/清空/导出 + 关窗落一条，并生成 shot_history.png
python smoketest_history.py

# 主程序自检：起一个实例、确认窗口与 DWM 状态后自动退出
dist\ToMe.exe --selftest
```

## 目录说明

| 文件 | 说明 |
| --- | --- |
| `motto_qt.py` | 主程序（全部逻辑） |
| `installer/setup_ui.py` | 自带安装器（安装 / 卸载 / 静默） |
| `installer/ToMe.iss` | Inno Setup 安装脚本（备选路线） |
| `ToMe.exe.spec` | PyInstaller 打包配置 |
| `version_info.txt` | exe 的产品名 / 版本号资源 |
| `test_autostart.py` | 开机自启注册表测试 |
| `test_history.py` | 编辑历史逻辑测试（隔离 APPDATA） |
| `smoketest_history.py` | 编辑历史界面冒烟测试 + 截图 |
| `smoketest.py` | 冒烟测试：实例化各窗口并截图 |
| `kill_tome.py` | 终止 ToMe.exe 实例（含提权进程处理） |
| `assets/tome.ico` | 应用图标（QPainter 渲染「念」字生成） |
| `backups/` | 历次改动前的源码与 exe 备份 |
| `docs/` | 界面截图 |

## 实现要点

- 沉底方案：`SetWindowPos(HWND_BOTTOM)` + `WS_EX_TRANSPARENT`（桌面歌词式，放弃 WorkerW 挂靠——Qt 透明窗口挂入 WorkerW 不渲染）
- 全代码绘制：托盘图标、开关、取色面板均由 QPainter 绘制，无第三方 UI 库
- 单实例：命名 Mutex + 命名 Event（第二实例 `SetEvent`，首实例 1s 轮询 `WaitForSingleObject` 唤起编辑窗）
- 全屏检测：`shell32.SHQueryUserNotificationState` 返回 `QUNS_RUNNING_D3D_FULL_SCREEN` 时自动隐藏
- 配置安全：写临时文件后 `os.replace` 原子替换，避免异常退出损坏配置

## License

MIT
