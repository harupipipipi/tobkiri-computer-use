"""Opt-in regression checks: never mutate the fixture's unselected sibling."""
import json
from pathlib import Path
import re
from tobkiri_computer_use import Computer, ComputerError

out = Path(__file__).resolve().parents[1] / "artifacts"
report = {"checks": {}, "scope": "Dedicated TobkiriFixture windows only"}
def count(s): return int(re.search(r"Count: (\d+)", s.tree).group(1))
with Computer() as c:
    a=c.window(app="TobkiriFixture",title="Tobkiri Fixture A",name="isolation-A")
    b=c.window(app="TobkiriFixture",title="Tobkiri Fixture B",name="isolation-B")
    sa,sb=a.observe(),b.observe()
    original=sb.raw["window_bounds"]
    counts=(count(sa),count(sb))
    try:
        c.transport.call("set_window_frame", {"pid":b.surface[0],"window_id":b.surface[1],
            **sa.raw["window_bounds"],"session":b.session})
        sa=a.observe()
        for name,op in (
            ("pixel_click", lambda:a.click(sa.find("Increment").point)),
            ("scroll", lambda:a.scroll(sa.find("Increment"),"down")),
            ("drag", lambda:a.drag(sa.point(100,100),sa.point(300,300))),
        ):
            try:
                op()
                raise AssertionError(name+" was sent despite overlapping sibling")
            except ComputerError as exc:
                assert exc.code=="overlapping_window", exc
                report["checks"][name+"_refused"] = True
        sa,sb=a.observe(),b.observe()
        assert (count(sa),count(sb))==counts
        report["checks"]["both_windows_unchanged_after_refusal"]=True
        # An AXPress is tied to the selected element, even with a sibling above it.
        r=a.click("Increment")
        assert count(r.observation)==counts[0]+1
        assert count(b.observe())==counts[1]
        report["checks"]["semantic_press_only_changes_selected_window"]=True
        values=(a.observe().find("Name").value,b.observe().find("Name").value)
        for name,op in (("key",lambda:a.press_key("x")),("type",lambda:a.type_text("Name","WRONG-WINDOW-TEST"))):
            try:
                op()
                raise AssertionError("Ambiguous same-PID keyboard input was sent")
            except ComputerError as exc:
                assert exc.code=="keyboard_target_unproven", exc
                report["checks"][name+"_refused"]=True
        assert (a.observe().find("Name").value,b.observe().find("Name").value)==values
        report["checks"]["both_text_fields_unchanged_after_refusal"]=True
        a.observe().save(out/"isolation-A.png")
        b.observe().save(out/"isolation-B.png")
    finally:
        c.transport.call("set_window_frame", {"pid":b.surface[0],"window_id":b.surface[1],**original,"session":b.session})
(out/"target-isolation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(report,ensure_ascii=False,indent=2))
