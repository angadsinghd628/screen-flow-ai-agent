# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'keyboard', 'keyboard._winkeyboard', 'keyboard._keyboard_event', 'PIL', 'PIL.Image', 'pydantic', 'pydantic.deprecated', 'pydantic.decorators', 'asyncio', 'typing_extensions', 'langgraph', 'langgraph.graph', 'langgraph.checkpoint', 'langgraph.checkpoint.memory', 'langchain_core', 'langchain_core.messages', 'langchain_core.language_models', 'langchain_core.language_models.chat_models', 'langchain_core.callbacks', 'langchain_core.outputs', 'volcenginesdkarkruntime', 'json', 're', 'io', 'base64'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'torch', 'torchvision', 'torchaudio', 'sympy', 'boto3', 'botocore', 'sphinx', 'docutils', 'nbformat', 'jsonschema', 'zmq', 'nacl', 'matplotlib', 'scipy', 'pandas', 'sqlalchemy', 'redis', 'celery', 'uvicorn', 'starlette', 'fastapi', 'flask', 'django', 'IPython', 'jupyter', 'notebook', 'PIL.ImageQt', 'tkinter', 'numpy.random', 'numpy.distutils', 'onnxruntime', 'onnx', 'tensorflow', 'tensorboard', 'google', 'grpc', 'prometheus', 'opentelemetry', 'pytest', 'black', 'isort', 'flake8', 'mypy', 'pylint', 'coverage', 'Cython', 'jaxlib', 'jax', 'paddle', 'cv2', 'opencv', 'bokeh', 'pyarrow', 'llvmlite', 'transformers', 'pymupdf', 'selenium', 'sklearn', 'scikit', 'jieba', 'googleapiclient', 'polars', 'numba', 'rasterio', 'pyogrio', 'shapely', 'geopandas', 'fiona', 'tensorflow_text', 'tensorflow_hub', 'tflite', 'mmengine', 'mmcv', 'mmdet', 'litellm', 'langchain', 'langchain_community', 'tqdm', 'paddleocr', 'paddlepaddle', 'rich', 'aiohttp', 'aiosignal', 'frozenlist', 'yarl', 'multidict'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Ai_Flow',
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
    icon=['F:/AIRAG/1.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Ai_Flow',
)
