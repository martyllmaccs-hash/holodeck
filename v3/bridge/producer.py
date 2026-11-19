#!/usr/bin/env python3
"""Read-only, profile-scoped SQLite metadata classification for tiny SSH frames.

States are inferences from telemetry, not observed tool use or proof of idleness.
No messages, prompts, task/result JSON, credentials, configs or routing payloads
are queried. A profile directory is not bot registration.
"""
import argparse
from contextlib import closing
import json
import math
import os
from pathlib import Path
import re
import socket
import sqlite3
import time
from urllib.parse import quote

DEFAULT_DB = Path('/opt/data/state.db')
DEFAULT_INVENTORY = Path(__file__).resolve().with_name('inventory.json')
CODES = {'STANDBY': 0, 'THINKING': 1, 'BUILDING': 2, 'READING': 3, 'SEARCHING': 4,
         'RUNNING': 5, 'DELEGATING': 6, 'LISTENING': 7, 'REPORTING': 8,
         'OFFLINE': 9, 'UNLINKED': 10}
EXPECTED = {
    'gateway_heartbeats': {'profile', 'pid', 'last_heartbeat', 'host'},
    'sessions': {'id', 'profile_name'},
    'session_turn_leases': {'conversation_id', 'holder', 'acquired_at', 'expires_at'},
    'async_delegations': {'parent_session_id', 'origin_session_id', 'state', 'updated_at', 'owner_pid'},
}
ID_RE = re.compile(r'[A-Za-z0-9_.:-]{1,128}\Z')


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, OSError):
        return False


