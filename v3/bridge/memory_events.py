#!/usr/bin/env python3
"""Metadata-only Hindsight retain/recall detector for the VPS fleet bridge.

Tails Lana's observer log (runtime-default.jsonl) from its current end and turns
memory traffic into E wire events between ``default`` and a ``hindsight`` node:

  retain  default -> hindsight   hindsight_retain tool call (explicit), and the
                                 provider's automatic turn retain, detected when a
                                 turn that made LLM calls stops refreshing
  recall  hindsight -> default   hindsight_recall / hindsight_reflect results, and
                                 the provider's automatic prefetch recall before
                                 the first LLM call of each turn

Event ids say which: mem.retain.tool.*, mem.retain.auto.*, mem.recall.tool.*,
mem.recall.auto.*. "auto" events are inferred from the configured memory mode
(memory_mode=hybrid, prefetch_method=recall), not observed on the wire.
Only tool names, event kinds, turn ids and timestamps are read; nothing leaves.
Only the default profile has a Hindsight provider, so only it is watched.
"""
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

NODE = 'hindsight'
LABEL = 'Hindsight'
ROOT = 'default'
WINDOW_S = 8.0           # resend recent events each tick; receiver dedupes by id
TURN_IDLE_S = 8.0        # observer refreshes an open turn every 5 s
MAX_READ = 2 * 1024 * 1024
HEALTH_URL = 'http://HINDSIGHT_HOST:8888/health'
HEALTH_EVERY_S = 30.0


def _h(s):
    return hashlib.sha1(s.encode()).hexdigest()[:12]


class MemoryWatch:
    def __init__(self, path='/opt/data/holo/runtime-default.jsonl', health_url=HEALTH_URL):
        self.path = Path(path)
        self.pos = None
        self.buf = b''
        self.turns = {}          # turn_id -> {'last': ts, 'llm': bool}
        self.events = {}         # eid -> (from, to, at)
        self.health_url = health_url
        self.health_at = 0.0
        self.healthy = None

    def state_code(self, now):
        if self.health_url and now - self.health_at >= HEALTH_EVERY_S:
            self.health_at = now
            try:
                with urllib.request.urlopen(self.health_url, timeout=1.5) as r:
                    self.healthy = 200 <= r.status < 300
            except Exception:
                self.healthy = False
        if self.healthy is False:
            return 9
        recent = any(now - at <= 6 for _, _, at in self.events.values())
        return 3 if recent else 0          # READING while traffic flows, else IDLE

    def _rows(self):
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        if self.pos is None or size < self.pos:
            self.pos, self.buf = size, b''   # first sight / rotation: baseline, no flood
            return []
        if size == self.pos:
            return []
        with open(self.path, 'rb') as f:
            f.seek(self.pos)
            data = f.read(min(MAX_READ, size - self.pos))
        self.pos += len(data)
        data = self.buf + data
        lines = data.split(b'\n')
        self.buf = lines.pop()
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def _add(self, kind, how, key, now):
        eid = 'mem.%s.%s.%s' % (kind, how, _h(key))
        if eid in self.events:
            return
        pair = (ROOT, NODE) if kind == 'retain' else (NODE, ROOT)
        self.events[eid] = (pair[0], pair[1], now)

    def poll(self, now=None):
        now = time.time() if now is None else now
        for r in self._rows():
            if not isinstance(r, dict) or r.get('root_id') != ROOT:
                continue
            ev, tool, turn = r.get('event'), r.get('tool_name'), r.get('turn_id')
            if isinstance(turn, str):
                t = self.turns.setdefault(turn, {'last': now, 'llm': False, 'done': False})
                t['last'] = now
                if ev == 'pre_llm_call' and not t['llm']:
                    t['llm'] = True
                    self._add('recall', 'auto', turn, now)
            if ev == 'pre_tool_call' and tool == 'hindsight_retain':
                self._add('retain', 'tool', str(r.get('tool_call_id') or r.get('observed_at')), now)
            if ev == 'post_tool_call' and tool in ('hindsight_recall', 'hindsight_reflect'):
                self._add('recall', 'tool', str(r.get('tool_call_id') or r.get('observed_at')), now)
        for turn, t in list(self.turns.items()):
            if now - t['last'] > TURN_IDLE_S:
                if t['llm'] and not t['done']:
                    self._add('retain', 'auto', turn, now)
                    t['done'] = True
                if now - t['last'] > 600:
                    del self.turns[turn]
        self.events = {k: v for k, v in self.events.items() if 0 <= now - v[2] <= WINDOW_S}
        return dict(self.events)


def add_node(wire, code):
    """Append the hindsight node to the M and F lines of a bridge wire chunk."""
    lines = wire.split('\n')
    out = []
    for line in lines:
        if line.startswith('M|'):
            p, ts, body = line.split('|', 2)
            if 'default' not in [x.split(',')[0] for x in body.split(';')] if body else True:
                return wire
            line = '%s|%s|%s' % (p, ts, body + ';' + ','.join((NODE, '', LABEL)))
        elif line.startswith('F|'):
            p, ts, body = line.split('|', 2)
            line = '%s|%s|%s' % (p, ts, body + ',%s=%d' % (NODE, code))
        out.append(line)
    return '\n'.join(out)


def merge_e(bot_line, mem_events, now):
    """One E line per tick (transport keeps only the latest): bot hops + memory."""
    entries = []
    if bot_line:
        body = bot_line.rstrip('\n').split('|', 2)[2]
        entries = [e for e in body.split(';') if e]
    mem = sorted(mem_events.items(), key=lambda kv: kv[1][2])
    entries += [','.join((quote(f, safe=''), quote(t, safe=''), quote(eid, safe=''), str(int(at * 1000))))
                for eid, (f, t, at) in mem]
    entries = entries[-24:]
    if not entries:
        return ''
    line = 'E|%d|%s\n' % (int(now), ';'.join(entries))
    while len(line.encode('ascii')) > 4096 and entries:
        entries = entries[1:]
        line = 'E|%d|%s\n' % (int(now), ';'.join(entries))
    return line if entries else ''
