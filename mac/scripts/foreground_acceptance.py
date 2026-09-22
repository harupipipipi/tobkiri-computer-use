"""Opt-in: ask the HUMAN to approve ONE foreground 'a' in our empty fixture.

No acceptance bypass exists in this script. Cancel/timeout/error sends no key.
Build/register TobkiriFocusFixture before running. All other setup/cleanup uses
background/semantic operations on the fixture owned by this transport only.
"""
from pathlib import Path
import json
import subprocess

from tobkiri_computer_use import Computer, ComputerError, MacOSDialogConsent
from tobkiri_computer_use.transport import structured

root = Path(__file__).resolve().parents[1]
probe = root / "artifacts/focus-probe"
def focus():
    return json.loads(subprocess.check_output([str(probe)], text=True))

report = {"scope": "One foreground 'a' into the Name field of a disposable TobkiriFocusFixture",
          "human_approval": "pending", "input_attempted": False}
try:
    with Computer(approval_callback=MacOSDialogConsent()) as computer:
        launch = structured(computer.tool("launch_app", {
            "bundle_id": "local.tobkiri.tobkirifocusfixture", "additional_arguments": ["--single"]}))
        pid = launch["pid"]
        try:
            rows = computer.windows(pid=pid, title="Tobkiri Fixture A")
            assert len(rows) == 1, rows
            w = computer.window(pid=pid, window_id=rows[0]["window_id"], name="approval-test")
            state = w.set_value("Name", "").observation
            report["target"] = w.target
            report["before_focus"] = focus()
            try:
                result = w.press_key("a", target=state.find("Name"), delivery_mode="foreground",
                                     fallback_reason="ユーザー指定の最終手段と承認UIを検証するため。専用テスト窓の空のName欄へ a を1回だけ入力します。背景入力の失敗を装うものではありません。")
                report.update(human_approval="approved", input_attempted=True, approval=result.approval,
                              delivery=result.delivery, fixture_value=result.observation.find("Name").value)
                report["expected_value_verified"] = report["fixture_value"] == "a"
                result.observation.save(root / "artifacts/foreground-result.png")
            except ComputerError as exc:
                report["error"] = exc.as_dict()
                no_input = {"approval_denied", "approval_unavailable", "approval_expired", "approval_target_changed",
                            "approval_required", "invalid_approval", "no_pixel_frame", "stale_geometry"}
                report["input_attempted"] = False if exc.code in no_input else "unknown"
                report["human_approval"] = "not_executed"
            report["after_focus"] = focus()
            report["prior_frontmost_restored"] = report["before_focus"]["pid"] == report["after_focus"]["pid"]
        finally:
            computer.tool("kill_app", {"pid": pid})
finally:
    (root / "artifacts/foreground-acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False, indent=2))
