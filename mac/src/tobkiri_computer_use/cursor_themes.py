"""Portable cursor artwork and trusted, offline Cua theme authoring.

Agent tools select installed IDs only. Source generation, compilation and
installation belong to this explicit host CLI, never to an input fallback.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


THEME_PROFILE = "cua-driver-actions-v2"
ACTIONS = ("idle", "observe", "click", "drag", "scroll", "text", "key",
           "navigate", "app", "transfer", "record", "system")
BUILTIN_THEMES = {
    "tobkiri.arrow": "Tobkiri Arrow",
    "tobkiri.stickman": "Tobkiri Stickman",
}
REDUCED_MOTION = ("auto", "on", "off")
_THEME_ID = re.compile(r"[A-Za-z0-9_-]{1,63}(?:\.[A-Za-z0-9_-]{1,63})+")
_INK = [0.08, 0.10, 0.15, 1]
_WHITE = [1, 1, 1, 1]
_BLUE = [0.13, 0.48, 0.94, 1]


def theme_arguments(theme_id, reduced_motion="auto"):
    """Validate a portable installed ID, keeping paths and source out of RPCs."""
    if not isinstance(theme_id, str) or len(theme_id) > 200 or not _THEME_ID.fullmatch(theme_id):
        raise ValueError("theme_id must be a dotted installed theme ID, such as cua.default or tobkiri.stickman")
    if reduced_motion not in REDUCED_MOTION:
        raise ValueError("reduced_motion must be auto, on, or off")
    return {"theme_id": theme_id, "reduced_motion": reduced_motion}


def _static(value):
    return {"a": 0, "k": value}


def _animated(*values):
    frames = []
    for index, (frame, value) in enumerate(values):
        item = {"t": frame, "s": value if isinstance(value, list) else [value]}
        if index + 1 < len(values):
            following = values[index + 1][1]
            item.update(e=following if isinstance(following, list) else [following],
                        i={"x": [0.833], "y": [0.833]}, o={"x": [0.167], "y": [0.167]})
        frames.append(item)
    return {"a": 1, "k": frames}


def _path(vertices, *, closed=False):
    return {"ty": "sh", "ks": _static({"v": vertices, "i": [[0, 0]] * len(vertices),
                                         "o": [[0, 0]] * len(vertices), "c": closed})}


def _ellipse(x, y, width, height):
    return {"ty": "el", "p": _static([x, y]), "s": _static([width, height]), "d": 1}


def _stroke(color, width):
    return {"ty": "st", "c": _static(color), "o": _static(100), "w": _static(width),
            "lc": 2, "lj": 2, "ml": 4}


def _transform():
    return {"ty": "tr", "p": _static([0, 0]), "a": _static([0, 0]),
            "s": _static([100, 100]), "r": _static(0), "o": _static(100),
            "sk": _static(0), "sa": _static(0)}


def _layer(index, name, geometry, frames, *, color=_INK, width=5, fill=None,
           position=None, rotation=None, scale=None, opacity=None, anchor=(64, 64)):
    paints = ([] if fill is None else [{"ty": "fl", "c": _static(fill), "o": _static(100), "r": 1}])
    return {"ddd": 0, "ind": index, "ty": 4, "nm": name, "sr": 1,
            "ks": {"p": position or _static(list(anchor)), "a": _static(list(anchor)),
                   "s": scale or _static([100, 100]), "r": rotation or _static(0),
                   "o": opacity or _static(100)},
            "ao": 0, "shapes": [*geometry, *paints, _stroke(color, width), _transform()],
            "ip": 0, "op": frames, "st": 0, "bm": 0}


def _artwork(theme_id, action, frames):
    if theme_id == "tobkiri.arrow":
        pointer = _path([[44, 24], [44, 92], [61, 77], [74, 104], [86, 98],
                         [73, 72], [98, 72]], closed=True)
        return [_layer(1, "Arrow", [pointer], frames, fill=_WHITE, width=4)]

    # Authored in the same 128-pixel canvas as Cua: renderer scale, heading,
    # window anchoring and the native input coordinate contract stay intact.
    body = [_ellipse(66, 39, 23, 23), _path([[66, 51], [66, 78]]),
            _path([[66, 77], [49, 105]]), _path([[66, 77], [83, 105]])]
    arm_position = _animated((0, [66, 58]), (frames // 2, [66, 57]), (frames, [66, 58]))
    wave = _animated((0, 0), (frames // 3, -32), (2 * frames // 3, 12), (frames, 0))
    arms = [(_path([[66, 58], [46, 74]]), None),
            (_path([[66, 58], [85, 48]]), wave if action in ("idle", "observe", "app") else None)]
    result = []
    # White under-strokes keep thin limbs readable on both light/dark windows.
    for color, width, offset in ((_WHITE, 10, 0), (_INK, 5, 10)):
        result.append(_layer(offset + 1, "Stickman body", body, frames, color=color, width=width))
        for index, (geometry, rotation) in enumerate(arms, 2):
            result.append(_layer(offset + index, "Stickman arm", [geometry], frames,
                                 color=color, width=width, anchor=(66, 58),
                                 position=arm_position, rotation=rotation))
    return result


def _cue(action, frames):
    # Every native semantic action has its own bounded animation. These cues
    # describe the driver's action, never successful delivery or app effects.
    geometry = {
        "observe": [_ellipse(27, 49, 21, 21), _path([[35, 57], [43, 65]])],
        "click": [_ellipse(35, 35, 24, 24)],
        "drag": [_path([[14, 52], [41, 52], [33, 44], [41, 52], [33, 60]])],
        "scroll": [_path([[26, 24], [26, 72]]), _path([[18, 32], [26, 24], [34, 32]]),
                   _path([[18, 64], [26, 72], [34, 64]])],
        "text": [_path([[17, 32], [39, 32]]), _path([[28, 32], [28, 67]]),
                 _path([[20, 67], [36, 67]])],
        "key": [_path([[13, 37], [42, 37], [42, 62], [13, 62]], closed=True),
                _path([[20, 50], [34, 50]])],
        "navigate": [_path([[13, 49], [42, 49], [32, 39], [42, 49], [32, 59]])],
        "app": [_path([[13, 33], [43, 33], [43, 62], [13, 62]], closed=True),
                _path([[13, 41], [43, 41]])],
        "transfer": [_path([[20, 65], [20, 28], [13, 35], [20, 28], [27, 35]]),
                     _path([[37, 28], [37, 65], [30, 58], [37, 65], [44, 58]])],
        "record": [_ellipse(29, 49, 23, 23), _ellipse(29, 49, 5, 5)],
        "system": [_ellipse(29, 49, 25, 25), _path([[29, 32], [29, 41]]),
                   _path([[12, 49], [21, 49]]), _path([[37, 49], [46, 49]])],
    }.get(action)
    if geometry is None:
        return []
    position = _animated((0, [64, 64]), (frames // 2, [64, 59]), (frames, [64, 64]))
    if action == "click":
        scale = _animated((0, [55, 55]), (frames // 2, [135, 135]), (frames, [55, 55]))
    else:
        scale = None
    return [_layer(31, action + " outline", geometry, frames, color=_WHITE, width=8,
                   position=position, scale=scale),
            _layer(32, action + " cue", geometry, frames, color=_BLUE, width=4,
                   position=position, scale=scale)]


def source_entries(theme_id):
    """Return editable actions-v2 authoring data; no driver/desktop access."""
    if theme_id not in BUILTIN_THEMES:
        raise ValueError("Source generation supports tobkiri.arrow or tobkiri.stickman; cua.default is embedded in Cua")
    manifest = {"schema": "cua.cursor-theme/2", "id": theme_id,
                "name": BUILTIN_THEMES[theme_id], "version": "1.0.0", "author": "Tobkiri",
                "license": "MIT", "compatibility": {"profile": THEME_PROFILE, "semantics": 2},
                "canvas": {"width": 128, "height": 128, "fps": 30},
                "hotspot": {"x": 44, "y": 24} if theme_id == "tobkiri.arrow" else {"x": 66, "y": 39},
                "actions": {name: {"animation": "action_" + name,
                                   "still_frame": 0 if name == "idle" else 8} for name in ACTIONS}}
    entries = {"manifest.json": {"version": "2", "generator": "Tobkiri cursor themes",
                                 "animations": [{"id": "action_" + name} for name in ACTIONS]},
               "cua/theme.json": manifest}
    for action in ACTIONS:
        frames = 60 if action == "idle" else 24 if action in ("click", "key") else 48
        entries["a/action_" + action + ".json"] = {
            "v": "5.12.2", "fr": 30, "ip": 0, "op": frames, "w": 128, "h": 128,
            "nm": "action_" + action, "ddd": 0, "assets": [],
            # Lottie lists the frontmost layer first; author helpers above
            # build in paint order (white under-strokes, then ink/cues).
            "layers": list(reversed([*_artwork(theme_id, action, frames), *_cue(action, frames)])),
        }
    return entries


def write_source(theme_id, output):
    """Write a reproducible dotLottie source; generated files stay local."""
    entries = source_entries(theme_id)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w") as archive:
        for name, value in entries.items():
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            data = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
            archive.writestr(info, data, compresslevel=9)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("theme_id", choices=BUILTIN_THEMES)
    parser.add_argument("--output", type=Path, default=Path("artifacts/cursor-themes"), help="Generated output directory")
    parser.add_argument("--source-only", action="store_true", help="Generate .lottie without invoking a compiler")
    compiler = parser.add_mutually_exclusive_group()
    compiler.add_argument("--driver", default="cua-driver", help="Cua executable providing the cursor-theme subcommand")
    compiler.add_argument("--compiler", help="Standalone cua-cursor-theme executable, if the driver cannot locate it")
    parser.add_argument("--install", action="store_true", help="Explicitly install the compiled theme in Cua's local store")
    args = parser.parse_args(argv)
    if args.source_only and args.install:
        parser.error("--install requires compilation; omit --source-only")
    output = args.output.resolve()
    source = write_source(args.theme_id, output / (args.theme_id + ".lottie"))
    print(source)
    if args.source_only:
        return
    command = [args.compiler] if args.compiler else [args.driver, "cursor-theme"]
    artifact = output / (args.theme_id + ".cua-theme")
    # check=True surfaces validation/refusal as-is. Never install after a failed
    # build, choose another driver, or modify permissions as a recovery tactic.
    subprocess.run([*command, "build", str(source), "--output", str(artifact)], check=True)
    if args.install:
        subprocess.run([*command, "install", str(artifact)], check=True)


if __name__ == "__main__":
    main()
