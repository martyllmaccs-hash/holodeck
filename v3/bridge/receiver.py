#!/usr/bin/env python3
"""Materialise tiny SSH telemetry frames; no network or GUI side effects."""
import argparse
import json
import os
import math
import re
import secrets
import stat
from pathlib import Path
import sys
import time
from urllib.parse import unquote

WORDS = dict(enumerate(('STANDBY', 'THINKING', 'BUILDING', 'READING', 'SEARCHING',
                        'RUNNING', 'DELEGATING', 'LISTENING', 'REPORTING', 'OFFLINE', 'UNLINKED')))
OUT = Path.home() / '.local/state/holo/beacon-vps.json'
MAX_LINE = 65536
MAX_NODES = 256
ID_RE = re.compile(r'[A-Za-z0-9_.:-]{1,128}\Z')


def decode(raw):
    if re.search(r'%(?![0-9a-fA-F]{2})', raw):
        raise ValueError('bad percent encoding')
    value = unquote(raw, errors='strict')
    if not value.isprintable() and value:
        raise ValueError('control character')
    return value


def parse_manifest(raw):
    result = []
    if raw:
        for entry in raw.split(';'):
            fields = entry.split(',')
            if len(fields) != 3:
                raise ValueError('bad manifest entry')
            result.append(tuple(decode(field) for field in fields))
    ids = [item[0] for item in result]
    if len(result) > MAX_NODES or len(set(ids)) != len(ids) or any(not ID_RE.fullmatch(node_id) for node_id in ids):
        raise ValueError('unknown or duplicate node id')
    parents = {node_id: parent for node_id, parent, _ in result}
    for node_id, parent, label in result:
        if not label or len(label) > 128 or (parent and parent not in parents):
            raise ValueError('invalid label or unknown parent')
        seen = {node_id}
        while parent:
            if parent in seen:
                raise ValueError('cyclic topology')
            seen.add(parent)
            parent = parents[parent]
    return result


def build_beacon(ts, topology, states, changed_at):
    nodes = []
    for node_id, parent, label in topology:
        code = states.get(node_id, 10)
        word = WORDS[code]
        nodes.append({
            'id': node_id, 'label': label,
            'role': 'ORCHESTRATOR' if not parent else 'WORKER',
            'kind': 'orchestrator' if not parent else 'worker',
            'profile': node_id, 'machine': 'vps',
            'state': {0: 'IDLE', 1: 'THINKING', 9: 'OFFLINE', 10: 'UNLINKED'}.get(code, word),
            'word': word, 'detail': word.lower(),
            'age_s': max(0, ts - changed_at.get(node_id, ts)),
            'alive': True if code <= 8 else (False if code == 9 else None),
            'inferred': True,
            'provenance': 'profile-scoped-state-db-classification',
        })
    online = sum(n['alive'] is True for n in nodes)
    working = sum(n['state'] not in ('IDLE', 'OFFLINE', 'UNLINKED') for n in nodes)
    return {
        'v': 1, 'machine': 'vps', 'transport': 'tiny-ssh-stream-v1',
        'beacon_ts': float(ts), 'iso': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(ts)),
        'nodes': nodes, 'links': [], 'handoffs': None,
        'totals': {'nodes_online': online, 'nodes_total': len(nodes), 'working': working,
                   'idle': online - working, **dict.fromkeys(('leaves_running', 'handoffs_today',
                   'api_calls_today', 'tokens_today', 'busiest'))},
    }


def atomic_write(path, payload):
    data = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode('utf-8')
    path = Path(path).absolute()
    # Walk from / with pinned directory descriptors. Never follow an ancestor symlink.
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    tmp = None
    try:
        for part in path.parts[1:-1]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            except FileNotFoundError:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=directory)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        try:
            existing = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(existing.st_mode):
                raise OSError('output is not a regular file')
        except FileNotFoundError:
            pass
        tmp = '.holo-' + secrets.token_hex(16) + '.tmp'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        tmp = None
        # Rename is the commit point. Directory sync is best effort after commit:
        # reporting a rejection here would disagree with the already replaced file.
        try:
            os.fsync(directory)
        except OSError:
            pass
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp, dir_fd=directory)
            except FileNotFoundError:
                pass
        os.close(directory)


