import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import "Ui.js" as Ui

Item {
    id: root
    property var shell: null
    property var manifest: null
    property bool opened: false
    property var results: []
    property var roots: []
    property string answer: ""
    property string message: "Add a folder, download the models, then index."
    property string request: ""
    property string output: ""
    property int errBytes: 0
    property int files: 0
    property int chunks: 0
    property bool embedModel: false
    property bool gemmaModel: false
    property bool discard: false
    property string pendingNote: ""
    readonly property string pluginId: "io.github.cfaulkingham.oma-gemma-find"
    readonly property string helper: decodeURIComponent(String(Qt.resolvedUrl("bin/oma_gemma_find.py")).replace(/^file:\/\//, ""))

    function open() {
        opened = true
        Qt.callLater(function() { queryInput.forceActiveFocus() })
        if (!worker.running) {
            message = "Checking the index…"
            start("status", null, 30000)
        }
    }
    function cancelWork() {
        if (!worker.running) return
        discard = true
        message = "Stopped."
        worker.signal(15)
        killTimer.start()
    }
    function close() {
        opened = false
        cancelWork()
    }
    function toggle() { opened ? dismiss() : open() }
    function dismiss() {
        close()
        if (shell && typeof shell.hide === "function") shell.hide(pluginId)
    }
    function escape() {
        if (worker.running) cancelWork()
        else dismiss()
    }
    function start(op, fields, limitMs) {
        if (worker.running) return
        output = ""
        errBytes = 0
        discard = false
        var body = {op: op}
        if (fields && typeof fields.query === "string") body.query = fields.query
        if (fields && typeof fields.path === "string") body.path = fields.path
        request = JSON.stringify(body)
        deadlineTimer.interval = limitMs
        deadlineTimer.restart()
        worker.running = true
    }
    function searchNow() {
        var query = queryInput.text.trim()
        if (worker.running || !query) return
        answer = ""
        message = "Searching…"
        start("search", {query: query}, 180000)
    }
    function askNow() {
        var query = queryInput.text.trim()
        if (worker.running || !query) return
        message = "Asking Gemma 4…"
        start("ask", {query: query}, 600000)
    }
    function indexNow() {
        if (worker.running) return
        message = "Indexing…"
        start("index", null, 600000)
    }
    function downloadNow() {
        if (worker.running) return
        message = "Downloading the pinned models…"
        start("fetch", null, 1860000)
    }
    function addRoot() {
        var path = rootInput.text.trim()
        if (worker.running || !path) return
        message = "Adding folder…"
        start("add-root", {path: path}, 30000)
    }
    function removeRoot(path) {
        if (worker.running || !path) return
        message = "Removing folder…"
        start("remove-root", {path: path}, 30000)
    }
    function openPath(path) {
        if (!Ui.allowedPath(path, roots)) {
            message = "That file is outside the folders you added."
            return
        }
        Quickshell.execDetached(["/usr/bin/xdg-open", "--", path])
    }
    function label(value) {
        var text = String(value == null ? "" : value).slice(0, 300)
        try { return Ui.plain(text, 300) } catch (e) { return "" }
    }
    function kindText(value) {
        return value === "image" ? "image" : "text"
    }
    function scoreText(value) {
        if (typeof value !== "number" || !isFinite(value)) return ""
        return value.toFixed(2)
    }
    function describe(parsed) {
        if (parsed.stopped === "deadline")
            return "Indexing stopped at the time limit. Files already indexed were kept."
        if (parsed.error && parsed.op !== "ask")
            return parsed.error
        if (parsed.op === "ask" && parsed.error && parsed.answer)
            return parsed.error
        if (parsed.op === "ask" && parsed.answer)
            return parsed.error || (parsed.results.length + " matches. The answer uses those files.")
        if (parsed.op === "ask")
            return parsed.error || "No answer."
        if (parsed.op === "search")
            return parsed.results.length ? parsed.results.length + " matches. Enter or click to open." : "No matching files."
        if (parsed.op === "index" && parsed.ok)
            return "Indexed " + parsed.files + " changed files."
        if (parsed.op === "fetch" && parsed.ok)
            return "Models are installed."
        if (parsed.op === "add-root" && parsed.ok)
            return "Folder added. Index it when you are ready."
        if (parsed.op === "remove-root" && parsed.ok)
            return "Folder removed from the index."
        return root.statusLine()
    }
    function statusLine() {
        return files + " files · " + chunks + " chunks · "
            + (embedModel ? "EmbeddingGemma ready" : "EmbeddingGemma missing")
            + " · " + (gemmaModel ? "Gemma 4 ready" : "Gemma 4 missing")
    }
    function moveSelection(delta) {
        if (!results.length) return
        var next = Math.min(results.length - 1, Math.max(-1, resultList.currentIndex + delta))
        resultList.currentIndex = next
        if (next >= 0) resultList.positionViewAtIndex(next, ListView.Contain)
    }
    Component.onDestruction: { if (worker.running) worker.signal(15) }

    Process {
        id: worker
        command: ["/usr/bin/python3", "-I", "-S", "-B", root.helper]
        clearEnvironment: true
        environment: ({
            HOME: Quickshell.env("HOME") || "",
            PATH: "/usr/bin:/bin",
            LANG: "C.UTF-8",
            LC_ALL: "C.UTF-8",
            XDG_RUNTIME_DIR: Quickshell.env("XDG_RUNTIME_DIR") || "",
            DBUS_SESSION_BUS_ADDRESS: Quickshell.env("DBUS_SESSION_BUS_ADDRESS") || ""
        })
        stdinEnabled: true
        onStarted: {
            write(root.request)
            stdinEnabled = false
            root.request = ""
        }
        onRunningChanged: { if (running) stdinEnabled = true }
        stdout: SplitParser {
            splitMarker: ""
            onRead: function(chunk) {
                if (root.output.length + chunk.length > 65536) {
                    root.discard = true
                    root.message = "The helper response exceeded the limit."
                    worker.signal(15)
                    killTimer.start()
                } else root.output += chunk
            }
        }
        stderr: SplitParser {
            splitMarker: ""
            onRead: function(chunk) {
                root.errBytes += chunk.length
                if (root.errBytes > 4096) {
                    root.discard = true
                    worker.signal(15)
                    killTimer.start()
                }
            }
        }
        onExited: function(code, status) {
            killTimer.stop()
            deadlineTimer.stop()
            var raw = root.output
            root.output = ""
            root.errBytes = 0
            if (root.discard) return
            try {
                var parsed = Ui.parse(raw)
                root.roots = parsed.roots
                if (parsed.ok && (parsed.op === "status" || parsed.op === "fetch" || parsed.op === "add-root" || parsed.op === "remove-root")) {
                    root.files = parsed.files
                    root.chunks = parsed.chunks
                }
                if (parsed.ok && (parsed.op === "status" || parsed.op === "fetch")) {
                    root.embedModel = parsed.embedModel
                    root.gemmaModel = parsed.gemmaModel
                }
                if (parsed.op === "search") {
                    root.results = parsed.results
                    root.answer = ""
                    resultList.currentIndex = -1
                } else if (parsed.op === "ask") {
                    root.results = parsed.results
                    root.answer = parsed.answer
                    resultList.currentIndex = -1
                } else if (parsed.op === "add-root" && parsed.ok) {
                    rootInput.text = ""
                }
                if (parsed.op === "status" && root.pendingNote) {
                    root.message = root.pendingNote + " " + root.statusLine()
                    root.pendingNote = ""
                } else {
                    root.message = root.describe(parsed)
                }
                if (parsed.op === "index" || parsed.op === "fetch" || parsed.op === "add-root" || parsed.op === "remove-root") {
                    root.pendingNote = root.message
                    root.start("status", null, 30000)
                }
            } catch (e) {
                root.message = "The helper returned a response that could not be shown."
            }
        }
    }

    Timer {
        id: killTimer
        interval: 2000
        onTriggered: { if (worker.running) worker.signal(9) }
    }
    Timer {
        id: deadlineTimer
        interval: 30000
        onTriggered: {
            if (!worker.running) return
            root.discard = true
            root.message = "The helper took too long and was stopped."
            worker.signal(15)
            killTimer.start()
        }
    }

    PanelWindow {
        id: window
        visible: root.opened
        anchors { top: true; bottom: true; left: true; right: true }
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.namespace: "oma-gemma-find"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive

        Shortcut { sequence: "Escape"; onActivated: root.escape() }

        Rectangle { anchors.fill: parent; color: "#88000000" }
        MouseArea { anchors.fill: parent; onClicked: root.dismiss() }

        Rectangle {
            id: card
            anchors.centerIn: parent
            width: Math.min(760, window.width - 40)
            height: Math.min(720, window.height - 40)
            color: Color.menu.background
            border.color: Color.menu.border
            border.width: 2
            radius: Style.cornerRadius
            MouseArea { anchors.fill: parent; onClicked: {} }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 24
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: "Gemma Find"
                        textFormat: Text.PlainText
                        color: Color.menu.text
                        font.family: Style.font.family
                        font.pixelSize: 22
                        font.bold: true
                    }
                    Item { Layout.fillWidth: true }
                    ActionButton { label: "×"; width: 48; onClicked: root.dismiss() }
                }
                Text {
                    Layout.fillWidth: true
                    text: "Search your folders on this machine. Ask uses Gemma 4 on the matches."
                    textFormat: Text.PlainText
                    color: Color.menu.text
                    opacity: 0.65
                    wrapMode: Text.Wrap
                    font.family: Style.font.family
                    font.pixelSize: 13
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Rectangle {
                        Layout.fillWidth: true
                        height: 42
                        radius: 6
                        color: "transparent"
                        border.color: queryInput.activeFocus ? Color.menu.text : Color.menu.border
                        TextInput {
                            id: queryInput
                            anchors.fill: parent
                            anchors.margins: 10
                            maximumLength: 500
                            color: Color.menu.text
                            font.family: Style.font.family
                            font.pixelSize: 14
                            clip: true
                            selectByMouse: true
                            onAccepted: root.searchNow()
                            Keys.onEscapePressed: root.escape()
                            Keys.onUpPressed: root.moveSelection(-1)
                            Keys.onDownPressed: root.moveSelection(1)
                            Keys.onPressed: function(event) {
                                if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && (event.modifiers & Qt.ControlModifier)) {
                                    root.askNow()
                                    event.accepted = true
                                }
                            }
                        }
                        Text {
                            anchors.fill: queryInput
                            anchors.leftMargin: 10
                            visible: !queryInput.text && !queryInput.activeFocus
                            text: "Search your files"
                            textFormat: Text.PlainText
                            color: Color.menu.text
                            opacity: 0.5
                            font.pixelSize: 14
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                    ActionButton {
                        label: "Search"
                        enabled: !worker.running && queryInput.text.trim().length > 0
                        onClicked: root.searchNow()
                    }
                    ActionButton {
                        label: "Ask"
                        enabled: !worker.running && queryInput.text.trim().length > 0
                        onClicked: root.askNow()
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: root.message
                    textFormat: Text.PlainText
                    color: Color.menu.text
                    wrapMode: Text.Wrap
                    font.family: Style.font.family
                    font.pixelSize: 12
                }
                Text {
                    Layout.fillWidth: true
                    visible: root.answer.length > 0
                    text: root.answer
                    textFormat: Text.PlainText
                    color: Color.menu.text
                    wrapMode: Text.Wrap
                    font.family: Style.font.family
                    font.pixelSize: 14
                    maximumLineCount: 8
                    elide: Text.ElideRight
                }
                ListView {
                    id: resultList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 8
                    currentIndex: -1
                    model: root.results
                    delegate: Rectangle {
                        id: resultCard
                        required property var modelData
                        required property int index
                        width: resultList.width
                        height: resultColumn.implicitHeight + 24
                        color: resultMouse.containsMouse || resultCard.ListView.isCurrentItem ? "#18888888" : "transparent"
                        radius: 6
                        border.width: 1
                        border.color: resultCard.ListView.isCurrentItem ? Color.menu.text : Color.menu.border
                        Column {
                            id: resultColumn
                            width: parent.width - 24
                            x: 12
                            y: 12
                            spacing: 4
                            Text {
                                width: parent.width
                                text: root.label(resultCard.modelData.path)
                                textFormat: Text.PlainText
                                color: Color.menu.text
                                font.family: Style.font.family
                                font.pixelSize: 13
                                font.bold: true
                                elide: Text.ElideMiddle
                            }
                            Text {
                                width: parent.width
                                text: root.kindText(resultCard.modelData.kind) + "  " + root.scoreText(resultCard.modelData.score)
                                textFormat: Text.PlainText
                                color: Color.menu.text
                                opacity: 0.55
                                font.pixelSize: 11
                            }
                            Text {
                                width: parent.width
                                text: root.label(resultCard.modelData.excerpt)
                                textFormat: Text.PlainText
                                color: Color.menu.text
                                opacity: 0.85
                                font.family: Style.font.family
                                font.pixelSize: 13
                                wrapMode: Text.Wrap
                                maximumLineCount: 3
                                elide: Text.ElideRight
                            }
                        }
                        MouseArea {
                            id: resultMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.openPath(resultCard.modelData.path)
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Rectangle {
                        Layout.fillWidth: true
                        height: 36
                        radius: 6
                        color: "transparent"
                        border.color: rootInput.activeFocus ? Color.menu.text : Color.menu.border
                        TextInput {
                            id: rootInput
                            anchors.fill: parent
                            anchors.margins: 8
                            maximumLength: 4096
                            color: Color.menu.text
                            font.family: Style.font.family
                            font.pixelSize: 12
                            clip: true
                            selectByMouse: true
                            onAccepted: root.addRoot()
                        }
                        Text {
                            anchors.fill: rootInput
                            anchors.leftMargin: 8
                            visible: !rootInput.text && !rootInput.activeFocus
                            text: "Absolute folder path"
                            textFormat: Text.PlainText
                            color: Color.menu.text
                            opacity: 0.5
                            font.pixelSize: 12
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                    ActionButton { label: "Add"; enabled: !worker.running; onClicked: root.addRoot() }
                    ActionButton { label: "Index"; enabled: !worker.running; onClicked: root.indexNow() }
                    ActionButton { label: "Download"; enabled: !worker.running; onClicked: root.downloadNow() }
                }
                ListView {
                    id: rootList
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(root.roots.length * 36, 108)
                    visible: root.roots.length > 0
                    clip: true
                    spacing: 4
                    model: root.roots
                    delegate: RowLayout {
                        required property string modelData
                        required property int index
                        width: rootList.width
                        Text {
                            Layout.fillWidth: true
                            text: root.label(modelData)
                            textFormat: Text.PlainText
                            color: Color.menu.text
                            font.pixelSize: 12
                            elide: Text.ElideMiddle
                        }
                        ActionButton {
                            label: "Remove"
                            enabled: !worker.running
                            onClicked: root.removeRoot(modelData)
                        }
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: "Enter searches. Ctrl+Enter asks Gemma 4. Download and Index run only when you click them. Esc cancels or closes."
                    textFormat: Text.PlainText
                    color: Color.menu.text
                    opacity: 0.5
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }
            }
        }
    }
}
