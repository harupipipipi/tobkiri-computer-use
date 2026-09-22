import pytest

from tobkiri_computer_use import ClickStep, ComputerError


def test_grid_measures_cell_centers_in_screenshot_pixels_without_driver_calls(rig):
    computer, transport = rig
    window = computer.window(pid=7, window_id=10)
    state = window.observe()
    calls = list(transport.calls)
    cells = state.grid([40, 100, 360, 300], rows=2, columns=4)
    assert transport.calls == calls
    assert [[(p.x, p.y) for p in row] for row in cells] == [
        [(80, 150), (160, 150), (240, 150), (320, 150)],
        [(80, 250), (160, 250), (240, 250), (320, 250)],
    ]
    assert all(p.surface == state.surface and p.observation_id == state.id for row in cells for p in row)
    # Grid centers use the returned screenshot size, not desktop pixels/points.
    small = window.observe(max_dimension=400)
    assert small.grid([0, 0, 400, 300], rows=1, columns=1)[0][0] == small.point(200, 150)


def test_grid_points_keep_translation_and_normal_staleness_guards(rig):
    computer, transport = rig
    window = computer.window(pid=7, window_id=10)
    state = window.observe()
    point = state.grid([0, 0, 800, 600], rows=2, columns=2)[0][0]
    transport.bounds['x'] += 40
    window.click(point)
    sent = [a for n, a in transport.calls if n == 'click']
    assert len(sent) == 1 and (sent[0]['x'], sent[0]['y']) == (200, 150)
    with pytest.raises(ComputerError) as exc:
        window.click(point)
    assert exc.value.code == 'stale_observation'
    assert len([n for n, _ in transport.calls if n == 'click']) == 1
    current = window.observe()
    point = current.grid([0, 0, 800, 600], rows=1, columns=1)[0][0]
    transport.bounds['width'] += 50
    with pytest.raises(ComputerError):
        window.click(point)
    assert len([n for n, _ in transport.calls if n == 'click']) == 1


@pytest.mark.parametrize('region,rows,columns', [
    ([0, 0, 800, 600], 0, 2), ([0, 0, 800, 600], True, 2),
    ([0, 0, 800, 600], 2, 1.5), ([0, 0, 800, 600], 100, 100),
    ([-1, 0, 800, 600], 1, 1), ([0, 0, 801, 600], 1, 1),
    ([0, 0, 800, 601], 1, 1), ([1, 0, 1, 600], 1, 1),
    ([0, 0, float('nan'), 600], 1, 1), ([0, 0, float('inf'), 600], 1, 1),
    ([False, 0, 800, 600], 1, 1), ([0, 0, 800], 1, 1),
    ('abcd', 1, 1), (None, 1, 1),
])
def test_grid_rejects_invalid_regions_without_sending_input(rig, region, rows, columns):
    computer, transport = rig
    state = computer.window(pid=7, window_id=10).observe()
    calls = list(transport.calls)
    with pytest.raises(ComputerError):
        state.grid(region, rows=rows, columns=columns)
    assert transport.calls == calls


def test_grid_requires_a_screenshot_frame(rig):
    computer, _ = rig
    state = computer.window(pid=7, window_id=10).observe(screenshot=False)
    with pytest.raises(ComputerError) as exc:
        state.grid([0, 0, 400, 300], rows=1, columns=1)
    assert exc.value.code == 'no_pixel_frame'


def test_grid_points_feed_existing_timeline_without_reobserving_each_cell(rig):
    computer, transport = rig
    window = computer.window(pid=7, window_id=10)
    state = window.observe()
    cells = state.grid([0, 0, 800, 600], rows=2, columns=4)
    transport.calls.clear()
    result = window.timeline([ClickStep(0, cells[0][1]), ClickStep(0, cells[1][3])], max_lateness=5)
    assert result.status == 'completed'
    assert [(a['x'], a['y']) for n, a in transport.calls if n == 'click'] == [(300, 150), (700, 450)]
    assert sum(n == 'get_window_state' for n, _ in transport.calls) == 1
    assert result.observation.id != state.id
    assert all(event['delivery']['effect'] == 'unverifiable' for event in result.events)
