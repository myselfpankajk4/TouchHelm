"""Content-derived browser builds; no frozen executable or manual version bump."""
import hashlib
from pathlib import Path
import threading

WEB_DIR = Path(__file__).resolve().parents[1] / 'web'
_lock = threading.Lock()
_cache = {}


def get_build_id(web_dir=WEB_DIR):
    root = Path(web_dir)
    files = sorted(path for path in root.rglob('*') if path.is_file()
                   and path.suffix.lower() in {'.html', '.css', '.js', '.json', '.svg'})
    signature = tuple((str(path.relative_to(root)), path.stat().st_mtime_ns,
                       path.stat().st_size) for path in files)
    with _lock:
        previous = _cache.get(str(root))
        if previous and previous[0] == signature:
            return previous[1]
        digest = hashlib.sha256()
        for path in files:
            digest.update(str(path.relative_to(root)).replace('\\', '/').encode())
            digest.update(b'\0')
            digest.update(path.read_bytes())
            digest.update(b'\0')
        version = digest.hexdigest()[:16]
        _cache[str(root)] = (signature, version)
        return version


def render_versioned(source, build_id):
    return source.replace('__TOUCHHELM_BUILD__', build_id)
