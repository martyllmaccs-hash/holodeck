#!/usr/bin/env python3
"""Isolated metadata bridge candidate; stdout is existing M/F wire only."""
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
from urllib.parse import quote

TOKEN = re.compile(r'[A-Za-z0-9_.:-]{1,64}\Z')
LABEL = re.compile(r'[A-Za-z0-9 _.:/-]{1,64}\Z')

class Tracker:
    def __init__(self, ttl=30):
        self.ttl = ttl
        self.turns = {}
        self.children = {}
        self.unknown = {}
        self.diagnostics = []
        self.unknown_turns = {}
        self.child_seen = {}
        self.ended = {}
        self.handoffs = []
        self.reporting = {}

    def note(self, node, reason):
        self.diagnostics.append({'node':node, 'reason':reason, 'lifecycle':'unknown'})
        del self.diagnostics[:-128]

    def accept(self, row, roots, *, now):
        events = {'pre_llm_call','on_session_end','pre_tool_call','post_tool_call',
                  'subagent_start','subagent_stop','api_request_error','execution_refresh'}
        if not isinstance(row, dict) or row.get('schema') != 'holo.runtime.v1' or not isinstance(row.get('event'),str) or row.get('event') not in events:
            return False
        root, node, event, ts = (row.get(k) for k in ('root_id','node_id','event','observed_at'))
        if not isinstance(root,str) or root not in roots or not isinstance(node,str) or not TOKEN.fullmatch(node):
            return False
        if isinstance(ts,bool) or not isinstance(ts,(float,int)) or not math.isfinite(ts) or ts < 0 or ts > now+5:
            return False
        identifier = re.compile(r'[A-Za-z0-9_.:-]{1,128}\Z')
        for k in ('session_id','turn_id','tool_call_id','tool_name','child_session_id','parent_session_id'):
            if k in row and (not isinstance(row[k],str) or not identifier.fullmatch(row[k])):
                return False
        session = row.get('child_session_id') if event.startswith('subagent_') else row.get('session_id')
        if not session:
            return False
        child = node != root
        if event.startswith('subagent_') and not child:
            return False
        parent = row.get('parent_node_id')
        if parent is not None and (not isinstance(parent,str) or not TOKEN.fullmatch(parent)):
            return False
        if child:
            if node != root+':child:'+session:
                return False
            if parent is None:
                parent = self.children.get(node)
            if parent != root and parent not in self.children:
                self.note(root, 'unobservable_parent_edge')
                return False
            if parent == node or (parent != root and not parent.startswith(root+':child:')):
                return False
            ancestor = parent
            seen = {node}
            while ancestor in self.children:
                if ancestor in seen:
                    return False
                seen.add(ancestor)
                ancestor = self.children[ancestor]
        elif parent:
            return False
        turn = row.get('turn_id')
        if not turn and isinstance(session, str) and session.startswith('local-'):
            # One-shot `hermes chat -q` sessions (source oneshot, ids local-...) carry no
            # turn_id since 7 Nov 2026; such a session is exactly one turn.
            turn = 'oneshot'
        key = (root, session, turn)
        if event in {'pre_llm_call','pre_tool_call','post_tool_call','on_session_end','api_request_error','execution_refresh'} and not turn:
            return False
        if event == 'execution_refresh' and row.get('execution_evidence') != 'host_turn_context':
            return False
        if event == 'on_session_end' and (not isinstance(row.get('outcome'),str) or row.get('outcome') not in {'completed','failed','cancelled','incomplete'}):
            return False
        if event in {'pre_tool_call','post_tool_call'} and not row.get('tool_call_id'):
            return False
        if event == 'execution_refresh':
            # Refresh is never a start, terminal or resurrection. Retain exact
            # concurrent tool states; writer observation time alone renews lease.
            if key in self.turns and key not in self.ended:
                self.turns[key]['ts'] = max(ts, self.turns[key]['ts'])
                if child: self.child_seen[node] = max(ts, self.child_seen.get(node, 0))
            return True
        if child and event not in {'subagent_stop','on_session_end'}:
            if len(self.children) >= 48 and node not in self.children:
                self.note(root, 'child_capacity_unknown')
                self.unknown[root] = 'child_capacity_unknown'
                return False
            self.children[node] = parent
            self.child_seen[node] = max(ts, self.child_seen.get(node,0))
        if event == 'subagent_stop':
            if row.get('child_status') == 'completed':
                self.children[node] = parent
                self.child_seen[node] = ts
                machine = 'p1' if root == 'p1-mila' else 'vps'
                eid = f'native:{node}:report:{ts}'
                if not any(e['id'] == eid for e in self.handoffs):
                    self.handoffs.append({'id': eid, 'from': node, 'to': parent,
                        'at': ts, 'derived': False, 'from_confirmed': True,
                        'source': 'native-subagent', 'status': 'completed',
                        'machine': machine, 'from_machine': machine, 'to_machine': machine})
                self.handoffs = self.handoffs[-128:]
                self.reporting[node] = ts
            for k in list(self.turns):
                if k[:2] == (root,session):
                    self.turns.pop(k)
            for k in list(self.unknown_turns):
                if k[:2] == (root,session): self.unknown_turns.pop(k)
            if node not in self.reporting: self.child_seen.pop(node,None)
            self.prune_children()
        elif event == 'on_session_end':
            self.turns.pop(key,None)
            self.unknown_turns.pop(key,None)
            self.ended[key] = ts
            if len(self.ended)>2048: self.ended.pop(next(iter(self.ended)))
            if child and not any(v['node']==node for v in self.turns.values()):
                self.child_seen.pop(node,None)
                self.prune_children()
        elif event == 'subagent_start':
            machine = 'p1' if root == 'p1-mila' else 'vps'
            eid = f'native:{node}:dispatch:{ts}'
            if not any(e['id'] == eid for e in self.handoffs):
                self.handoffs.append({'id': eid, 'from': parent, 'to': node,
                    'at': ts, 'derived': False, 'from_confirmed': True,
                    'source': 'native-subagent', 'status': 'dispatched',
                    'machine': machine, 'from_machine': machine, 'to_machine': machine})
            self.handoffs = self.handoffs[-128:]
        elif event in {'pre_llm_call','pre_tool_call'}:
            if ts <= self.ended.get(key,-1): return True
            if len(self.turns) >= 2048 and key not in self.turns:
                self.unknown[root] = 'turn_capacity_unknown'
                self.note(root, 'turn_capacity_unknown')
                return False
            value = self.turns.setdefault(key, {'node':node,'ts':ts,'tools':{}})
            value['ts'] = max(ts,value['ts'])
            if event == 'pre_tool_call':
                if len(value['tools']) >= 128:
                    self.note(node, 'tool_capacity_unknown')
                    return False
                value['tools'][row['tool_call_id']] = row.get('tool_name','unknown')
        elif event in {'post_tool_call','api_request_error'}:
            if key in self.turns:
                if event == 'post_tool_call': self.turns[key]['tools'].pop(row['tool_call_id'],None)
                self.turns[key]['ts'] = max(ts,self.turns[key]['ts'])
            elif key not in self.ended:
                self.unknown_turns[key] = node
                if len(self.unknown_turns)>2048: self.unknown_turns.pop(next(iter(self.unknown_turns)))
                self.note(node, 'nonterminal_without_start')
        return True

    def prune_children(self):
        while True:
            dead = [node for node in self.children if node not in self.child_seen
                    and node not in self.children.values()]
            if not dead: break
            for node in dead: self.children.pop(node)

    def states(self, now):
        self.handoffs = [e for e in self.handoffs if 0 <= now-e['at'] < 6]
        for node, ts in list(self.reporting.items()):
            if now-ts >= 6:
                self.reporting.pop(node)
                self.child_seen.pop(node, None)
        for key,value in list(self.turns.items()):
            if now-value['ts'] > self.ttl:
                self.turns.pop(key)
                self.unknown_turns[key] = value['node']
                if len(self.unknown_turns)>2048: self.unknown_turns.pop(next(iter(self.unknown_turns)))
                self.note(value['node'], 'expired_without_terminal')
        for node,ts in list(self.child_seen.items()):
            if now-ts > self.ttl and not any(v['node']==node for v in self.turns.values()):
                self.child_seen.pop(node)
                self.note(node, 'expired_without_terminal')
        self.prune_children()
        # Lifecycle uncertainty remains diagnostics only. Expired activity is OFFLINE,
        # not UNLINKED: only source/transport health can produce code 10.
        sticky = {k:v for k,v in self.unknown.items() if v != 'expired_without_terminal'}
        self.unknown = sticky | {node:'expired_without_terminal' for node in self.unknown_turns.values()}
        states = {}
        for node in self.child_seen:
            states.setdefault(node, 1)
        tool_codes = {'read_file':3,'search_files':4,'web_search':4,'web_extract':3,
                      'terminal':5,'execute_code':5,'write_file':2,'patch':2,
                      'delegate_task':6}
        for value in self.turns.values():
            node = value['node']
            codes = [tool_codes.get(tool,5) for tool in value['tools'].values()]
            states[node] = max(states.get(node,1),max(codes,default=1))
        for node in self.reporting:
            states[node] = 8
        return states


