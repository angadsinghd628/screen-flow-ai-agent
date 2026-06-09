# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'keyboard', 'keyboard._winkeyboard', 'PIL', 'PIL.Image', 'pydantic', 'asyncio', 'typing_extensions', 'langgraph', 'langgraph.graph', 'langgraph.checkpoint', 'langgraph.checkpoint.memory', 'langchain_core', 'langchain_core.messages', 'langchain_core.language_models', 'langchain_core.language_models.chat_models', 'langchain_core.callbacks', 'langchain_core.outputs', 'volcenginesdkarkruntime', 'volcenginesdkcore', 'volcenginesdkark', 'json', 're', 'io', 'base64', 'six', 'sniffio'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AIRAG',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['F:\\AIRAG\\dist\\1.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AIRAG',
)
