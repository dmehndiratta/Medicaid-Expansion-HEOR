"""Pipeline package marker so `from pipeline.common import ...` resolves.

Stage scripts live in numbered subfolders (01_fetch, ...) that are not valid
Python module names, so they run as standalone scripts and add the repo root to
sys.path before importing this package.
"""