class JsonlReader:
    """Read at most byte_budget per tick; never load the whole log or follow its symlink."""
    def __init__(self, path, byte_budget=65536, max_line=8192):
        self.path = Path(path)
        self.byte_budget = byte_budget
        self.max_line = max_line
        self.offset = 0
        self.identity = None
        self.pending = b''
        self.drain = False
        self.status = 'missing'
        self.errors = 0
        self.gap = False
        self.caught_up = False

    def poll(self):
        self.gap = False
        rows = []
        self.caught_up = False
        fd = None
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode): raise OSError('not regular')
            identity = (info.st_dev,info.st_ino)
            if self.identity is not None and (identity != self.identity or info.st_size < self.offset):
                self.offset = 0
                self.pending = b''
                self.drain = False
                self.gap = True
            self.identity = identity
            os.lseek(fd,self.offset,os.SEEK_SET)
            data = os.read(fd,self.byte_budget)
            self.offset += len(data)
            parts = data.split(b'\n')
            for i,part in enumerate(parts):
                complete = i < len(parts)-1
                if self.drain:
                    if complete: self.drain = False
                    continue
                if len(self.pending)+len(part)>self.max_line:
                    self.errors += 1
                    self.pending = b''
                    self.drain = not complete
                    continue
                self.pending += part
                if not complete: continue
                raw,self.pending = self.pending,b''
                try:
                    row = json.loads(raw.decode('utf-8'), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
                    if not isinstance(row,dict): raise ValueError('not object')
                    rows.append(row)
                except (UnicodeError,ValueError,RecursionError):
                    self.errors += 1
            self.caught_up = self.offset >= os.fstat(fd).st_size and not self.pending and not self.drain
            self.status = 'connected'
        except FileNotFoundError:
            self.status = 'missing'
            self.gap = self.identity is not None
        except OSError:
            self.status = 'unavailable'
            self.gap = True
        finally:
            if fd is not None: os.close(fd)
        return rows


def load_inventory(path):
    """Same authoritative v2 registration predicate as producer; fail closed on DB read loss."""
    import sqlite3
    from contextlib import closing
    path = Path(path)
    if path.stat().st_size>65536 or path.is_symlink(): raise ValueError('inventory bound')
    data = json.loads(path.read_text())
    if not isinstance(data,dict) or data.get('v')!=2: raise ValueError('v2 inventory required')
    home = Path(data['registration_home'])
    labels = data.get('labels',{})
    if not home.is_absolute() or home.is_symlink() or not isinstance(labels,dict):
        raise ValueError('invalid registration home or labels')
    candidates = [('default',home)]
    profiles = home/'profiles'
    if profiles.is_symlink(): raise ValueError('symlink profiles')
    if profiles.is_dir():
        candidates.extend(sorted((p.name,p) for p in profiles.iterdir()
                                 if p.is_dir() and not p.is_symlink() and TOKEN.fullmatch(p.name)))
    if len(candidates)>256: raise ValueError('registration scan bound')
    nodes = []
    for name,directory in candidates:
        dbpath = directory/'state.db'
        if dbpath.is_symlink(): raise ValueError('symlink DB')
        if not dbpath.is_file(): continue
        try:
            with closing(sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True,timeout=.2)) as db:
                db.execute('PRAGMA query_only=ON')
                registered = db.execute("SELECT 1 FROM sessions WHERE title='Bot Chat' AND archived=0 AND profile_name=? AND source NOT IN ('tool','kanban','subagent') LIMIT 1",(name,)).fetchone()
            if registered:
                label = labels.get(name,'LANA' if name=='default' else name)
                if not isinstance(label,str) or not LABEL.fullmatch(label): raise ValueError('transport label whitelist')
                nodes.append({'id':name,'label':label,'db':str(dbpath),'parent':''})
        except sqlite3.Error as exc:
            raise ValueError('registration query unavailable') from exc
    if len(nodes)>64: raise ValueError('transport inventory bound')
    return nodes


