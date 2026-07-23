import Toybox.Application;
import Toybox.Lang;
import Toybox.WatchUi;

class IronQuestSafeApp extends Application.AppBase {
    private var _view;

    public function initialize() {
        AppBase.initialize();
        _view = new $.IronQuestSafeView();
    }

    public function getInitialView() as [Views] or [Views, InputDelegates] {
        return [_view, new $.IronQuestSafeDelegate(_view)];
    }

    public function onStart(state as Dictionary?) as Void {
    }

    public function onStop(state as Dictionary?) as Void {
    }
}
