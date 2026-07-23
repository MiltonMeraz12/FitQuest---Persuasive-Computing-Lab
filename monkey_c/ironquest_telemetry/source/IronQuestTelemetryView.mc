import Toybox.Graphics;
import Toybox.Lang;
import Toybox.WatchUi;

class IronQuestTelemetryView extends WatchUi.View {
    private var _samplesSent;
    private var _lastResponse;
    private var _lastError;

    public function initialize() {
        View.initialize();
        _samplesSent = 0;
        _lastResponse = null;
        _lastError = null;
    }

    public function setStatus(samplesSent, lastResponse, lastError) as Void {
        _samplesSent = samplesSent;
        _lastResponse = lastResponse;
        _lastError = lastError;
    }

    public function onUpdate(dc as Dc) as Void {
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_BLACK);
        dc.clear();

        var width = dc.getWidth();
        var centerX = width / 2;
        var y = 88;

        dc.setColor(0x00FFFF, Graphics.COLOR_TRANSPARENT);
        dc.drawText(centerX, y, Graphics.FONT_MEDIUM, "IronQuest", Graphics.TEXT_JUSTIFY_CENTER);
        y += 42;
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(centerX, y, Graphics.FONT_SMALL, "Telemetry ON", Graphics.TEXT_JUSTIFY_CENTER);
        y += 36;
        dc.drawText(centerX, y, Graphics.FONT_SMALL, "Sent: " + _samplesSent.toString(), Graphics.TEXT_JUSTIFY_CENTER);
        y += 30;

        if (_lastResponse != null) {
            dc.drawText(centerX, y, Graphics.FONT_TINY, "Last: " + _lastResponse.toString(), Graphics.TEXT_JUSTIFY_CENTER);
            y += 24;
        }
        if (_lastError != null) {
            dc.setColor(Graphics.COLOR_RED, Graphics.COLOR_TRANSPARENT);
            dc.drawText(centerX, y, Graphics.FONT_TINY, _lastError, Graphics.TEXT_JUSTIFY_CENTER);
        } else {
            dc.setColor(Graphics.COLOR_GREEN, Graphics.COLOR_TRANSPARENT);
            dc.drawText(centerX, y, Graphics.FONT_TINY, "Waiting / sending", Graphics.TEXT_JUSTIFY_CENTER);
        }
    }
}
