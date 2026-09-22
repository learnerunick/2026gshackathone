#!/usr/bin/env python3
"""Generate local deployment secrets once without printing their values."""
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
target = root / '.env.remote'
data = ('# Keep this file private. Configure the two HTTPS origins before deployment.\n'
        'BOCA_PUBLIC_ORIGIN=https://your-project.vercel.app\n'
        'BOCA_BRIDGE_ORIGIN=https://boca-worker.your-domain.example\n' +
        ''.join(key + '=' + secrets.token_urlsafe(36) + '\n' for key in
                ['BOCA_BRIDGE_SECRET', 'BOCA_SESSION_SECRET']))
try:
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit('.env.remote already exists; existing secrets were not replaced.')
with os.fdopen(fd, 'w') as stream:
    stream.write(data)
print('Created private .env.remote (0600); no secret values were printed.')
