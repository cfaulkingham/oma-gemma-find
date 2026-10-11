.pragma library

function allowedPath(path, roots) {
    if (typeof path !== "string" || path.length < 2 || path.length > 4096 || !path.startsWith("/"))
        return false
    if (/[\u0000-\u001f\u007f-\u009f<>&\\]/.test(path)) return false
    var parts = path.split("/")
    if (parts[0] !== "") return false
    for (var i = 1; i < parts.length; ++i) {
        if (parts[i] === "" || parts[i] === "." || parts[i] === "..") return false
    }
    if (!Array.isArray(roots)) return false
    for (var r = 0; r < roots.length; ++r) {
        var root = roots[r]
        if (typeof root !== "string" || root.length < 2) continue
        if (path === root || path.startsWith(root + "/")) return true
    }
    return false
}

function plain(value, limit) {
    if (typeof value !== "string") throw new Error("text")
    var text = value.replace(/[\u0000-\u0008\u000b-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069<>&]/g, "")
    if (text.length > limit) throw new Error("length")
    return text
}

function whole(value) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 10000000)
        throw new Error("count")
    return value
}

function parse(raw) {
    if (typeof raw !== "string" || raw.length > 65536) throw new Error("size")
    var doc = JSON.parse(raw)
    if (!doc || typeof doc !== "object" || Array.isArray(doc) || typeof doc.ok !== "boolean")
        throw new Error("shape")
    if (!Array.isArray(doc.results) || doc.results.length > 8) throw new Error("results")
    if (!Array.isArray(doc.roots) || doc.roots.length > 16) throw new Error("roots")
    var results = []
    for (var i = 0; i < doc.results.length; ++i) {
        var row = doc.results[i]
        if (!row || typeof row !== "object" || (row.kind !== "text" && row.kind !== "image"))
            throw new Error("result")
        if (typeof row.score !== "number" || !Number.isFinite(row.score) || row.score < -1.01 || row.score > 1.01)
            throw new Error("score")
        if (typeof row.path !== "string" || !allowedPath(row.path, doc.roots)) throw new Error("path")
        results.push({
            path: row.path,
            excerpt: plain(row.excerpt, 400),
            kind: row.kind,
            score: row.score
        })
    }
    var roots = []
    for (var n = 0; n < doc.roots.length; ++n) {
        if (typeof doc.roots[n] !== "string" || doc.roots[n].length > 4096) throw new Error("root")
        roots.push(doc.roots[n])
    }
    return {
        ok: doc.ok,
        op: typeof doc.op === "string" ? doc.op.slice(0, 32) : "",
        error: plain(typeof doc.error === "string" ? doc.error : "", 400),
        answer: plain(typeof doc.answer === "string" ? doc.answer : "", 2000),
        results: results,
        roots: roots,
        files: whole(typeof doc.files === "number" ? doc.files : 0),
        chunks: whole(typeof doc.chunks === "number" ? doc.chunks : 0),
        embedModel: doc.embedModel === true,
        gemmaModel: doc.gemmaModel === true,
        stopped: typeof doc.stopped === "string" ? plain(doc.stopped, 32) : ""
    }
}
