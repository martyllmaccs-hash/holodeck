// Decorative, bounded drift. Stable identity phases survive telemetry rebuilds.
function seed(key) {
    var h = 0;
    for (var i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
    return h;
}
function offset(key, t) {
    var h = seed(String(key));
    var p = (h % 997) / 997 * 6.283185307;
    var q = ((h >>> 10) % 991) / 991 * 6.283185307;
    return [60 * (0.62 * Math.sin(t * 0.2375 + p) + 0.38 * Math.sin(t * 0.08875 + q)),
             40 * (0.60 * Math.sin(t * 0.17875 + q) + 0.40 * Math.sin(t * 0.06625 + p))];
}