def load_legacy(path='/opt/data/holo/producer.py'):
    spec = importlib.util.spec_from_file_location('holo_legacy_producer',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class Bridge:
    def __init__(self, events, *, ttl=30, legacy=('playroom',), legacy_status=None):
        self.tracker = Tracker(ttl)
        self.readers = {root:JsonlReader(path) for root,path in events.items()}
        self.legacy = set(legacy)
        self.legacy_status = legacy_status
        self.rejected = 0
        self.legacy_module = None

    def poll(self, nodes, *, now):
        roots = {node['id'] for node in nodes}
        t = self.tracker
        for mapping in (t.turns,t.unknown_turns,t.ended):
            for key in list(mapping):
                if key[0] not in roots: mapping.pop(key)
        for node in list(t.children):
            if not any(node.startswith(root+':child:') for root in roots):
                t.children.pop(node)
                t.child_seen.pop(node,None)
        t.unknown = {node:reason for node,reason in t.unknown.items()
                     if node in roots or node in t.children}
        unavailable = set()
        for root,reader in self.readers.items():
            if root not in roots: continue
            old_errors = reader.errors
            rows = reader.poll()
            if reader.gap or reader.errors>old_errors:
                for key,value in list(t.turns.items()):
                    if key[0] == root:
                        t.turns.pop(key)
                        t.unknown_turns[key] = value['node']
                        if len(t.unknown_turns)>2048: t.unknown_turns.pop(next(iter(t.unknown_turns)))
                        t.note(value['node'],'source_gap_without_terminal')
                for child in list(t.child_seen):
                    if child.startswith(root+':child:'):
                        t.child_seen.pop(child)
                        t.note(child,'source_gap_without_terminal')
                t.prune_children()
            for row in rows:
                if not t.accept(row, {root}, now=now):
                    self.rejected += 1
            if reader.status == 'unavailable' or (reader.status=='connected' and not reader.caught_up):
                unavailable.add(root)
                unavailable.update(node for node in t.children if node.startswith(root+':child:'))
        wire = make_frame(nodes,t,now=now,unavailable=unavailable)
        # Preserve existing Playroom classification, not its registration/layout.
        legacy_states = {}
        for node in nodes:
            if node['id'] in self.legacy and node['id'] not in self.readers:
                if self.legacy_status:
                    state = self.legacy_status(node,now)
                else:
                    if self.legacy_module is None: self.legacy_module = load_legacy()
                    state = self.legacy_module.read_status(node['db'],now=now,profile=node['id'])
                codes = {'STANDBY':0,'THINKING':1,'BUILDING':2,'READING':3,'SEARCHING':4,'RUNNING':5,
                         'DELEGATING':6,'LISTENING':7,'REPORTING':8,'OFFLINE':9,'UNLINKED':10}
                # Legacy no-heartbeat means unproven bot liveness, not lost source.
                legacy_states[quote(node['id'],safe='')] = codes[state] if state!='UNLINKED' else 9
        if legacy_states:
            manifest,frame,_ = wire.split('\n')
            prefix,ts,body = frame.split('|')
            fields=[]
            for field in body.split(','):
                node,code = field.rsplit('=',1)
                fields.append(node+'='+str(legacy_states.get(node,code)))
            wire=manifest+'\n'+prefix+'|'+ts+'|'+','.join(fields)+'\n'
        return wire


def make_frame(nodes, tracker, *, now=None, unavailable=()):
    now = time.time() if now is None else now
    states = tracker.states(now)
    entries = [(n['id'], '', n['label']) for n in nodes]
    ids = {n['id'] for n in nodes}
    for node, parent in tracker.children.items():
        if parent in ids:
            entries.append((node, parent, 'child'))
            ids.add(node)
    if len(entries) > 64:
        raise ValueError('transport node bound')
    for node, parent, label in entries:
        if not TOKEN.fullmatch(node) or (parent and not TOKEN.fullmatch(parent)) or not LABEL.fullmatch(label):
            raise ValueError('transport metadata whitelist')
    ts = int(now)
    manifest = ';'.join(','.join(quote(x, safe='') for x in row) for row in entries)
    frame = ','.join(f'{quote(node, safe="")}={10 if node in unavailable else states.get(node, 9)}'
                     for node, _, _ in entries)
    wire = f'M|{ts}|{manifest}\nF|{ts}|{frame}\n'
    if any(len(line.encode('ascii'))+1 > 4096 for line in wire.splitlines()):
        raise ValueError('transport line bound')
    return wire


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',type=Path,default=Path('/opt/data/holo/inventory.json'))
    parser.add_argument('--events',action='append',default=[],metavar='ROOT=/ABS/LOG.jsonl')
    parser.add_argument('--legacy-root',action='append',default=None)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--loop',action='store_true')
    mode.add_argument('--once',action='store_true')
    parser.add_argument('--interval',type=float,default=2)
    parser.add_argument('--ttl',type=float,default=30)
    args=parser.parse_args(argv)
    if not math.isfinite(args.interval) or not .05<=args.interval<=60:
        parser.error('interval must be in [.05,60]')
    if not math.isfinite(args.ttl) or not 1<=args.ttl<=3600:
        parser.error('ttl must be in [1,3600]')
    events={}
    for value in args.events:
        root,sep,path=value.partition('=')
        if not sep or not TOKEN.fullmatch(root) or not Path(path).is_absolute() or root in events:
            parser.error('events require unique exact ROOT=/absolute/path')
        events[root]=Path(path)
    if len(events)>64: parser.error('event source bound')
    legacy=args.legacy_root if args.legacy_root is not None else ['playroom']
    if any(not TOKEN.fullmatch(root) for root in legacy): parser.error('invalid legacy root')
    bridge=Bridge(events,ttl=args.ttl,legacy=legacy)
    last_diag=None
    try:
        while True:
            nodes=load_inventory(args.inventory)
            now=time.time()
            wire=bridge.poll(nodes,now=now)
            diag={'schema':'holo.bridge.diagnostics.v1','sources':{
                root:{'status':r.status,'caught_up':r.caught_up,'malformed':r.errors,
                      'coverage':'observer_events_only' if r.status=='connected' else 'unobserved'}
                for root,r in bridge.readers.items()},
                'unknown':bridge.tracker.unknown,'recent':bridge.tracker.diagnostics,
                'rejected':bridge.rejected}
            text=json.dumps(diag,separators=(',',':'),allow_nan=False)
            if text!=last_diag:
                print(text,file=sys.stderr,flush=True)
                last_diag=text
            print(wire,end='',flush=True)
            if not args.loop: return 0
            time.sleep(args.interval)
    except (BrokenPipeError,KeyboardInterrupt):
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'event':'bridge_source_unavailable','exception':type(exc).__name__}),file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':
    sys.exit(main())
