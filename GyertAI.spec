# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Кладём .env внутрь сборки, чтобы установленное приложение находило ключи API.
for _extra in ('edge_tts', 'gtts'):
    _t = collect_all(_extra)
    datas += _t[0]; binaries += _t[1]; hiddenimports += _t[2]

if os.path.exists('.env'):
    datas.append(('.env', '.'))

# Логотип: PNG с прозрачным фоном из assets попадает в сборку, а из него делается
# .ico — он становится значком самой программы и установщика.
if os.path.exists('assets'):
    datas.append(('assets', 'assets'))

ICON = None
if os.path.exists('assets/logo.png'):
    ICON = 'assets/logo.ico'
    if not os.path.exists(ICON):
        try:
            from PIL import Image
            logo = Image.open('assets/logo.png').convert('RGBA')
            # Значки Windows квадратные: логотип вписываем по центру прозрачного квадрата.
            side = max(logo.size)
            canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
            canvas.paste(logo, ((side - logo.width) // 2, (side - logo.height) // 2))
            canvas.save(
                ICON, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
            )
        except Exception as e:
            print('Не удалось сделать значок из логотипа:', e)
            ICON = None


a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Папка сборки (не один файл): так приложение запускается мгновенно и его
# удобно положить в установщик, который ставит GyertAI как обычную программу.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GyertAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GyertAI',
)
