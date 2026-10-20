"""Locations shared by the self-contained Windows distribution."""
import os
from pathlib import Path


def bundle_root():
    value = os.environ.get('TOUCHHELM_PORTABLE_ROOT')
    # Resolving a redirected AppData alias expands it into a much longer Store
    # package cache path. Keep the logical absolute path for native child loads.
    return Path(value).absolute() if value else None


def config_path(source_root):
    if bundle_root() is None:
        return Path(source_root)/'config.json'
    local = os.environ.get('LOCALAPPDATA')
    if not local:
        raise RuntimeError('Windows LocalAppData is unavailable. Sign in to a Windows user account and retry.')
    folder = Path(local)/'TouchHelm'
    folder.mkdir(parents=True, exist_ok=True)
    return folder/'config.json'
