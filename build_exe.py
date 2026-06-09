"""AIRAG 打包脚本 — 运行此脚本生成 exe"""
import sys
sys.setrecursionlimit(10000)

import PyInstaller.__main__

EXCLUDES = [
    'PyQt5', 'torch', 'torchvision', 'torchaudio',
    'sympy', 'boto3', 'botocore', 'sphinx', 'docutils',
    'nbformat', 'jsonschema', 'zmq', 'nacl',
    'matplotlib', 'scipy', 'pandas', 'sqlalchemy',
    'redis', 'celery', 'uvicorn', 'starlette', 'fastapi',
    'flask', 'django', 'IPython', 'jupyter', 'notebook',
    'PIL.ImageQt', 'tkinter', 'numpy.random', 'numpy.distutils',
    'onnxruntime', 'onnx', 'tensorflow', 'tensorboard',
    'google', 'grpc', 'prometheus', 'opentelemetry',
    'pytest', 'black', 'isort', 'flake8', 'mypy', 'pylint',
    'coverage', 'Cython',
]

HIDDEN_IMPORTS = [
    'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
    'keyboard', 'keyboard._winkeyboard', 'keyboard._keyboard_event',
    'PIL', 'PIL.Image',
    'pydantic', 'pydantic.deprecated', 'pydantic.decorators',
    'asyncio', 'typing_extensions',
    'langgraph', 'langgraph.graph', 'langgraph.checkpoint',
    'langgraph.checkpoint.memory',
    'langchain_core', 'langchain_core.messages',
    'langchain_core.language_models',
    'langchain_core.language_models.chat_models',
    'langchain_core.callbacks', 'langchain_core.outputs',
    'volcenginesdkarkruntime',
    'json', 're', 'io', 'base64',
]

args = [
    '--onedir',
    '--name', 'AIRAG',
    '--console',
    '--noconfirm',
    '--clean',
]

for h in HIDDEN_IMPORTS:
    args += ['--hidden-import', h]

for e in EXCLUDES:
    args += ['--exclude-module', e]

args.append('main.py')

print(f"Building with {len(HIDDEN_IMPORTS)} hidden imports, {len(EXCLUDES)} exclusions...")
PyInstaller.__main__.run(args)
