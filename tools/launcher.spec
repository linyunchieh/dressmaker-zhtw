# -*- mode: python ; coding: utf-8 -*-
# pyinstaller tools/launcher.spec（路徑以本檔所在目錄為準）
from PyInstaller.utils.hooks import collect_data_files
a = Analysis(['Dressmaker_zhTW.py'], pathex=[SPECPATH], datas=collect_data_files('certifi'),
             hiddenimports=['truststore', 'certifi'], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='Dressmaker繁體中文化補丁',
          debug=False, strip=False, upx=True, console=False)
