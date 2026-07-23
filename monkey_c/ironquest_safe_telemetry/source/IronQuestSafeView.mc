import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Communications;
import Toybox.Math;
import Toybox.Sensor;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;

const IRONQUEST_SAFE_ENDPOINT = "https://fitquest-garmin.merazmilton9.workers.dev/garmin";
const WATCH_PAGE_COUNT = 3;

class IronQuestSafeView extends WatchUi.View {
    private var _sent;
    private var _lastCode;
    private var _message;
    private var _timer;
    private var _inFlight;
    private var _waitTicks;
    private var _lastHr;
    private var _lastContact;
    private var _lastAccelX;
    private var _lastAccelY;
    private var _lastAccelZ;
    private var _lastAccelMag;
    private var _lastMotionDelta;
    private var _motionState;
    private var _lastBattery;
    private var _page;

    public function initialize() {
        View.initialize();
        _sent = 0;
        _lastCode = null;
        _message = "Booting";
        _timer = null;
        _inFlight = false;
        _waitTicks = 0;
        _lastHr = null;
        _lastContact = null;
        _lastAccelX = null;
        _lastAccelY = null;
        _lastAccelZ = null;
        _lastAccelMag = null;
        _lastMotionDelta = null;
        _motionState = "waiting";
        _lastBattery = null;
        _page = 0;
    }

    public function setStatus(sent as Number, lastCode as Number or Null, message as String) as Void {
        _sent = sent;
        _lastCode = lastCode;
        _message = message;
    }

    public function onShow() as Void {
        _message = "Ready";
        WatchUi.requestUpdate();
        if (_timer == null) {
            _timer = new Timer.Timer();
            _timer.start(method(:sendPing), 3000, true);
        }
    }

    public function onHide() as Void {
        if (_timer != null) {
            _timer.stop();
            _timer = null;
        }
    }

    public function sendPing() as Void {
        if (_inFlight) {
            _waitTicks += 1;
            if (_waitTicks >= 4) {
                _inFlight = false;
                _waitTicks = 0;
                setStatus(_sent, _lastCode, "No response");
                WatchUi.requestUpdate();
            }
            return;
        }

        var payload = {
            "device" => "garmin_venu_3",
            "device_name" => "Venu 3",
            "provider" => "garmin",
            "sample_type" => "connect_iq_safe",
            "source" => "connect_iq_safe_watch_view",
            "activity_state" => "ironquest_safe_ping",
            "sequence" => _sent + 1,
            "sent_count" => _sent,
            "sample_interval_ms" => 3000,
            "endpoint_mode" => "cloudflare_https"
        };

        if (_lastCode != null) {
            payload["last_http_code"] = _lastCode;
        }

        try {
            var info = Sensor.getInfo();
            if (info != null) {
                if ((info has :heartRate) && info.heartRate != null) {
                    _lastHr = info.heartRate;
                }
                if (_lastHr != null) {
                    payload["heart_rate_bpm"] = _lastHr;
                    payload["heart_rate_contact"] = "detected";
                    _lastContact = "detected";
                }
                if ((info has :accel) && info.accel != null && info.accel.size() >= 3) {
                    _lastAccelX = info.accel[0];
                    _lastAccelY = info.accel[1];
                    _lastAccelZ = info.accel[2];
                    payload["acceleration"] = {
                        "x" => _lastAccelX,
                        "y" => _lastAccelY,
                        "z" => _lastAccelZ
                    };
                    payload["acceleration_unit"] = "mg";
                    var mag = Math.sqrt(
                        (_lastAccelX * _lastAccelX)
                        + (_lastAccelY * _lastAccelY)
                        + (_lastAccelZ * _lastAccelZ)
                    );
                    var delta = 0.0;
                    if (_lastAccelMag != null) {
                        delta = mag - _lastAccelMag;
                        if (delta < 0) {
                            delta = 0 - delta;
                        }
                    }
                    _lastAccelMag = mag;
                    _lastMotionDelta = delta;
                    if (delta < 35) {
                        _motionState = "steady";
                    } else if (delta < 150) {
                        _motionState = "moving";
                    } else {
                        _motionState = "active";
                    }
                    payload["acceleration_magnitude_mg"] = mag;
                    payload["watch_motion_delta_mg"] = delta;
                    payload["watch_motion_state"] = _motionState;
                }
            }
        } catch (e) {
            payload["note"] = "Sensor read failed";
        }

        try {
            var stats = System.getSystemStats();
            if (stats != null && (stats has :battery) && stats.battery != null) {
                _lastBattery = stats.battery;
                payload["battery"] = _lastBattery;
                payload["battery_unit"] = "percent";
            }
        } catch (e) {
        }

        var options = {
            :method => Communications.HTTP_REQUEST_METHOD_POST,
            :headers => {
                "Content-Type" => Communications.REQUEST_CONTENT_TYPE_JSON
            },
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
        };

        try {
            _inFlight = true;
            _waitTicks = 0;
            setStatus(_sent, _lastCode, "Sending");
            WatchUi.requestUpdate();
            Communications.makeWebRequest(IRONQUEST_SAFE_ENDPOINT, payload, options, method(:onResponse));
        } catch (e) {
            _inFlight = false;
            _waitTicks = 0;
            setStatus(_sent, _lastCode, "Request failed");
            WatchUi.requestUpdate();
        }
    }

