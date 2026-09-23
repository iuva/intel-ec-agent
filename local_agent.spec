# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# 路径锚点：以 spec 文件自身位置为根目录，跨机器可直接复用
# PyInstaller 通过 exec() 执行 spec，不会自动设置 __file__，
# 但 sys.argv 里必定包含 .spec 文件路径（pyinstaller <spec> ...）。
_spec_candidates = [
    globals().get('specfile'),   # PyInstaller 5.x/6.x 可能注入
    globals().get('specpath'),
    globals().get('__file__'),   # 若直接 python xxx.spec 则有
]
for _arg in sys.argv[1:]:
    if _arg.lower().endswith('.spec'):
        _spec_candidates.append(_arg)
        break

_spec_path = next((p for p in _spec_candidates if p), None)
if not _spec_path:
    raise RuntimeError("无法解析 spec 文件自身路径，请通过 pyinstaller 命令运行")

_ROOT = os.path.dirname(os.path.abspath(_spec_path))

_ENTRY = os.path.join(_ROOT, 'src', 'local_agent', '__main__.py')
# 父目录用于解析 ../activity_monitor/ 模块
_PATHEX = [os.path.dirname(_ROOT), _ROOT, os.path.join(_ROOT, 'src')]
_DATAS = [
    (os.path.join(_ROOT, 'requirements.txt'), '.'),
    (os.path.join(_ROOT, 'VERSION'), '.'),
    (os.path.join(_ROOT, 'scripts'), 'scripts'),
]
_HOOKSPATH = [os.path.join(_ROOT, 'hooks')]


a = Analysis(
    [_ENTRY],
    pathex=_PATHEX,
    binaries=[],
    datas=_DATAS,
    hiddenimports=['local_agent', 'local_agent.api', 'local_agent.core', 'local_agent.websocket', 'local_agent.keep_alive', 'local_agent.ui', 'activity_monitor', 'activity_monitor.monitor', 'activity_monitor.state_machine', 'activity_monitor.logger', 'activity_monitor.config', 'activity_monitor.detectors', 'activity_monitor.detectors.input_detector', 'activity_monitor.detectors.process_detector', 'activity_monitor.detectors.screen_detector', 'activity_monitor.detectors.user_session_detector', 'tkinter', '_tkinter', 'fastapi', 'uvicorn', 'websockets', 'psutil', 'pywin32', 'requests', 'threading', 'time', 'subprocess'],
    hookspath=_HOOKSPATH,
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pythonwin', 'win32comext', 'adodbapi', 'isapi', 'pip', 'setuptools', 'pkg_resources', 'unittest', 'test', 'numpy', 'cryptography', 'PIL._avif', 'PIL._webp', 'win32ui', 'pywin.dialogs', 'pywin.mfc', 'matplotlib', 'pdfplumber', 'pdfminer', 'pdfminer.six', 'pptx', 'python_pptx', 'reportlab', 'authlib', 'msal'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='local_agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)