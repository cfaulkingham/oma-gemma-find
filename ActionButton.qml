import QtQuick
import qs.Commons

Rectangle {
    id: root
    property string label: ""
    property bool selected: false
    signal clicked()
    implicitWidth: caption.implicitWidth + 24
    implicitHeight: 34
    width: implicitWidth
    height: implicitHeight
    radius: 6
    color: selected || mouse.containsMouse ? "#30888888" : "transparent"
    border.width: 1
    border.color: selected ? Color.menu.text : Color.menu.border
    opacity: enabled ? 1 : 0.45
    Text {
        id: caption
        anchors.centerIn: parent
        text: root.label
        textFormat: Text.PlainText
        color: Color.menu.text
        font.family: Style.font.family
        font.pixelSize: 12
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
