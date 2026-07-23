import Toybox.Graphics;
import Toybox.WatchUi;

class IronQuestSmokeView extends WatchUi.View {
    public function initialize() {
        View.initialize();
    }

    public function onUpdate(dc as Dc) as Void {
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_BLACK);
        dc.clear();

        var width = dc.getWidth();
        var centerX = width / 2;
        var y = 120;

        dc.setColor(0x00FFFF, Graphics.COLOR_TRANSPARENT);
        dc.drawText(centerX, y, Graphics.FONT_MEDIUM, "IronQuest", Graphics.TEXT_JUSTIFY_CENTER);
        y += 45;
        dc.setColor(Graphics.COLOR_GREEN, Graphics.COLOR_TRANSPARENT);
        dc.drawText(centerX, y, Graphics.FONT_SMALL, "CHECK OK", Graphics.TEXT_JUSTIFY_CENTER);
        y += 34;
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(centerX, y, Graphics.FONT_TINY, "Sideload works", Graphics.TEXT_JUSTIFY_CENTER);
    }
}
