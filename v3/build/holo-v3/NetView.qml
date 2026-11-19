// One live neural net, GPU-cheap: nothing is repainted per frame.
//   the crisp net (pre-rendered) breathes: tiny scale + sway about its centre
//   spikes = pooled sprites running along the real edges, in cascades
//   flashes = pooled sprites on the node a spike lands on
//   off   (offline/unknown/absent)  still, no spikes
//   idle                            slow breathing, a rare lone spark
//   work                            faster breathing, spikes cascade; activity scales the rate
// burst(n) fires n cascades from the core (Hindsight recall/retain on Lana).
// The derpy one's eyes are a tiny Canvas repainted only when it blinks or glances.
import QtQuick

Item {
  id: net
  property var e
  property var box                     // Scene layers[e.layer + "_core"]
  property string mode: "off"
  property real activity: 0
  property real t: 0
  property string tint: "warm"
  readonly property var g: e.geo
  readonly property bool big: e.kind === "lana" || e.kind === "mila"
  readonly property int poolN: big ? 18 : 6
  readonly property int flashN: big ? 14 : 5
  readonly property string col: tint === "cool" ? "128,214,255" : tint === "rose" ? "255,168,158" : "255,179,92"

  x: box.x; y: box.y; width: box.w; height: box.h

  property var adj: []
  property var spikes: []
  property var flashes: []             // {i, at, s}
  property real amp: 0
  property real rate: 0
  property real nextSpawn: 0
  property real look: 0
  property real blinkAt: -10
  property real lastEyes: -10

  Component.onCompleted: {
    var a = []
    for (var i = 0; i < g.nodes.length; i++) a.push([])
    for (var k = 0; k < g.edges.length; k++) { a[g.edges[k][0]].push(g.edges[k][1]); a[g.edges[k][1]].push(g.edges[k][0]) }
    adj = a
  }

  Item {
    id: body
    anchors.fill: parent
    // breathing about the net's centre: GPU transform only
    transform: [
      Scale { origin.x: net.e.cx - net.box.x; origin.y: net.e.cy - net.box.y
              xScale: 1 + 0.012 * net.amp * Math.sin(net.t * (net.mode === "work" ? 1.9 : 0.8))
              yScale: 1 + 0.012 * net.amp * Math.sin(net.t * (net.mode === "work" ? 1.9 : 0.8) + 0.6) },
      Rotation { origin.x: net.e.cx - net.box.x; origin.y: net.e.cy - net.box.y
                 angle: 0.6 * net.amp * Math.sin(net.t * 0.37 + net.e.cx) }
    ]
    Image { anchors.fill: parent; source: Qt.resolvedUrl("assets/" + net.e.layer + "_core.png"); smooth: true }

    Repeater {
      id: flashPool
      model: net.flashN
      Image { source: Qt.resolvedUrl("assets/node_white.png"); width: 18; height: 18; visible: false; smooth: true }
    }
    Repeater {
      id: tailPool
      model: net.poolN
      Rectangle { height: 1.6; radius: 0.8; color: "#fffaeb"; visible: false; transformOrigin: Item.Left; antialiasing: true }
    }
    Repeater {
      id: headPool
      model: net.poolN
      Image { source: Qt.resolvedUrl("assets/node_white.png"); width: 11; height: 11; visible: false; smooth: true }
    }
    Canvas {
      id: eyes
      visible: !!net.g.eyes
      anchors.fill: parent
      onPaint: {
        var ctx = getContext("2d"); ctx.reset(); ctx.clearRect(0, 0, width, height)
        if (!net.g.eyes) return
        var bl = Math.max(0, 1 - Math.abs(net.t - net.blinkAt) / 0.12), R = [8.2, 5.5]
        for (var k = 0; k < 2; k++) {
          var E = net.g.eyes[k]
          ctx.save(); ctx.translate(E[0] - net.box.x, E[1] - net.box.y); ctx.scale(1, 1 - 0.85 * bl)
          ctx.beginPath(); ctx.arc(0, 0, R[k], 0, 6.283)
          ctx.strokeStyle = "rgba(" + net.col + ",0.95)"; ctx.lineWidth = 1.4; ctx.stroke()
          if (bl < 0.6) {
            ctx.beginPath(); ctx.arc(Math.cos(net.look) * R[k] * 0.45, Math.sin(net.look) * R[k] * 0.45, 2.2, 0, 6.283)
            ctx.fillStyle = "rgba(255,255,255,0.95)"; ctx.fill()
          }
          ctx.restore()
        }
      }
    }
  }

  function nx(i) { return g.nodes[i][0] - box.x }
  function ny(i) { return g.nodes[i][1] - box.y }
  function spawn(from, depth) {
    if (spikes.length >= poolN) return
    var list = adj[from]
    if (!list || !list.length) return
    spikes.push({a: from, b: list[Math.floor(Math.random() * list.length)], t0: t,
                 dur: (big ? 0.32 : 0.45) + Math.random() * 0.3, depth: depth})
  }
  function flash(i, s) {
    flashes.push({i: i, at: t, s: s})
    if (flashes.length > flashN) flashes.shift()
  }
  function burst(n) {
    for (var i = 0; i < n; i++) spawn(g.core[Math.floor(Math.random() * g.core.length)], 0)
    for (var c = 0; c < g.core.length && c < 6; c++) flash(g.core[c], 1)
  }

  // called by the root timer every 40 ms
  function step() {
    var target = mode === "work" ? (big ? 1.0 : 0.8) : mode === "idle" ? 0.45 : 0
    amp += (target - amp) * 0.04
    if (mode === "work" && t >= nextSpawn) {
      var r = (big ? 4 : 1.4) * (0.45 + 0.55 * activity)
      nextSpawn = t + (0.5 + Math.random()) / r
      spawn(big && Math.random() < 0.6 ? g.core[Math.floor(Math.random() * g.core.length)]
                                         : Math.floor(Math.random() * g.nodes.length), 0)
    } else if (mode === "idle" && t >= nextSpawn) {
      nextSpawn = t + 3 + Math.random() * 5
      spawn(Math.floor(Math.random() * g.nodes.length), 3)
    } else if (mode === "off" && t >= nextSpawn) nextSpawn = t + 1
    var keep = [], landed = []
    for (var k = 0; k < spikes.length; k++) {
      if (t - spikes[k].t0 < spikes[k].dur) keep.push(spikes[k]); else landed.push(spikes[k])
    }
    spikes = keep
    for (k = 0; k < landed.length; k++) {
      var s = landed[k]
      flash(s.b, mode === "work" ? 1 : 0.6)
      if (s.depth < 4 && Math.random() < (mode === "work" ? 0.62 : 0.4)) spawn(s.b, s.depth + 1)
      if (s.depth < 2 && mode === "work" && Math.random() < 0.25) spawn(s.b, s.depth + 1)
    }
    // push state to the pooled sprites
    for (k = 0; k < poolN; k++) {
      var h = headPool.itemAt(k), tl = tailPool.itemAt(k)
      if (!h || !tl) continue
      if (k >= spikes.length) { h.visible = false; tl.visible = false; continue }
      var sp = spikes[k], p = Math.min(1, (t - sp.t0) / sp.dur)
      var ax = nx(sp.a), ay = ny(sp.a), bx = nx(sp.b), by = ny(sp.b)
      var hx = ax + (bx - ax) * p, hy = ay + (by - ay) * p, q = Math.max(0, p - 0.35)
      var tx = ax + (bx - ax) * q, ty = ay + (by - ay) * q
      h.x = hx - 5.5; h.y = hy - 5.5; h.visible = true
      tl.x = tx; tl.y = ty - 0.8; tl.width = Math.max(0.1, Math.hypot(hx - tx, hy - ty))
      tl.rotation = Math.atan2(hy - ty, hx - tx) * 57.2958; tl.opacity = 0.8; tl.visible = true
    }
    var fl = []
    for (k = 0; k < flashes.length; k++) if (t - flashes[k].at < 0.6) fl.push(flashes[k])
    flashes = fl
    for (k = 0; k < flashN; k++) {
      var f = flashPool.itemAt(k)
      if (!f) continue
      if (k >= flashes.length) { f.visible = false; continue }
      var fe = flashes[k], age = (t - fe.at) / 0.6, sz = (big ? 20 : 15) * (1 + 0.4 * (1 - age))
      f.width = sz; f.height = sz; f.x = nx(fe.i) - sz / 2; f.y = ny(fe.i) - sz / 2
      f.opacity = fe.s * (1 - age) * (1 - age); f.visible = true
    }
    if (g.eyes && mode !== "off") {
      if (Math.random() < 0.006) blinkAt = t
      if (Math.random() < 0.01) { look = Math.random() * 6.283; eyes.requestPaint() }
      if (Math.abs(t - blinkAt) < 0.2) eyes.requestPaint()
    }
  }
  Timer { interval: 300; running: !!net.g.eyes; repeat: false; onTriggered: eyes.requestPaint() }
}
