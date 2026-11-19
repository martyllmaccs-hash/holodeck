// One sister's body state. base.jpg already shows her at ATTENTION (the original render
// pose), so "awake" draws nothing. Otherwise:
//   dormant  fig_<n>_dormant.jpg over the base (arms low, head turned away and down)
//   rise     fig_<n>_rise.mp4  dormant -> attention (first frame == dormant still)
//   fall     fig_<n>_fall.mp4  attention -> dormant (first frame == base)
// Assets come from build/build_figures.py, graded and cropped like base.jpg, so the
// rectangle has no seam. Wakes as soon as she is working; goes dormant only after
// `holdSec` without work, so short gaps between tool calls don't make her bob.
// A clip always finishes before the next decision, so she never snaps mid-move.
import QtQuick
import QtMultimedia

Item {
  id: fig
  property string name
  property var b                       // [x, y, w, h] in 1920x1080 stage space
  property bool working: false         // fed by shell.qml (node.working or preview)
  property bool ready: false           // fleet data has arrived; boot pose waits for it
  property real now: 0
  property real holdSec: 20
  property string phase: ""            // "" (boot) | dormant | rise | awake | fall
  property real lastWork: -1e9
  property int demoLeft: 0             // IPC figdemo only (display): clips still to play, ignores working
  x: b[0]; y: b[1]; width: b[2]; height: b[3]

  function asset(f) { return Qt.resolvedUrl("assets/" + f) }
  function play(kind) {
    phase = kind
    player.stop()
    player.source = asset("fig_" + name + "_" + kind + ".mp4")
    player.play()
  }
  function step() {
    if (!ready || demoLeft > 0) return
    if (working) lastWork = now
    var want = working || (now - lastWork) < holdSec
    if (phase === "") { phase = want ? "awake" : "dormant"; return }   // boot: no clip
    if (phase === "dormant" && want) play("rise")
    else if (phase === "awake" && !want) play("fall")
  }
  onWorkingChanged: step()
  onNowChanged: step()
  function finish() {                  // clip done: settle, then free the decoder
    phase = phase === "rise" ? "awake" : "dormant"
    Qt.callLater(function() {
      player.stop(); player.source = ""
      if (fig.demoLeft > 0) { fig.demoLeft--; if (fig.demoLeft > 0) demoPause.restart(); else fig.step() }
      else fig.step()
    })
  }
  function demo(cycles) {              // fall + rise pairs from the current resting pose, 2 s rest between
    if (phase !== "awake" && phase !== "dormant") return "busy: " + phase
    demoLeft = cycles * 2
    demoPause.restart()
    return name + " demo " + cycles + " cycles from " + phase
  }
  Timer {
    id: demoPause; interval: 2000
    onTriggered: fig.play(fig.phase === "awake" ? "fall" : "rise")
  }

  Image {
    anchors.fill: parent
    source: fig.asset("fig_" + fig.name + "_dormant.jpg")
    visible: fig.phase === "dormant" || fig.phase === "rise"
    smooth: true
  }
  VideoOutput {
    id: vo
    anchors.fill: parent
    fillMode: VideoOutput.Stretch
    visible: fig.phase === "rise" || fig.phase === "fall"
  }
  MediaPlayer {
    id: player
    videoOutput: vo
    onMediaStatusChanged: {
      if (mediaStatus !== MediaPlayer.EndOfMedia && mediaStatus !== MediaPlayer.InvalidMedia) return
      if (fig.phase === "rise" || fig.phase === "fall") fig.finish()
    }
    onErrorOccurred: (error, errorString) => {
      console.warn("holo-v3 figure " + fig.name + ": " + errorString)
      if (fig.phase === "rise" || fig.phase === "fall") fig.finish()
    }
  }
}
