// DEPRECATED: kept only for reference. Do not sideload this app.
//
// This app starts its Timer from Application.onStart(), which is the exact
// pattern documented in docs/20_GARMIN_CONNECTIQ_TROUBLESHOOTING.md as the
// cause of an on-device crash ("Invalid Value" in IronQuestSafeApp.onStart
// before the fix). It also points at an ephemeral trycloudflare.com quick
// tunnel URL that changes every time the tunnel restarts.
//
// Use monkey_c/ironquest_safe_telemetry instead: it starts its Timer from
// the View's onShow() (the correct lifecycle hook) and posts to the
// permanent Cloudflare Worker endpoint.
import Toybox.Application;
import Toybox.Communications;
import Toybox.Lang;
import Toybox.Sensor;
import Toybox.Timer;
import Toybox.WatchUi;

const IRONQUEST_ENDPOINT = "https://northwest-distinct-springfield-oliver.trycloudflare.com/garmin";

class IronQuestTelemetryApp extends Application.AppBase {
    private var _view;
    private var _timer;
    private var _inFlight;
    private var _inFlightTicks;
    private var _samplesSent;
    private var _lastResponse;
    private var _lastError;
    private var _rr;

    public function initialize() {
        AppBase.initialize();
        _view = new $.IronQuestTelemetryView();
        _timer = null;
        _inFlight = false;
        _inFlightTicks = 0;
        _samplesSent = 0;
        _lastResponse = null;
        _lastError = null;
        _rr = null;
    }

    public function onStart(state as Dictionary?) as Void {
        _timer = new Timer.Timer();
        _timer.start(method(:sendSnapshot), 3000, true);
    }

    public function onStop(state as Dictionary?) as Void {
        if (_timer != null) {
            _timer.stop();
            _timer = null;
        }
    }

    public function getInitialView() as [Views] or [Views, InputDelegates] {
        return [_view];
    }

    private function sendSnapshot() as Void {
        if (_inFlight) {
            _inFlightTicks += 1;
            if (_inFlightTicks >= 10) {
                _inFlight = false;
                _inFlightTicks = 0;
                _lastError = "No response";
                _view.setStatus(_samplesSent, _lastResponse, _lastError);
                WatchUi.requestUpdate();
            }
            return;
        }

        var payload = {
            "device" => "garmin_venu_3",
            "device_name" => "Venu 3",
            "provider" => "garmin",
            "sample_type" => "connect_iq_live",
            "source" => "connect_iq_watch_app",
            "activity_state" => "ironquest_live_stream",
            "acceleration_unit" => "mg",
            "gyroscope_unit" => "dps"
        };

        try {
            var info = Sensor.getInfo();
            if (info != null) {
                if ((info has :heartRate) && info.heartRate != null) {
                    payload["heart_rate_bpm"] = info.heartRate;
                    payload["heart_rate_contact"] = "detected";
                }
                if ((info has :accel) && info.accel != null && info.accel.size() >= 3) {
                    payload["acceleration"] = {
                        "x" => info.accel[0],
                        "y" => info.accel[1],
                        "z" => info.accel[2]
                    };
                }
            }
        } catch (e) {
            payload["note"] = "Sensor read failed";
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
            _inFlightTicks = 0;
            Communications.makeWebRequest(IRONQUEST_ENDPOINT, payload, options, method(:onResponse));
        } catch (e) {
            _inFlight = false;
            _inFlightTicks = 0;
            _lastError = "Req " + e.getErrorMessage();
            _view.setStatus(_samplesSent, _lastResponse, _lastError);
            WatchUi.requestUpdate();
        }
    }

    public function onResponse(responseCode as Number, data as Dictionary or String or Null) as Void {
        _inFlight = false;
        _inFlightTicks = 0;
        _lastResponse = responseCode;
        if (responseCode == 200) {
            _samplesSent += 1;
            _lastError = null;
        } else {
            _lastError = "HTTP " + responseCode.toString();
        }
        _view.setStatus(_samplesSent, _lastResponse, _lastError);
        WatchUi.requestUpdate();
    }

    private function latestNumber(values) {
        if (values == null) {
            return null;
        }
        if (values instanceof Array) {
            if (values.size() == 0) {
                return null;
            }
            return values[values.size() - 1];
        }
        return values;
    }
}
