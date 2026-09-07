"""Evidence for observed renders, separate from structural and editor checks."""
import hashlib
from pathlib import Path


def screenshot(path):
    from asset_validation import asset_error
    p = Path(path).expanduser().resolve()
    error = asset_error(p, 'PNG')
    if error:
        raise ValueError('Invalid review screenshot: ' + str(error))
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def current(evidence):
    if not isinstance(evidence, dict) or evidence.get('surface') not in ('local_preview', 'cardkit'):
        return False
    for key in ('desktop', 'mobile'):
        item = evidence.get(key) or {}
        if not isinstance(item, dict):
            return False
        try:
            if screenshot(item['path'])['sha256'] != item['sha256']:
                return False
        except (KeyError, OSError, ValueError):
            return False
    return True
