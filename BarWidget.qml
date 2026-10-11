import QtQuick
import Quickshell
import qs.Ui as Shell

Shell.BarWidget {
    id: root
    moduleName: "io.github.cfaulkingham.oma-gemma-find"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    Shell.BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        iconComponent: Component {
            Item {
                Rectangle {
                    width: parent.width * 0.42
                    height: width
                    anchors.centerIn: parent
                    rotation: 45
                    color: "transparent"
                    border.color: button.foreground
                    border.width: Math.max(1.5, parent.width * 0.1)
                }
            }
        }
        tooltipText: "Gemma Find"
        onPressed: function(buttonCode) {
            if (buttonCode === Qt.LeftButton)
                Quickshell.execDetached(["/usr/share/omarchy/bin/omarchy-shell", "shell", "toggle", root.moduleName])
        }
    }
}