class Receiver:
    def __init__(self, out=OUT, *, max_age=30, future_tolerance=5):
        if not math.isfinite(max_age) or not 0 < max_age <= 300 or not math.isfinite(future_tolerance) or not 0 <= future_tolerance <= 30:
            raise ValueError('invalid freshness bounds')
        self.max_age = max_age
        self.future_tolerance = future_tolerance
        self.out = Path(out)
        self.topology = []
        self.states = {}
        self.changed_at = {}
        self.state_seen = {}
        self.last_ts = None
        self.has_manifest = False

    def accept(self, line, *, now=None):
        if len(line) > MAX_LINE or line.count('|') != 2:
            raise ValueError('oversized or invalid frame')
        kind, raw_ts, body = line.removesuffix('\n').split('|')
        if not re.fullmatch(r'[0-9]{1,12}', raw_ts):
            raise ValueError('invalid timestamp')
        ts = int(raw_ts)
        now = time.time() if now is None else now
        if not math.isfinite(now) or not now - self.max_age <= ts <= now + self.future_tolerance:
            raise ValueError('timestamp outside freshness bounds')
        if ts < 0 or (self.last_ts is not None and ts < self.last_ts):
            raise ValueError('stale or non-monotonic timestamp')
        topology = self.topology
        if kind == 'M':
            topology = parse_manifest(body)
            ids = {item[0] for item in topology}
            states = {node_id: code for node_id, code in self.states.items()
                      if node_id in ids and now - self.state_seen.get(node_id, 0) <= self.max_age}
            state_seen = {node_id: self.state_seen[node_id] for node_id in states}
        elif kind == 'F':
            if not self.has_manifest:
                raise ValueError('frame before manifest')
            states = {}
            ids = {item[0] for item in topology}
            if body:
                for field in body.split(','):
                    node_id, raw_code = field.rsplit('=', 1)
                    node_id = decode(node_id)
                    if not re.fullmatch(r'(?:[0-9]|10)', raw_code):
                        raise ValueError('bad state code')
                    code = int(raw_code)
                    if code not in WORDS or node_id not in ids or node_id in states:
                        raise ValueError('unknown or duplicate node or bad state code')
                    states[node_id] = code
            state_seen = {node_id: ts for node_id in states}
        else:
            raise ValueError('unknown frame kind')
        changed_at = {node_id: self.changed_at.get(node_id, ts)
                      if self.states.get(node_id, 10) == states.get(node_id, 10) else ts
                      for node_id, _, _ in topology}
        payload = build_beacon(ts, topology, states, changed_at)
        # Commit filesystem first, then in-memory state; rejection never advances the cursor.
        atomic_write(self.out, payload)
        self.topology, self.states, self.changed_at = topology, states, changed_at
        self.state_seen = state_seen
        self.last_ts = ts
        self.has_manifest = True
        return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()
    receiver = Receiver(args.out)
    while True:
        raw = sys.stdin.buffer.readline(MAX_LINE + 1)
        if not raw:
            break
        try:
            if len(raw) > MAX_LINE:
                # Drain one oversized packet in bounded chunks; never treat its suffix as a packet.
                while raw and not raw.endswith(b'\n'):
                    raw = sys.stdin.buffer.readline(MAX_LINE + 1)
                raise ValueError('oversized frame')
            if not raw.endswith(b'\n'):
                raise ValueError('unterminated frame at EOF')
            receiver.accept(raw.decode('utf-8', errors='strict'))
        except (ValueError, OSError, OverflowError) as exc:
            print(f'holo stream receiver ignored malformed frame: {exc}', file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
