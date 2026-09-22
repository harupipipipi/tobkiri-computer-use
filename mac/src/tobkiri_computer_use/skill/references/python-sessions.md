# Interactive Python: observe, act, inspect

Start `python -i` in a retained TTY session using the environment where this
package is installed. In the source checkout, that is `.venv/bin/python -i`.
Send subsequent code to that same session. A plain script with a `with Computer()`
block is also suitable when all intended actions can be decided in advance.

```python
from tobkiri_computer_use import Computer, ComputerError
computer = Computer()
print(computer.windows())
```

If the host supplies an explicit runtime command, use
`computer = Computer(command=HOST_COMMAND)` instead of the default connection.
Select the requested PID and window ID from the inventory:

```python
window = computer.window(pid=PID, window_id=WINDOW_ID)
state = window.observe()
print(state.tree)
print([element.to_dict() for element in state.elements])
state.save('/absolute/output/before.png', marks=False)
```

Inspect the saved image with the host's image tool. Keep `computer`, `window`
and `state` alive while doing so. There is no need to implement a JSON command
bridge, reach into private SDK members, or reconnect for each input.

For a click, use `window.click(state.find(OBSERVED_LABEL))`. If a visible control
has no AX element, select its coordinates from that image and use
`window.click(state.point(X, Y))`. For a drag, choose both endpoints from the
same current image:

```python
start = state.point(START_X, START_Y)
end = state.point(END_X, END_Y)
result = window.drag(start, end, duration_ms=500)
print(result.delivery)
state = result.observation
print(state.changes)
state.save('/absolute/output/after.png', marks=False)
```

The uppercase labels and coordinates are placeholders for values you observed.
They are not fixture coordinates. Points use the screenshot's pixels; do not
apply Retina scaling or subtract the window's desktop origin yourself.
Pure window translation preserves that coordinate system. Resizing, image-scale
changes and changed layouts require fresh observations and freshly selected points.

Each completed action returns `result.observation`; use it for the next target.
When the app has not redrawn yet, `state = window.observe()` obtains fresh
evidence without sending more input. An empty element search does not mean an
input was attempted. An input timeout, in contrast, can have an unknown effect;
observe the result before deciding the next action, without automatic replay.

`window.set_value(state.find(OBSERVED_FIELD), TEXT)` replaces an editable native
field through AX. `window.type_text(target, TEXT)` inserts text, and
`window.press_key(KEY, modifiers=[...])` generates a key. Check the current
background keyboard route when using keys; the window need not be brought to
the foreground for AX field replacement.

For an expected semantic change, the public actions accept `expect`, using the
same native predicates as `window.verify(...)`. Inspect its returned status;
unknown is not proof of completion. For a visual result, inspect the actual image.

For reusable selectors, state waits with cancellation, and measured grid
coordinates, see [Python automation](python-automation.md). These are public
SDK methods; a separate automation server or custom retry loop is unnecessary.

Close only when the workflow is complete:

```python
computer.close()
```
