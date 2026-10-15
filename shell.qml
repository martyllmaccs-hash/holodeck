// holo — the orchestration lattice: a holographic view of the agent fleet across both
// machines, live from the Hermes session stores. Non-interactive background layer (current live baseline).
//
// Data: ~/.local/state/holo/fleet.json (this machine, written by
// holo-collector.service) plus, when the local collector has not merged it yet,
// ~/.local/state/holo/beacon-vps.json (pushed from the runtime every minute).
//
// Every animation here is timer-driven. `SequentialAnimation on <property>` silently never
// ran in this Quickshell build, so motion comes from one 40 ms timer feeding wall time and
// `breathe`, which the items bind to.
import Quickshell
import Quickshell.Wayland
import Quickshell.Io
import QtQuick
import "Renderer.js" as Renderer
import "Drift.js" as Drift

ShellRoot {
  id: root

  readonly property string home: Quickshell.env("HOME")
  readonly property string stateDir: home + "/.local/state/holo/"
  readonly property string fleetPath: stateDir + "fleet.json"
  readonly property string beaconPath: stateDir + "beacon-vps.json"
  readonly property string assetDir: "file://" + home + "/.config/quickshell/holo/assets/"

  property var fleet: null
  property var beacon: null
  property var view: []
  property var linkView: []
  property var particleView: []
  property var pulseState: null
  property var handoffView: []
  property var totals: ({})
  property real beaconAge: -1
  property bool everRead: false
  property int badReads: 0
  property int rev: 0
  property real pulseNow: Date.now() / 1000 // one non-looping traversal per event timestamp
  property real breathe: 0           // 0..1, 1.7 s cycle — drives node breathing
  property real driftT: 0            // decorative drift, independent of reported activity
  property bool vpsStale: true
  property bool localFresh: false
  property int omitted: 0
  property int collisions: 0

  readonly property color cyan: "#7ff0ff"
  readonly property color dim: "#3d6f7d"

  function value(v) { return v === null || v === undefined ? "?" : v }
  // Pulse tint by event kind -- every colour already exists elsewhere in the
  // fleet's own palette (handoff = the standard cyan; a2a/message/smoke-test
  // get their own existing accent so the pulse stream reads apart by kind).
  function pulseColor(kind) {
    if (kind === "handoff") return root.cyan
    if (kind === "a2a") return "#d8f6ff"
    if (kind === "smoke_test") return "#2f7c8c"
    return "#a8f7ff"
  }

  // Read-only runtime proof: actual transformed centres versus drawn endpoints.
  IpcHandler {
    target: "drift"
    function sample(): string {
      var samples = []
      for (var i = 0; i < root.view.length; i++) {
        var n = root.view[i], item = nodeItems.itemAt(i)
        if (!item) continue
        var pt = item.mapToItem(canvas, n.labelOnLeft ? 245 : 55, 55)
        samples.push({key:n.key, x:item.x, y:item.y,
                      actual:[pt.x,pt.y], endpoint:[root.cx(n),root.cy(n)]})
      }
      return JSON.stringify({time:root.driftT,nodes:samples})
    }
    function pulses(): string {
      return JSON.stringify({now:root.pulseNow,particles:root.particleView.map(function(e){
        return {id:e.eventId,from:e.fromId,to:e.toId,progress:Renderer.pulseProgress(e,root.pulseNow),
                point:root.pulsePoint(e,Renderer.pulseProgress(e,root.pulseNow)||0)};
      })})
    }
    function sweep(): string {
      var now=root.pulseNow, evs=[];
      for(var i=0;i<root.linkView.length;i++){var l=root.linkView[i];
        evs.push({eventId:"sweep:"+now+":"+i,eventAt:now,active:true,fromId:l.fromId,toId:l.toId,kind:"smoke_test",crossMachine:!!l.crossMachine});}
      root.pulseState=Renderer.advancePulses(root.pulseState,evs,now,root.view.map(function(n){return n.key;}));
      root.particleView=root.pulseState.particles;
      return "fired "+evs.length+" links";
    }
    function probe(): string {
      var now=root.pulseNow, a=Renderer.key("vps","default"), b=Renderer.key("p1","p1-mila");
      var e={eventId:"visual-probe:"+now,eventAt:now-3,active:true,fromId:a,toId:b,kind:"smoke_test",crossMachine:true};
      root.pulseState=Renderer.advancePulses(root.pulseState,[e],now,root.view.map(function(n){return n.key;}));
      root.particleView=root.pulseState.particles;
      return e.eventId
    }
  }

  function ageStr(s) {
    if (s === null || s === undefined || s < 0) return "--"
    if (s < 90) return Math.round(s) + "S"
    if (s < 5400) return Math.round(s / 60) + "M"
    return (s / 3600).toFixed(1) + "H"
  }

  // Keep observed journeys; deleting an endpoint still deletes its effects.
  function ingest(text, fromBeacon, exitOk) {
    var snapshot = Renderer.ingest(text, fromBeacon ? root.beacon : root.fleet,
                                   fromBeacon, Date.now() / 1000, exitOk)
    if (!snapshot.valid) root.badReads++
    if (fromBeacon) root.beacon = snapshot
    else root.fleet = snapshot
    root.everRead = root.everRead || snapshot.valid
    root.rebuild()
  }
  function rebuild() {
    var result = Renderer.build(root.fleet, root.beacon, Date.now() / 1000, panel.width)
    root.view = result.view
    root.linkView = result.links
    root.pulseState = Renderer.advancePulses(root.pulseState, result.particles, root.pulseNow,
      result.view.map(function(n){return n.key;}))
    root.particleView = root.pulseState.particles
    root.handoffView = result.handoffs
    root.totals = result.totals
    root.beaconAge = result.beaconAge
    root.vpsStale = result.vpsStale
    root.localFresh = result.localFresh
    root.omitted = result.omitted
    root.collisions = result.collisions
    root.rev++
    canvas.requestPaint()
  }

  Process {
    id: fleetProc
    command: ["cat", root.fleetPath]
    stdout: StdioCollector { id: fleetOut }
    onExited: (exitCode, exitStatus) => root.ingest(fleetOut.text, false, exitCode === 0)
  }
  Process {
    id: beaconProc
    command: ["cat", root.beaconPath]
    stdout: StdioCollector { id: beaconOut }
    onExited: (exitCode, exitStatus) => root.ingest(beaconOut.text, true, exitCode === 0)
  }

  Timer {
    interval: 2000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: {
      if (!fleetProc.running) fleetProc.running = true
      if (!beaconProc.running) beaconProc.running = true
    }
  }
  Timer {
    interval: 40
    running: true
    repeat: true
    onTriggered: {
      root.pulseNow = Date.now() / 1000
      root.breathe = (root.breathe + 0.016 / 1.7) % 1.0
      root.driftT += 0.04
      canvas.requestPaint()
    }
  }
  Timer {
    interval: 1000
    running: true
    repeat: true
    onTriggered: root.rebuild()      // flash decay + beacon staleness keep moving
  }

  function nodeById(id) {
    for (var i = 0; i < root.view.length; i++) if (root.view[i].key === id) return root.view[i]
    return null
  }
  function drift(n) { return Drift.offset(n.key, root.driftT) }
  function nodeScale(n) {
    var i = root.view.indexOf(n)
    var beat = 0.5 + 0.5 * Math.sin((root.breathe + (i % 7) * 0.14) * 6.283185)
    return n.layoutScale * Renderer.breathScale(n.alive, n.working, n.state, beat, n.activity)
  }
  function cx(n) { return n.x + root.drift(n)[0] + (n.labelOnLeft ? 245 : 55) * root.nodeScale(n) }
  function cy(n) { return n.y + root.drift(n)[1] + 55 * root.nodeScale(n) }
  function linkControl(l, a, b) {
    if(l.peer || l.crossMachine) return [(root.cx(a)+root.cx(b))/2, -80]
    return [a.machine === "vps" ? 30 : panel.width-30, (root.cy(a)+root.cy(b))/2]
  }
  function pulsePoint(l, t) {
    var a = root.nodeById(l.fromId), b = root.nodeById(l.toId)
    if (!a || !b) return [0, 0]
    var x0 = root.cx(a), y0 = root.cy(a), x2 = root.cx(b), y2 = root.cy(b)
    var control = root.linkControl(l,a,b)
    var x1 = control[0], y1 = control[1]
    var u = 1 - t
    return [u * u * x0 + 2 * u * t * x1 + t * t * x2, u * u * y0 + 2 * u * t * y1 + t * t * y2]
  }

  // ================================================================ surface
  PanelWindow {
    id: panel

    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    exclusiveZone: 0
    implicitWidth: 1920
    implicitHeight: 1045

    // Background layer, the same slot the Soviet panel used: above the wallpaper,
    // behind every normal window, so it reads as a live desktop background rather
    // than an overlay sitting on top of the user's work.
    WlrLayershell.layer: WlrLayer.Background
    WlrLayershell.namespace: "holo"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    mask: Region {}

    // Martin's photo is the background; the live bot fleet remains layered above it.
    // Keep the photo clean: no galaxy, grid, stars, or scanline wash over the subject.
    Rectangle { anchors.fill: parent; color: "black" }
    Image {
      width: parent.width; height: parent.height
      x: -parent.width * 0.025; y: 0
      source: root.assetDir + "background.jpg"
      fillMode: Image.Stretch
      smooth: true
    }

    // ------------------------------------------------------------- links
    Canvas {
      id: canvas
      anchors.fill: parent
      renderStrategy: Canvas.Cooperative
      Connections { target: root; function onRevChanged() { canvas.requestPaint() } }
      onPaint: {
        var ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)
        ctx.lineWidth = 1
        for (var i = 0; i < root.linkView.length; i++) {
          var l = root.linkView[i]
          var a = root.nodeById(l.fromId), b = root.nodeById(l.toId)
          if (!a || !b) continue
          var x0 = root.cx(a), y0 = root.cy(a), x2 = root.cx(b), y2 = root.cy(b)
          // The inter-machine arc runs high across the black band, above her head.
          var control = root.linkControl(l,a,b)
          var x1 = control[0], y1 = control[1]
          ctx.beginPath()
          ctx.moveTo(x0, y0)
          ctx.quadraticCurveTo(x1, y1, x2, y2)
          // Quiet solid topology lines; inference stays in metadata, not dashes.
          ctx.strokeStyle = "rgba(47,124,140,0.55)"
          ctx.setLineDash([])
          ctx.stroke()
          ctx.setLineDash([])
        }
      }
    }

    // One crisp sprite per link, no echo copies. Observation starts a full journey.
    Repeater {
      model: root.particleView
      Item {
        id: pulseItem
        property var evt: modelData
        property var eventProgress: Renderer.pulseProgress(evt, root.pulseNow)
        property string kind: typeof evt.kind === "string" ? evt.kind : "message"
        property color tint: root.pulseColor(kind)
        property var pt: root.pulsePoint(evt, eventProgress === null ? 0 : eventProgress)
        visible: eventProgress !== null
        x: 0; y: 0

        Image {
          source: root.assetDir + "glow-pulse.png"
          width: 34; height: 34
          smooth: true
          opacity: 0.95
          x: pulseItem.pt[0] - width / 2
          y: pulseItem.pt[1] - height / 2
        }
      }
    }

    // ------------------------------------------------------------- nodes
    Repeater {
      id: nodeItems
      model: root.view
      HoloNode {
        x: modelData.x + root.drift(modelData)[0]
        y: modelData.y + root.drift(modelData)[1]
        label: modelData.label; word: modelData.word; state: modelData.state
        detail: modelData.detail; role: modelData.role; machine: modelData.machine
        ageS: modelData.ageS === null ? -1 : modelData.ageS
        tokens: modelData.tokens; calls5h: modelData.calls5h; apiCalls: modelData.apiCalls
        lease: modelData.lease; alive: modelData.alive; flash: modelData.flash
        working: modelData.working
        activity: modelData.activity === undefined || modelData.activity === null ? 0 : modelData.activity
        toolActive: modelData.toolActive === true
        disc: modelData.disc
        layoutScale: modelData.layoutScale
        labelOnLeft: modelData.labelOnLeft === true
        breathe: root.breathe
        phase: (index % 7) * 0.14
        glowSprite: root.assetDir + "glow-node.png"
      }
    }

    // ------------------------------------------------------------ headers
    Text {
      x: 395 - width / 2; y: 120
      text: "VPS · RUNTIME"
      color: "#5fb6c9"
      font.family: "Noto Sans Mono"; font.pixelSize: 14; font.letterSpacing: 4
    }
    Text {
      x: panel.width - 395 - width / 2; y: 120
      text: "P1 · WORKSTATION"
      color: "#5fb6c9"
      font.family: "Noto Sans Mono"; font.pixelSize: 14; font.letterSpacing: 4
    }
    // totals
    Column {
      x: (panel.width - width) / 2; y: 20
      spacing: 2
      Text {
        text: "NODES " + root.value(root.totals.nodes_online)
              + "/" + root.value(root.totals.nodes_total)
              + "   WORKING " + (root.value(root.totals.working) + (root.totals.working_unknown ? " +?" : ""))
        color: "#a8f7ff"
        font.family: "Noto Sans Mono"; font.pixelSize: 13; font.letterSpacing: 2
      }
      Text {
        text: "VISIBLE TOKENS " + (root.totals.tokens_today !== undefined && root.totals.tokens_today !== null ? (root.totals.tokens_today / 1e6).toFixed(1) + "M" : "-")
              + "   BEACON " + (root.beaconAge >= 0 ? root.ageStr(root.beaconAge) : "NONE")
        color: root.vpsStale ? "#c9a227" : "#5fb6c9"
        font.family: "Noto Sans Mono"; font.pixelSize: 12; font.letterSpacing: 2
      }
    }


  }
}
