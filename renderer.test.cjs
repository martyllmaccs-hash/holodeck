const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const R = vm.createContext({});
vm.runInContext(fs.readFileSync(__dirname + '/Renderer.js', 'utf8'), R);
function node(id, machine, extra={}) { return {id,machine,state:'IDLE',alive:true,...extra}; }
function model(handoffs=[], nodes=[], now=1000, remote=[]) {
  const fleet={valid:true,receivedAt:1000,data:{ts:1000,nodes:[node('p1-mila','p1'),...nodes],handoffs}};
  const beacon={valid:true,receivedAt:1000,data:{beacon_ts:1000,nodes:[node('default','vps'),...remote]}};
  return R.build(fleet,beacon,now,1920);
}
const event = (extra={}) => ({id:'actual-session:report:1',at:998,from:'default',to:'p1-mila',from_machine:'vps',to_machine:'p1',derived:false,...extra});
test('confirmed unique event produces one directional event-timed particle', () => {
  const m=model([event(),event()]);
  assert.equal(m.particles.length,1);
  assert.equal(m.particles[0].eventId,event().id);
  assert.equal(m.particles[0].fromId,R.key('vps','default'));
  assert.equal(m.particles[0].toId,R.key('p1','p1-mila'));
  assert.equal(R.pulseProgress(m.particles[0],1000),2/6);
  assert.equal(R.pulseProgress(m.particles[0],1001),3/6);
  assert.equal(R.pulseProgress(m.particles[0],1004),null);
});
test('leaf topology follows same-machine parent_id, including completed reporting child', () => {
  const leaf=node('child','p1',{kind:'leaf',parent_id:'staff2',state:'OFFLINE',alive:false});
  const m=model([event({from:'child',to:'staff2',from_machine:'p1',id:'return'})],[leaf,node('staff2','p1')]);
  const n=m.view.find(n=>n.id==='child');
  assert.equal(n.parent_id,'staff2');
  const edge=m.links.find(e=>e.inferred && e.toId===n.key);
  // A confirmed return may suppress the explanatory edge for this same pair.
  const topology=model([],[leaf,node('staff2','p1')]).links.find(e=>e.toId===n.key);
  assert.equal(topology.fromId,R.key('p1','staff2'));
  assert.equal(m.particles[0].fromId,n.key);
  assert.equal(m.particles[0].toId,R.key('p1','staff2'));
  assert.equal(model([],[node('orphan','p1',{kind:'leaf'})]).links.some(e=>e.toId===R.key('p1','orphan')),false);
});
test('QML consumes event particles using wall time, not shared looping phase', () => {
  const qml=fs.readFileSync(__dirname+'/shell.qml','utf8');
  assert.match(qml,/root\.particleView = root\.pulseState\.particles/);
  assert.match(qml,/model: root\.particleView/);
  assert.match(qml,/Renderer\.pulseProgress\((?:modelData|evt), root\.pulseNow\)/);
  assert.doesNotMatch(qml,/root\.pulseT/);
  const a=model([event(),event({id:'second',at:999})]).particles;
  assert.notEqual(R.pulseProgress(a[0],1000),R.pulseProgress(a[1],1000));
});
test('particles fail closed without explicit from/to contract or on conflicting event identity', () => {
  assert.equal(model([event({from:undefined,fromId:'default'})]).particles.length,0);
  assert.equal(model([event(),event({at:999})]).particles.length,0);
});
test('freshness, malformed events, and inferred topology never create traffic', () => {
  for(const extra of [{at:undefined,age_s:2},{from_machine:undefined},{to_machine:undefined},
    {at:1001},{at:994},{stale:true},{from:'missing'},{at:998,age_s:100}]) {
    assert.equal(model([event(extra)]).particles.length,0,JSON.stringify(extra));
  }
  assert.equal(model([event()],[],1031).particles.length,0);
  assert.equal(model([],[node('child','p1',{kind:'leaf',parent_id:'p1-mila',state:'REPORTING'})]).particles.length,0);
  assert.equal(R.pulseProgress(model([event()]).particles[0],997),null);
});
test('message-derived and inferred communications animate when fresh and resolvable', () => {
  for(const extra of [{derived:true,source:'user_message',from_confirmed:false},
    {inferred:true,source:'user_message'}, {id:undefined,derived:true,source:'user_message'}]) {
    const m=model([event(extra)]);
    assert.equal(m.particles.length,1,JSON.stringify(extra));
    assert.equal(m.particles[0].inferred,true);
    assert.equal(R.pulseProgress(m.particles[0],1000),2/6);
  }
  assert.equal(model([event({derived:true,source:'user_message'}) ,event({derived:true,source:'user_message'})]).particles.length,1);
});
test('node data carries rolling calls separately from the existing TOK display', () => {
  const m=model([], [node('worker','p1',{tokens_in:1200,tokens_out:300,calls_5h:2})]);
  const worker=m.view.find(n=>n.id==='worker');
  assert.equal(worker.tokens,1500);
  assert.equal(worker.calls5h,2);
  const qml=fs.readFileSync(__dirname+'/HoloNode.qml','utf8');
  assert.match(qml,/node\.calls5h \+ "\/5H CALLS"/);
  assert.match(qml,/node\.tokens \/ 1000/);
});

test('delegation and reporting follow explicit direction; identical IDs stay machine scoped', () => {
  const nodes=[node('staff2','p1'),node('child','p1',{kind:'leaf',parent_id:'staff2'})];
  const down=event({id:'delegate',from:'staff2',to:'child',from_machine:'p1',to_machine:'p1',at:999});
  const up=event({id:'report',from:'child',to:'staff2',from_machine:'p1',to_machine:'p1'});
  const m=model([down,up],nodes,1000,[node('child','vps',{kind:'leaf',parent_id:'default'})]);
  assert.equal(m.particles.length,2);
  assert.equal(m.particles[0].fromId,R.key('p1','staff2'));
  assert.equal(m.particles[0].toId,R.key('p1','child'));
  assert.equal(m.particles[1].fromId,R.key('p1','child'));
  assert.equal(m.particles[1].toId,R.key('p1','staff2'));
  const topology=model([],nodes,1000,[node('child','vps',{kind:'leaf',parent_id:'default'})]).links;
  assert.equal(topology.find(e=>e.toId===R.key('vps','child')).fromId,R.key('vps','default'));
  assert.equal(model([up],nodes,1004).particles.length,0);
  assert.equal(model([up],nodes.filter(n=>n.id!=='child')).particles.length,0);
});
