# Observation diagnostics draft

This is a proposed diagnostic contract and skill wording.  It does not change
the search API, retry an input, or change the current input/permission rules.

## What elements_complete currently means

In the current macOS driver, get_window_state always emits
elements_complete: false.  This is deliberate: the structured list includes
only actionable nodes, while individual AX child reads can fail independently
of the walk limits.  The driver therefore cannot prove that an absent label is
absent from the whole AX domain.

False is an absence-of-proof marker, not evidence that the current walk reached
its element limit.  It must not by itself cause a larger AX budget, a retry of
an input, or a refusal to use a valid current screenshot.

## Read the concrete diagnostic instead

The following fields distinguish the cases that completeness cannot:

| Condition | Existing response evidence | Meaning and safe next step |
| --- | --- | --- |
| Element-count cap actually stopped the walk | raw tree_markdown ends with the AX tree truncated at N nodes warning. | This is the only current response-level proof of the max_elements cap. Re-observe with a deliberately chosen budget or use the current visual path. |
| Depth limit omitted descendants | There is no exported truncated boolean or depth-cutoff marker. It is knowable only from the explicitly requested max_depth value. | Do not infer it from elements_complete. The Python helper currently does not send max_depth. |
| AX walk timed out | get_window_state returns a driver error containing AX tree walk ... timed out after 20 s; no Observation is produced. | This is not an empty-element observation. A new bounded observation is a read-only recovery; do not replay a prior input. |
| Requested WindowServer window has no matching AXWindow | degraded is true; degraded_reason starts with ax_window_unresolved; escalation.recommended is foreground. The elements array is intentionally empty. | This is an exact-window proof failure, separate from ordinary missing AX. Re-observe after the app settles. Background pixel input remains refused because it could reach a same-process sibling; follow the existing foreground policy only if needed. |
| AX walk returned no actionable nodes on a resolved window | degraded is true; degraded_reason starts with ax_tree_empty; escalation.recommended is px. | Re-observe if the UI is still settling. Otherwise, a current valid screenshot can supply a normal bound pixel target. |
| Pixel frame cannot be proved | screenshot_frame_valid is false and screenshot_error.code identifies px_capture_unavailable, px_frame_mismatch, or px_window_not_found. | Do not create or reuse a pixel point. Re-observe the exact window. |
| Window identity is stale or has another owner | The tool refuses with structured code window_id_not_found or window_owner_pid_mismatch. | There is no usable observation from that response. Select the current exact window before continuing. |

For a non-projected state, element_count and total_element_count describe the
actionable-node count before response projection, and
returned_element_count describes the array returned to the caller.  With a
native query, filtered_element_count is also present.  These counts are useful
context, but none proves completeness.  The native TreeWalkResult has a
truncated flag internally; it is not currently exported as a structured field.

## Valid screenshot and missing AX

Missing AX alone does not make a current screenshot unusable.  If the
observation has image data, a frame, screenshot_frame_valid is not false, and
the diagnosis is not ax_window_unresolved, a fresh Observation.point selected
from that image can use the ordinary exact-window pixel ladder.  The usual
geometry, overlapping-window, and delivery checks still apply.

This distinction matters: elements_complete false and ax_tree_empty describe
incomplete or unavailable semantics.  ax_window_unresolved additionally says
the driver cannot prove which same-process surface would receive a background
event, so its background refusal has a separate exact-target basis.

## Non-breaking find diagnostic proposal

Keep Observation.find_all returning a list, including an empty list.  Keep
Observation.find raising element_not_found for zero matches.  The proposed
change is only the zero-match message and details; it must not turn normal
searches into a new refusal.

Suggested element_not_found message:

> No current observed element matched the requested label and role. This does
> not prove the control is absent. Obtain a fresh observation of the same
> pid/window_id; if its image has a valid frame and its degradation is not
> ax_window_unresolved, select a new image point and use the normal
> exact-window pixel path. Do not resend a prior input whose outcome is
> unknown.

Suggested additive details shape:

    {
      "selector": {"label": "...", "role": "...", "contains": false},
      "surface": {"pid": "<pid>", "window_id": "<window_id>"},
      "observation_id": "...",
      "returned_element_count": "<len(observation.elements)>",
      "element_count": "<raw.element_count>",
      "elements_complete": false,
      "degraded_reason": null,
      "screenshot_frame_valid": true,
      "input_sent": false,
      "next_step": "fresh_observation_then_bound_pixel_if_valid"
    }

The values should be copied from the observation that failed the search, not
guessed from a future state.  Existing ambiguous-match details can remain the
current list of candidate elements.

## Proposed skill wording

Replace wording that says to check elements_complete and increase
max_elements when a visible control is missing with:

> The default AX walk budget is 2000 nodes. elements_complete false means the
> driver cannot prove that the actionable AX list is exhaustive; it does not
> itself show that the walk hit a limit. Increase max_elements only when the
> current tree explicitly reports truncation, or when another concrete reason
> calls for a different read. If the current screenshot has a valid frame and
> the exact-window diagnosis permits background pixel delivery, use a fresh
> bound image point through the normal ladder. Never repeat an earlier input
> merely because an element search returned no match.

This wording preserves a normal read-only recovery after an empty search and
does not make missing AX a blanket block on pixel interaction.
