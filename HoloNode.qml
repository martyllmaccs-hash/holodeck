// HoloNode — one agent in the orchestration lattice: a glowing disc, a name, a state
// word, and the numbers behind it. Idle nodes are dim; working nodes breathe.
import QtQuick
import "Renderer.js" as Renderer

Item {
  id: node

  property string label: ""
  property string word: ""
  property string state: "UNKNOWN"      // ACTIVE | TOOLING | THINKING | IDLE | OFFLINE | UNLINKED
  property string detail: ""
  property string role: ""
  property string machine: ""
  property real ageS: -1
  property var tokens: null
  property var calls5h: null
  property var apiCalls: null
  property var lease: null
  property var alive: null
  property real activity: 0          // 0..1 reported effort: scales breathing/glow beyond the plain working flag
  property bool toolActive: false    // a dispatched tool call is genuinely in flight right now
  property real flash: 0             // 1.0 right after a handoff lands on this node
  property real breathe: 0           // 0..1 from the shell's 40 ms timer
  property real phase: 0             // per-node offset so the fleet does not pulse in lockstep
  property string glowSprite: ""
  property real disc: 54
  property bool labelOnLeft: false

  property bool working: state === "ACTIVE" || state === "TOOLING" || state === "THINKING" || state === "WORKING"
  readonly property real beat: 0.5 + 0.5 * Math.sin((node.breathe + node.phase) * 6.283185)
  readonly property color accent:
      state === "UNLINKED" ? "#7a3030"
    : (state === "OFFLINE" || state === "IDLE") ? "#2f7c8c"
    : state === "UNKNOWN" ? "#7a7452"
    : state === "THINKING" ? "#d8f6ff"
    : "#7ff0ff"
  readonly property real lit: working ? 1.0 : (state === "IDLE" ? 0.42 : 0.30)

  property real layoutScale: 1
  implicitWidth: 300
  implicitHeight: 110
  transformOrigin: Item.TopLeft

  // halo — a working node's glow swells and brightens with how hard it is
  // reported to be working, not just a flat on/off.
  Image {
    anchors.centerIn: parent
    anchors.horizontalCenterOffset: node.labelOnLeft ? 95 : -95
    source: node.glowSprite
    width: node.disc * (node.working ? 3.6 + 0.9 * node.activity : 2.8)
    height: width
    opacity: node.lit * (0.55 + 0.25 * node.flash + 0.2 * node.activity)
    smooth: true
    Behavior on width { NumberAnimation { duration: 400 } }
    Behavior on opacity { NumberAnimation { duration: 500 } }
  }

  // breathing on the working nodes — timer-driven, not a property animation:
  // `SequentialAnimation on <prop>` silently never ran in this Quickshell build.
  scale: node.layoutScale * Renderer.breathScale(node.alive, node.working, node.state, node.beat, node.activity)

  // disc
  Rectangle {
    id: disc
    x: (node.labelOnLeft ? 245 : 55) - node.disc / 2
    y: (parent.height - node.disc) / 2
    width: node.disc
    height: node.disc
    radius: node.disc / 2
    color: "#04121a"
    border.width: node.working ? 2 : 1
    border.color: Qt.rgba(node.accent.r, node.accent.g, node.accent.b, 0.35 + 0.65 * node.lit)
    Behavior on border.color { ColorAnimation { duration: 400 } }
  }
  Rectangle {
    anchors.centerIn: disc
    width: node.disc * 0.44
    height: width
    radius: width / 2
    color: node.accent
    opacity: node.lit * (node.state === "OFFLINE" ? 0.35 : 0.9)
    Behavior on opacity { NumberAnimation { duration: 400 } }
  }
  // lease ring: a turn is held on this node right now
  Rectangle {
    anchors.centerIn: disc
    width: node.disc + 14
    height: width
    radius: width / 2
    color: "transparent"
    border.width: 1
    border.color: "#a8f7ff"
    opacity: node.lease === true ? 0.35 + 0.45 * node.beat : 0.0
    visible: node.lease === true
  }
  // tool-activity ring: a dispatched tool call is genuinely running right now,
  // independent of any lease -- the signal that used to go dark mid-task.
  Rectangle {
    anchors.centerIn: disc
    width: node.disc + 24
    height: width
    radius: width / 2
    color: "transparent"
    border.width: 2
    border.color: node.accent
    opacity: node.toolActive === true ? 0.25 + 0.4 * node.beat : 0.0
    visible: node.toolActive === true
  }

  Column {
    x: node.labelOnLeft ? 6 : 95
    width: 199
    y: 14
    spacing: 1
    Text {
      width: parent.width
      horizontalAlignment: node.labelOnLeft ? Text.AlignRight : Text.AlignLeft
      elide: Text.ElideRight
      text: node.label
      color: node.working ? "#e8fdff" : "#7fb6c4"
      font.family: "Noto Sans Mono"; font.pixelSize: 17; font.bold: true; font.letterSpacing: 2
    }
    Text {
      width: parent.width
      horizontalAlignment: node.labelOnLeft ? Text.AlignRight : Text.AlignLeft
      elide: Text.ElideRight
      text: node.word + (node.role === "ORCHESTRATOR" ? "  ◆" : "")
      color: node.accent
      font.family: "Noto Sans Mono"; font.pixelSize: 13; font.letterSpacing: 2
      opacity: 0.55 + 0.45 * node.lit
    }
    Text {
      width: parent.width
      horizontalAlignment: node.labelOnLeft ? Text.AlignRight : Text.AlignLeft
      elide: Text.ElideRight
      text: {
        var bits = []
        if (node.calls5h === null) bits.push("--/5H CALLS")
        else bits.push(node.calls5h + "/5H CALLS")
        bits.push(node.tokens === null ? "? TOK" : (node.tokens / 1000).toFixed(0) + "K TOK")
        if (node.alive === null) bits.push("LIVE ?")
        return bits.join(" · ")
      }
      color: "#4f8fa0"
      font.family: "Noto Sans Mono"; font.pixelSize: 10; font.letterSpacing: 1
    }
  }
}
