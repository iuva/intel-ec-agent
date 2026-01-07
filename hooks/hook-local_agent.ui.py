"""
PyInstaller hook for local_agent.ui module
Ensures GUI process related files are included in the bundle
"""

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('local_agent.ui')

# Add Windows API modules
hiddenimports.extend([
    'win32pipe',
    'win32file', 
    'pywintypes',
    'win32api',
    'win32con',
    'win32process',
    'win32security',
    'ctypes'
])