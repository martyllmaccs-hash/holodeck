// Pure renderer model shared verbatim by QML and Node offline checks.
// Freshness policy: local 30 s; VPS 180 s; future tolerance 30 s.
function number(v) { return typeof v === 'number' && isFinite(v) && v >= 0 ? v : null; }
function breathScale(alive, working, state, beat) {
  if(alive!==true || ['UNKNOWN','UNLINKED','OFFLINE'].indexOf(state)>=0)return 1;
  return 1+(working?0.035:0.012)*beat;
}
// One traversal per communication event, never a looping activity simulation.
function pulseProgress(event, now) {
  if(!event || event.active!==true || typeof event.eventId!=='string' || !event.eventId.length || number(event.eventAt)===null)return null;
  var age=now-event.eventAt;
  return age>=0 && age<6 ? age/6 : null;
}
function boolean(v) { return typeof v === 'boolean' ? v : null; }
function key(machine, id) { return JSON.stringify([machine, id]); }
function validData(d) {
  if (!d || typeof d !== 'object' || !Array.isArray(d.nodes)) return false;
  for (var i=0;i<d.nodes.length;i++) {
    var n=d.nodes[i];
    if (!n || typeof n !== 'object' || typeof n.id !== 'string' || !n.id.length || (n.machine !== undefined && n.machine !== 'p1' && n.machine !== 'vps')) return false;
  }
  return true;
}
function stampAge(ts, now) { return number(ts) !== null && ts > 0 && ts <= now+30 ? Math.max(0,now-ts) : -1; }
function elapsed(s, now) { return s && number(s.receivedAt)!==null ? Math.max(0,now-s.receivedAt) : Infinity; }
function localAge(s, now) {
  if (!s) return -1;
  var d=s.data || {};
  // Explicit invalid timestamps fail closed; untimestamped legacy files use
  // the time of the last changed payload, NOT repeated successful cat reads.
  var names=['ts','timestamp','generated_at','collected_at','fleet_ts'];
  for(var i=0;i<names.length;i++) if(d[names[i]]!==undefined) return stampAge(d[names[i]],now);
  return elapsed(s,now);
}
var wireStates=['IDLE','THINKING','BUILDING','READING','SEARCHING','RUNNING','DELEGATING','LISTENING','REPORTING','OFFLINE','UNLINKED'];
function isWorking(st) {
  return (typeof st==='number' && st>=1 && st<=8 && Math.floor(st)===st) || ['ACTIVE','TOOLING','THINKING','BUILDING','READING','SEARCHING','RUNNING','LISTENING','DELEGATING','REPORTING','WORKING','RESPONDING','WAITING_TOOL'].indexOf(st)>=0;
}
function ingest(text, prior, fromBeacon, now, exitOk) {
  var d=null; try { d=JSON.parse(text); } catch(e) {}
  var ok=exitOk && validData(d) && (!fromBeacon || stampAge(d.beacon_ts,now)>=0);
  if(!ok) return {data:fromBeacon?null:(prior?prior.data:null),receivedAt:prior?prior.receivedAt:now,valid:false,text:!fromBeacon && prior ? prior.text : null};
  return {data:d,receivedAt:prior && prior.text===text ? prior.receivedAt : now,valid:true,text:text};
}
function build(fleet, beacon, now, screenWidth) {
  var fd=fleet && validData(fleet.data) ? fleet.data : {nodes:[]};
  var bd=beacon && beacon.valid && validData(beacon.data) ? beacon.data : null;
  var ba=bd ? stampAge(bd.beacon_ts,now) : -1;
  var remoteFresh=ba>=0 && ba<=180;
  var fa=localAge(fleet,now), localFresh=!!(fleet && fleet.valid && fa>=0 && fa<=30);
  var nodes=[], seen={}, collisions={}, out=[], links=[], omitted=0;
  function add(n,m,fresh,snapshot) {
    fresh=fresh && n.stale!==true;
    m=n.machine || m;
    var k=key(m,n.id);
    if(seen[k]) { collisions[k]=true; return; }
    var st=fresh ? n.state : 'UNKNOWN';
    if(typeof st==='number' && Math.floor(st)===st && st>=0 && st<=10) st=wireStates[st];
    if(st==='STANDBY') st='IDLE';
    var knownState=typeof st==='string' && ['IDLE','OFFLINE','UNLINKED','UNKNOWN'].indexOf(st)>=0 || isWorking(st);
    if(!knownState) st='UNKNOWN';
    var ti=number(n.tokens_in),to=number(n.tokens_out);
    var item={id:n.id,key:k,machine:m,label:typeof n.label==='string'?n.label:n.id,
      word:fresh && st!=='UNKNOWN' ? (typeof n.word==='string'?n.word:(typeof st==='number'?'STATE '+st:st)) : 'UNKNOWN',
      state:typeof st==='number'?'WORKING':st,working:isWorking(st),detail:fresh?(typeof n.detail==='string'?n.detail:''):'LOCAL STATE UNAVAILABLE',
      role:n.kind==='leaf'?'LEAF':(typeof n.role==='string'?n.role:''),kind:n.kind,parent_id:typeof n.parent_id==='string'?n.parent_id:null,ageS:fresh && number(n.age_s)!==null ? n.age_s+(m==='vps'?ba:fa) : -1,
      tokens:fresh && ti!==null && to!==null ? ti+to : null,
      calls5h:fresh?number(n.calls_5h):null,
      apiCalls:fresh?number(n.api_calls):null,
      alive:fresh?boolean(n.alive):null,lease:fresh?boolean(n.lease):null,flash:0};
    seen[k]=item; nodes.push(item);
  }
  for(var i=0;i<fd.nodes.length;i++) if(fd.nodes[i].machine!=='vps') add(fd.nodes[i],'p1',localFresh,fleet);
  // The standalone beacon is authoritative: never resurrect deleted merged VPS rows.
  if(remoteFresh) for(i=0;i<bd.nodes.length;i++) if(!bd.nodes[i].machine || bd.nodes[i].machine==='vps') add(bd.nodes[i],'vps',true,beacon);
  nodes=nodes.filter(function(n){return !collisions[n.key];});
  if(!remoteFresh || !nodes.some(function(n){return n.machine==='vps' && n.id==='default';})) {
    var lana={id:'default',key:key('vps','default'),machine:'vps',label:'LANA',word:'UNLINKED',state:'UNLINKED',working:false,
      detail:'REMOTE STATE UNAVAILABLE',role:'ORCHESTRATOR',ageS:ba,alive:null,lease:null,tokens:null,apiCalls:null,flash:0};
    nodes.push(lana);
  }
  var vps=[],p1=[],leaves=[];
  nodes.forEach(function(n){if(n.kind==='leaf')leaves.push(n);if(n.machine==='vps')vps.push(n);else p1.push(n);});
  function byId(a,b){return a.key<b.key?-1:a.key>b.key?1:0;}
  vps.sort(byId);p1.sort(byId);
  var vo=null,vs=null,po=null;
  vps.forEach(function(n){if(n.id==='default')vo=n;else if(n.id==='orchestrator')vs=n;});
  p1.forEach(function(n){if(n.id==='p1-mila')po=n;});
  if(!po) p1.forEach(function(n){if(!po&&(n.role==='ORCHESTRATOR'||n.kind==='orchestrator'))po=n;});
  function grid(group,left) {
    if(!group.length)return;
    var cols=Math.max(2,Math.ceil(Math.sqrt(group.length*130*640/(320*860))));
    var rows=Math.ceil(group.length/cols);
    var scale=Math.min(1,640/(cols*320),860/(rows*130));
    group.forEach(function(n,i){
      n.x=left+(i%cols)*320*scale;n.y=160+Math.floor(i/cols)*130*scale;
      n.disc=n.kind==='orchestrator'?54:44;n.layoutScale=scale;
      n.layoutWidth=320*scale;n.layoutHeight=130*scale;
      n.role=n.role||(n.kind==='leaf'?'LEAF':'WORKER');out.push(n);
    });
  }
  grid(vps,20);grid(p1,1260);
  // Sphere centres: Lana takes Architect's original slot; Mila mirrors her.
  // Swap Architect into Lana's former slot to avoid overlapping identities.
  var architect = null;
  vps.forEach(function(n){if(n.id==='architect')architect=n;});
  if(vo) {
    var oldX=vo.x, oldY=vo.y;
    vo.x=340; vo.y=160; vo.layoutScale=1; vo.disc=54*1.5;
    if(architect){architect.x=oldX;architect.y=oldY;}
    if(po){
      var width=number(screenWidth) || 1920;
      po.layoutScale=1;po.disc=54*1.25;
      po.x=width-(vo.x+55)-55;po.y=vo.y;
    }
  }
  // Ordered parabolic fans, mirrored about the actual screen midpoint.
  var fanWidth=number(screenWidth) || 1920;
  function fan(ids,machine,mirror) {
    ids.forEach(function(id,i){
      var n=out.filter(function(item){return item.machine===machine && item.id===id;})[0];
      if(!n)return;
      var u=ids.length>1?i/(ids.length-1):0;
      // Broad quadratic sweep with evenly spaced heights, not a narrow diagonal.
      var branchSpan=Math.min(260,fanWidth*0.14);
      var centreX=80+branchSpan*Math.pow(1-u,2);
      var centreY=400+550*u;
      n.layoutScale=1;n.disc=44;n.labelOnLeft=mirror;
      if(mirror)centreX=fanWidth-centreX;
      n.x=centreX-(mirror?245:55);n.y=centreY-55;
    });
  }
  fan(['researcher','analyst','architect','auditor','librarian','playroom'],'vps',false);
  fan(['staff1','staff2','staff3','staff4'],'p1',true);
  var byKey=Object.create(null), byBare=Object.create(null), edgePairs=Object.create(null), handoffs=[], particles=[], eventIds=Object.create(null);
  out.forEach(function(n){byKey[n.key]=n;(byBare[n.id]||(byBare[n.id]=[])).push(n);});
  function resolve(value,machine) {
    if(value && typeof value==='object') {machine=value.machine;value=value.id;}
    if(typeof value!=='string')return null;
    if(machine!==undefined)return byKey[key(machine,value)]||null;
    if(byKey[value])return byKey[value];
    return byBare[value] && byBare[value].length===1 ? byBare[value][0] : null;
  }
  function pair(a,b){return JSON.stringify([a.key,b.key].sort());}
  function edge(a,b,active,inferred,source) {
    if(!a||!b||a===b||!byKey[a.key]||!byKey[b.key])return;
    var p=pair(a,b);
    if(inferred && edgePairs[p])return;
    if(!inferred)edgePairs[p]=true;
    links.push({fromId:a.key,toId:b.key,active:!!active,inferred:!!inferred,source:source,crossMachine:a.machine!==b.machine});
  }
  function records(s,fresh,source) {
    if(!fresh||!s)return;
    var d=s.data;
    function consume(rows,isHandoff) {
      if(!Array.isArray(rows))return;
      rows.forEach(function(e){
        if(!e||typeof e!=='object')return;
        if(e.stale===true)return;
        // Fleet contains collector-merged remote records; standalone beacon owns them.
        if(source==='fleet' && e.machine==='vps')return;
        var a=resolve(e.from!==undefined?e.from:(e.fromId!==undefined?e.fromId:e.from_id),e.from_machine!==undefined?e.from_machine:e.machine);
        var b=resolve(e.to!==undefined?e.to:(e.toId!==undefined?e.toId:e.to_id),e.to_machine!==undefined?e.to_machine:e.machine);
        if(source==='fleet' && a && b && a.machine==='vps' && b.machine==='vps')return;
        if(!a||!b||a.state==='UNKNOWN'||a.state==='UNLINKED'||b.state==='UNKNOWN'||b.state==='UNLINKED')return;
        var age=-1, delay=source==='beacon'?ba:fa;
        var at=e.at!==undefined?e.at:e.ts;
        if(at!==undefined) {
          age=stampAge(at,now);
          if(number(at)===null || at>now || at>now-delay)age=-1;
          // age_s is rounded to tenths by the collector. Contradictions fail closed.
          if(e.age_s!==undefined && (number(e.age_s)===null || Math.abs((now-delay-at)-e.age_s)>1))age=-1;
          if(e.at!==undefined && e.ts!==undefined && (number(e.ts)===null || Math.abs(e.ts-e.at)>1))age=-1;
        } else if(number(e.age_s)!==null) age=e.age_s+delay;
        var inferred=e.derived===true || e.from_confirmed===false || e.inferred===true || e.source==='user_message';
        // Local collector links reflect worker message recency, not sender communication.
        if(isHandoff ? !(e.derived===false || e.from_confirmed===true) : e.from_confirmed!==true)inferred=true;
        var active=(isHandoff || !inferred && e.active===true) && age>=0 && age<6;
        edge(a,b,active,inferred,e.source || (isHandoff?'handoff':'collector'));
        if(isHandoff){
          handoffs.push(e);
          if(active && number(e.at)!==null &&
             typeof e.from==='string' && e.from===a.id && typeof e.to==='string' && e.to===b.id &&
             (e.from_machine==='p1'||e.from_machine==='vps') && (e.to_machine==='p1'||e.to_machine==='vps') &&
             a!==b) {
            var particleId=typeof e.id==='string' && e.id.length ? e.id : JSON.stringify([e.at,a.key,b.key]);
            var signature=JSON.stringify([e.at,a.key,b.key]);
            if(eventIds[particleId]) {
              if(eventIds[particleId]!==signature)eventIds[particleId]='conflict';
            } else {
              eventIds[particleId]=signature;
              particles.push({eventId:particleId,eventAt:e.at,fromId:a.key,toId:b.key,active:true,inferred:inferred,crossMachine:a.machine!==b.machine});
            }
          }
        }
      });
    }
    consume(d.links,false);consume(d.handoffs,true);
  }
  records(fleet,localFresh,'fleet');records(beacon,remoteFresh,'beacon');
  particles=particles.filter(function(p){return eventIds[p.eventId]!=='conflict';});
  particles.forEach(function(p){var b=byKey[p.toId];b.flash=Math.max(b.flash,(6-(now-p.eventAt))/6);});
  // Layout relationships are explanatory only: no activity is inferred from words,
  // alive/lease booleans, or leaf membership. Solid topology styling is display-only.
  if(vo)out.forEach(function(n){if(n.machine==='vps'&&n!==vo&&['researcher','analyst','architect','auditor','librarian','playroom'].indexOf(n.id)>=0)edge(vo,n,false,true,'layout');});
  if(po)out.forEach(function(n){if(n.machine==='p1'&&n!==po&&n.role==='WORKER')edge(po,n,false,true,'inferred');});
  leaves.forEach(function(n){if(byKey[n.key])edge(resolve(n.parent_id,n.machine),n,false,true,'inferred');});
  edge(vo,po,false,true,'inferred');
  var online=0,working=0,tokens=0,total=0,leafCount=0,unknownOnline=false,unknownTokens=false,unknownWorking=false;
  out.forEach(function(n){if(n.role==='LEAF'){leafCount++;return;}total++;if(n.alive===null)unknownOnline=true;else if(n.alive)online++;
    if(n.state==='UNKNOWN'||n.state==='UNLINKED')unknownWorking=true;else if(n.working)working++;
    if(n.tokens===null)unknownTokens=true;else tokens+=n.tokens;});
  return {view:out,links:links,particles:particles,handoffs:handoffs.slice(0,5),beaconAge:ba,vpsStale:!remoteFresh,localFresh:localFresh,omitted:omitted,collisions:Object.keys(collisions).length,
    totals:{nodes_online:unknownOnline?null:online,nodes_total:total,working:working,working_unknown:unknownWorking,tokens_today:unknownTokens?null:tokens,leaves_running:leafCount,handoffs_today:null}};
}
