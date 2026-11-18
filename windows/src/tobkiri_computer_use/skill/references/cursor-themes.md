# Portable cursor themes

Mac and Windows use the same installed theme IDs. `cua.default` is embedded
Cua artwork, including its stable named-session colors. `tobkiri.arrow` is a
classic white arrow; `tobkiri.stickman` is a waving stick figure. Both custom
themes cover all twelve native action animations and require local installation.
Other installed dotted IDs need no helper or MCP schema change.

```python
window.set_cursor_theme("cua.default")
window.set_cursor_theme("tobkiri.stickman", reduced_motion="on")
print(window.cursor_state())
```

`Computer(cursor_theme="cua.default", cursor_reduced_motion="auto")` selects
defaults for new helper sessions. Omission preserves the native theme. Named
mouse sessions can select independent themes. `reduced_motion` is `auto`, `on`
or `off`; movement speed remains a separate `set_cursor_speed()` setting.

MCP: call `tobkiri_cursor` with the exact `pid`, `window_id`, `cursor`,
`action="theme"`, `theme_id="tobkiri.stickman"`, and optional
`reduced_motion`. No observation or pixel point is needed. `action="state"`
reads Cua's theme/playback/visibility/fallback for that named helper session;
`action="status"` retains window-follower diagnostics. Selecting or reading a
theme does not move input or take focus. Native responses queue render changes;
readback alone is not proof of painted pixels. Preserve native fallback/refusal
diagnostics and do not resend app input because a theme failed.

Source paths, inline animation and legacy shape/color/image controls are not
accepted by the theme helper. Source authoring and installation use the trusted
local host CLI when that setup is requested:

```sh
tobkiri-cursor-theme tobkiri.stickman --install
tobkiri-cursor-theme tobkiri.arrow --install
```

Equivalent: run the package's Python with
`-m tobkiri_computer_use.cursor_theme_cli`. Omit `--install` to compile only;
`--source-only` generates deterministic `.lottie` without starting a driver.
`--driver PATH` chooses Cua, `--compiler PATH` its standalone `cua-cursor-theme`
compiler, and `--output DIRECTORY` chooses generated output. Compilation failure
never triggers install, retries, driver changes or permission setup.

Custom themes use Cua's trusted `cursor-theme validate/build/preview/install`
workflow: `cua.cursor-theme/2`, `cua-driver-actions-v2`, a 128×128 30fps canvas,
and idle/observe/click/drag/scroll/text/key/navigate/app/transfer/record/system.
The same compiled `.cua-theme` can be installed on both OSes. Generated archives,
artifacts and previews stay out of Git. Both CLI and driver must use the same
theme store; an absolute `CUA_DRIVER_CURSOR_THEME_DIR` can select a host-owned
store. A version string alone does not prove theme support: older builds lacking
the modern `theme_id` tool or compiler fail normally, without a legacy fallback.