def read_status(path=DEFAULT_DB, *, now=None, max_age=30, profile='default'):
    """Use a single read-only snapshot; un-attributable activity is never assigned."""
    now = time.time() if now is None else float(now)
    if not math.isfinite(now) or not math.isfinite(max_age) or not 0 < max_age <= 300:
        raise ValueError('invalid timestamp or max age')
    if not ID_RE.fullmatch(profile):
        raise ValueError('invalid profile identifier')
    try:
        uri = Path(path).resolve().as_uri() + '?mode=ro'
        with closing(sqlite3.connect(uri, uri=True, timeout=1)) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            for table, expected in EXPECTED.items():
                columns = {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')}
                if not expected <= columns:
                    return 'UNLINKED'
            beats = db.execute('SELECT pid,last_heartbeat,host FROM gateway_heartbeats WHERE profile=?',
                               (profile,)).fetchall()
            local_host = socket.gethostname()
            # PID checks apply only in this host/PID namespace, never to foreign heartbeats.
            local = [(int(pid), float(ts)) for pid, ts, host in beats if host == local_host]
            # Hermes backend refreshes every 60s by default; allow three ticks.
            # Activity recency remains independently bounded by max_age.
            heartbeat_live = any(0 <= now-ts <= 180 and pid > 0 and _pid_alive(pid) for pid, ts in local)
            leases = db.execute('''SELECT l.holder FROM session_turn_leases l
                JOIN sessions s ON s.id=l.conversation_id
                WHERE s.profile_name=? AND l.acquired_at<=? AND l.expires_at>?''',
                               (profile, now, now)).fetchall()
            for (holder,) in leases:
                match = re.search(r'(?:^|[:| ,])pid=(\d+)(?:$|[:| ,])', str(holder))
                if match:
                    pid = int(match.group(1))
                    if pid > 0 and _pid_alive(pid):
                        return 'THINKING'
                elif heartbeat_live:
                    return 'THINKING'
            rows = db.execute('''SELECT d.owner_pid FROM async_delegations d
                JOIN sessions s ON s.id=COALESCE(NULLIF(d.origin_session_id,''),d.parent_session_id)
                WHERE s.profile_name=? AND d.state IN ('running','finalizing')
                AND d.updated_at BETWEEN ? AND ?''', (profile, now-max_age, now)).fetchall()
            if any(pid is not None and int(pid) > 0 and _pid_alive(int(pid)) for (pid,) in rows):
                return 'DELEGATING'
            # Bot activity is independent of its source connection. A registered
            # profile with no active turn/delegation is OFFLINE; transport/collector
            # freshness is the only authority for UNLINKED.
            return 'OFFLINE'
    except (OSError, sqlite3.Error, TypeError, ValueError, OverflowError):
        return 'UNLINKED'


def produce_frame(path=DEFAULT_DB, *, now=None, max_age=30, profile='default'):
    observed_at = time.time() if now is None else float(now)
    ts = int(observed_at)
    state = read_status(path, now=observed_at, max_age=max_age, profile=profile)
    label = 'LANA' if profile == 'default' else profile
    node_id = quote(profile, safe='')
    return f'M|{ts}|{node_id},,{quote(label, safe="")}\nF|{ts}|{node_id}={CODES[state]}\n'


def produce_inventory_frame(nodes, *, now=None, max_age=30):
    if not isinstance(nodes, list) or len(nodes) > 256:
        raise ValueError('invalid inventory node list')
    seen = set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {'id', 'label', 'db', 'parent'}:
            raise ValueError('invalid inventory entry')
        node_id, label = node['id'], node['label']
        if not isinstance(node_id, str) or not ID_RE.fullmatch(node_id) or node_id in seen:
            raise ValueError('duplicate or invalid inventory id')
        if not isinstance(label, str) or not label or len(label) > 128 or not label.isprintable():
            raise ValueError('invalid inventory label')
        if node['parent'] != '' or not isinstance(node['db'], str) or not Path(node['db']).is_absolute():
            raise ValueError('inventory must use explicit absolute DBs and independent roots')
        seen.add(node_id)
    observed_at = time.time() if now is None else float(now)
    ts = int(observed_at)
    manifest = ';'.join(f'{quote(n["id"], safe="")},,{quote(n["label"], safe="")}' for n in nodes)
    frame = ','.join(f'{quote(n["id"], safe="")}={CODES[read_status(n["db"], now=observed_at, max_age=max_age, profile=n["id"])]}' for n in nodes)
    result = f'M|{ts}|{manifest}\nF|{ts}|{frame}\n'
    if any(len(line) + 1 > 65536 for line in result.splitlines()):
        raise ValueError('inventory exceeds wire size limit')
    return result


def discover_registered_nodes(home, labels=None):
    """Read canonical Bot Chat registration metadata every cycle, never messages.

    Mirrors the backend's canonical identity predicate conservatively: an exact
    nonarchived Bot Chat on the exact profile and a human-facing source. Never
    calls the backend helper, which may unarchive sessions or read previews.
    """
    home = Path(home)
    if not home.is_absolute() or home.is_symlink():
        raise ValueError('registration home must be explicit, absolute and not a symlink')
    labels = labels or {}
    candidates = [('default', home)]
    profiles = home / 'profiles'
    if profiles.is_dir() and not profiles.is_symlink():
        candidates.extend(sorted((p.name, p) for p in profiles.iterdir()
                                 if p.is_dir() and not p.is_symlink() and ID_RE.fullmatch(p.name)))
    nodes = []
    for name, directory in candidates:
        path = directory/'state.db'
        if path.is_symlink() or not path.is_file():
            continue
        try:
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
                db.execute('PRAGMA query_only=ON')
                registered = db.execute("""SELECT 1 FROM sessions WHERE title='Bot Chat'
                    AND archived=0 AND profile_name=?
                    AND source NOT IN ('tool','kanban','subagent') LIMIT 1""",(name,)).fetchone()
            if registered:
                nodes.append({'id':name,'label':labels.get(name, 'LANA' if name=='default' else name),
                              'db':str(path),'parent':''})
        except (OSError,sqlite3.Error):
            continue
    return nodes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--max-age', type=float, default=30)
    parser.add_argument('--profile')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--once', action='store_true')
    mode.add_argument('--loop', action='store_true')
    parser.add_argument('--interval', type=float, default=2)
    args = parser.parse_args()
    if not math.isfinite(args.interval) or not 0 < args.interval <= 60:
        parser.error('--interval must be finite and in (0,60]')
    if not math.isfinite(args.max_age) or not 0 < args.max_age <= 300:
        parser.error('--max-age must be finite and in (0,300]')
    if args.profile is not None and not ID_RE.fullmatch(args.profile):
        parser.error('invalid profile identifier')
    if args.inventory is not None and (args.db is not None or args.profile is not None):
        parser.error('--inventory is incompatible with --db/--profile')
    inventory = args.inventory if args.inventory is not None else (DEFAULT_INVENTORY if args.db is None and args.profile is None else None)
    try:
        while True:
            # Repeat the manifest for reconnect-safe streams; it carries no invented bots.
            if inventory is None:
                frame = produce_frame(args.db or DEFAULT_DB, max_age=args.max_age, profile=args.profile or 'default')
            else:
                try:
                    snapshot = json.loads(inventory.read_text(encoding='utf-8'))
                    if not isinstance(snapshot, dict) or snapshot.get('v') not in (1,2):
                        raise ValueError('invalid inventory version')
                    if snapshot['v'] == 2:
                        if not isinstance(snapshot.get('labels',{}),dict):
                            raise ValueError('invalid labels mapping')
                        nodes = discover_registered_nodes(snapshot['registration_home'], snapshot.get('labels'))
                    else:
                        nodes = snapshot.get('nodes')
                    frame = produce_inventory_frame(nodes, max_age=args.max_age)
                except (OSError, ValueError, TypeError) as exc:
                    parser.error(f'invalid inventory: {exc}')
            print(frame, end='', flush=True)
            if not args.loop:
                break
            time.sleep(args.interval)
    except (BrokenPipeError, KeyboardInterrupt):
        return


if __name__ == '__main__':
    main()