    public function onResponse(code as Number, data as Dictionary or String or Null) as Void {
        _inFlight = false;
        _waitTicks = 0;
        _lastCode = code;
        if (code == 200) {
            _sent += 1;
            _message = "OK";
        } else {
            _message = "HTTP " + code.toString();
        }
        WatchUi.requestUpdate();
    }

    private function roundedNumber(value) as String {
        if (value == null) {
            return "--";
        }
        return (value + 0.5).toNumber().toString();
    }

    private function signedNumber(value) as String {
        if (value == null) {
            return "--";
        }
        return value.toNumber().toString();
    }

    public function handleSwipe(direction as WatchUi.SwipeDirection) as Boolean {
        if (direction == WatchUi.SWIPE_UP) {
            if (_page < WATCH_PAGE_COUNT - 1) {
                _page += 1;
            }
        } else if (direction == WatchUi.SWIPE_DOWN) {
            if (_page > 0) {
                _page -= 1;
            }
        } else {
            return false;
        }
        WatchUi.requestUpdate();
        return true;
    }

    private function pageTitle() as String {
        if (_page == 0) {
            return "SESSION";
        } else if (_page == 1) {
            return "MOTION";
        }
        return "LINK";
    }

    private function metricCenter(dc, label, value, y, color) as Void {
        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_BLACK);
        dc.drawText(dc.getWidth() / 2, y, Graphics.FONT_XTINY, label, Graphics.TEXT_JUSTIFY_CENTER);
        dc.setColor(color, Graphics.COLOR_BLACK);
        dc.drawText(dc.getWidth() / 2, y + 30, Graphics.FONT_SMALL, value, Graphics.TEXT_JUSTIFY_CENTER);
    }

    public function onUpdate(dc as Dc) as Void {
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_BLACK);
        dc.clear();

        var centerX = dc.getWidth() / 2;
        var statusColor = (_lastCode == 200) ? Graphics.COLOR_GREEN : Graphics.COLOR_YELLOW;
        if (_message.equals("Sending")) {
            statusColor = 0x00FFFF;
        }

        dc.setColor(0x00FFFF, Graphics.COLOR_BLACK);
        dc.drawText(centerX, 28, Graphics.FONT_MEDIUM, "FitQuest", Graphics.TEXT_JUSTIFY_CENTER);

        dc.setColor(Graphics.COLOR_GREEN, Graphics.COLOR_BLACK);
        dc.drawText(centerX, 76, Graphics.FONT_SMALL, pageTitle(), Graphics.TEXT_JUSTIFY_CENTER);

        var statusLine = _message;
        if (_lastCode != null && !_message.equals("HTTP " + _lastCode.toString())) {
            statusLine = _message + "  HTTP " + _lastCode.toString();
        }
        dc.setColor(statusColor, Graphics.COLOR_BLACK);
        dc.drawText(centerX, 116, Graphics.FONT_SMALL, statusLine, Graphics.TEXT_JUSTIFY_CENTER);

        if (_page == 0) {
            metricCenter(dc, "SENT PACKETS", _sent.toString(), 164, Graphics.COLOR_WHITE);
            metricCenter(dc, "HEART RATE", (_lastHr == null ? "--" : _lastHr.toString()) + " bpm", 280, Graphics.COLOR_YELLOW);
        } else if (_page == 1) {
            metricCenter(dc, "ACCELERATION", roundedNumber(_lastAccelMag) + " mg", 164, 0xFF00FF);
            metricCenter(dc, "MOTION STATE", _motionState + "  " + roundedNumber(_lastMotionDelta) + " mg", 280, Graphics.COLOR_GREEN);
        } else if (_page == 2) {
            metricCenter(dc, "BATTERY", roundedNumber(_lastBattery) + "%", 164, 0x00FFFF);
            metricCenter(dc, "SYNC INTERVAL", "3 s HTTPS", 280, Graphics.COLOR_LT_GRAY);
        }

        dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_BLACK);
        dc.drawText(centerX, 410, Graphics.FONT_XTINY, (_page + 1).toString() + "/" + WATCH_PAGE_COUNT.toString(), Graphics.TEXT_JUSTIFY_CENTER);
    }
}

class IronQuestSafeDelegate extends WatchUi.BehaviorDelegate {
    private var _view;

    public function initialize(view as IronQuestSafeView) {
        BehaviorDelegate.initialize();
        _view = view;
    }

    public function onSwipe(swipeEvent as WatchUi.SwipeEvent) as Boolean {
        return _view.handleSwipe(swipeEvent.getDirection());
    }
}

