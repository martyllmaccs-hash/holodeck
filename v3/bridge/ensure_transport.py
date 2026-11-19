#!/usr/bin/env python3
"""Restore the Holodeck s6 slot after container restart; no agent/API calls."""
import argparse
import os
from pathlib import Path
import stat
import subprocess


def ensure(scandir=Path('/run/service'), template=Path('/opt/data/holo/service'), ctl='/command/s6-svscanctl'):
    slot = scandir / 'holo-transport'
    if slot.is_symlink():
        if slot.resolve() != template.resolve():
            raise RuntimeError('unexpected Holodeck service target')
    elif slot.exists():
        if (slot / 'run').read_bytes() != (template / 'run').read_bytes():
            raise RuntimeError('unexpected Holodeck service directory')
    else:
        # Runtime control state belongs on /run, not the persistent data volume.
        # Seed hermes-owned supervision paths before the root supervisor starts.
        import shutil
        slot.mkdir(mode=0o700)
        (slot / 'log').mkdir(mode=0o700)
        for name in ('run', 'finish', 'log/run'):
            shutil.copy2(template / name, slot / name)
        for root in (slot, slot / 'log'):
            for name in ('supervise', 'event'):
                p = root / name
                p.mkdir(mode=0o700, exist_ok=True)
            fifo = root / 'supervise/control'
            if not fifo.exists():
                os.mkfifo(fifo, 0o600)
            elif not stat.S_ISFIFO(fifo.stat().st_mode):
                raise RuntimeError('unexpected control file')
    subprocess.run([ctl, '-a', str(scandir)], check=True, timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scandir', type=Path, default=Path('/run/service'))
    parser.add_argument('--template', type=Path, default=Path('/opt/data/holo/service'))
    parser.add_argument('--ctl', default='/command/s6-svscanctl')
    args = parser.parse_args()
    ensure(args.scandir, args.template, args.ctl)
