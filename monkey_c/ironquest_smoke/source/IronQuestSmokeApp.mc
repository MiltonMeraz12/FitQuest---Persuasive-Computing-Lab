import Toybox.Application;
import Toybox.WatchUi;

class IronQuestSmokeApp extends Application.AppBase {
    public function initialize() {
        AppBase.initialize();
    }

    public function getInitialView() as [Views] or [Views, InputDelegates] {
        return [new $.IronQuestSmokeView()];
    }
}
