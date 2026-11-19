#!/usr/bin/env python3
"""Metadata-only Bot Chat hop detector for the VPS fleet bridge.

Reads each registered profile's canonical ``Bot Chat`` session read-only and
reports new conversational hops as ``E`` wire lines:

    E|<ts>|<from>,<to>,<event_id>,<at_ms>;...

A new user row in a worker's Bot Chat is reported as default -> worker; a final
assistant reply (no tool calls) as worker -> default.  The store does not record
who typed the user row, so every event is flagged derived/from_confirmed=false
by the receiver -- the same honesty level as P1's collector message pulses.
Message bodies are only inspected locally to skip process notifications; no
body, title or tool data ever leaves this process.
"""
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

TOKEN = re.compile(r'[A-Za-z0-9_.:-]{1,64}\Z')
ORCHESTRATOR = 'default'
WINDOW_S = 8.0          # resend recent hops each tick; receiver dedupes by id
MAX_EVENTS = 24
MAX_PER_NODE_TICK = 4
NOTIFICATION_PREFIXES = ('[IMPORTANT:', '[SYSTEM:', '[System:')

QUERY = """
SELECT m.id, m.role, m.timestamp, m.tool_calls, m.display_kind, substr(m.content,1,16)
FROM messages m JOIN sessions s ON s.id = m.session_id
WHERE s.title = 'Bot Chat' AND s.archived = 0 AND s.profile_name = ?
  AND s.source NOT IN ('tool','kanban','subagent')
  AND m.role IN ('user','assistant') AND m.id > ?
ORDER BY m.id ASC LIMIT 64
"""
NEWEST = """
SELECT max(m.id) FROM messages m JOIN sessions s ON s.id = m.session_id
WHERE s.title = 'Bot Chat' AND s.archived = 0 AND s.profile_name = ?
"""


def _hop(node, row):
    """One stored row -> (from, to) or None when it is not a conversational hop."""
    _id, role, _ts, tool_calls, display_kind, head = row
    if display_kind:
        return None                     # process completions, deliveries, etc.
    if role == 'user':
        if isinstance(head, str) and head.lstrip().startswith(NOTIFICATION_PREFIXES):
            return None
        return ORCHESTRATOR, node
    if role == 'assistant':
        if tool_calls not in (None, '', '[]', b'', b'[]'):
            return None                 # intermediate tool step, not a reply
        if not isinstance(head, str) or not head.strip():
            return None
        return node, ORCHESTRATOR
    return None


class MessageWatch:
    def __init__(self, window=WINDOW_S):
        self.window = window
        self.cursor = {}                # node -> last seen message id
        self.events = {}                # event id -> (from, to, at)

    def poll(self, nodes, *, now=None):
        now = time.time() if now is None else now
        ids = {n['id'] for n in nodes}
        if ORCHESTRATOR not in ids:
            self.events.clear()
            return ''
        for node in nodes:
            name = node['id']
            if name == ORCHESTRATOR or not TOKEN.fullmatch(name):
                continue
            db = Path(node['db'])
            if db.is_symlink() or not db.is_file():
                continue
            try:
                with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=.2)) as con:
                    con.execute('PRAGMA query_only=ON')
                    if name not in self.cursor:
                        # First sight only sets the baseline: no flood on restart.
                        self.cursor[name] = con.execute(NEWEST, (name,)).fetchone()[0] or 0
                        continue
                    rows = con.execute(QUERY, (name, self.cursor[name])).fetchall()
            except sqlite3.Error:
                continue                # fail open: a locked store just skips a tick
            if not rows:
                continue
            self.cursor[name] = rows[-1][0]
            emitted = 0
            for row in rows:
                hop = _hop(name, row)
                ts = row[2]
                if hop is None or not isinstance(ts, (int, float)) or now - ts > self.window:
                    continue
                if emitted >= MAX_PER_NODE_TICK:
                    break
                self.events['bot:%s:%d' % (name, row[0])] = (hop[0], hop[1], now)
                emitted += 1
        self.events = {eid: e for eid, e in self.events.items()
                       if e[0] in ids and e[1] in ids and 0 <= now - e[2] <= self.window}
        if len(self.events) > MAX_EVENTS:
            keep = sorted(self.events.items(), key=lambda kv: kv[1][2])[-MAX_EVENTS:]
            self.events = dict(keep)
        if not self.events:
            return ''
        body = ';'.join(','.join((quote(f, safe=''), quote(t, safe=''), quote(eid, safe=''),
                                  str(int(at * 1000))))
                        for eid, (f, t, at) in sorted(self.events.items(), key=lambda kv: kv[1][2]))
        line = 'E|%d|%s\n' % (int(now), body)
        if len(line.encode('ascii')) > 4096:
            return ''
        return line
