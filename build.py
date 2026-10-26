"""Run with Python 3.13 x64 after installing requirements-build.txt."""
from pathlib import Path
import PyInstaller.__main__
root = Path(__file__).resolve().parent
PyInstaller.__main__.run([
    '--noconfirm', '--clean', '--onefile', '--windowed',
    '--name', '异环小游戏助手',
    '--distpath', str(root / 'dist'),
    '--workpath', str(root / 'build'),
    '--specpath', str(root),
    '--add-data', str(root / 'src' / 'assets.npz') + ';.',
    str(root / 'src' / 'app.py'),
])
