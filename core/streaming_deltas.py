# Copied from openai-python (https://github.com/openai/openai-python)
# src/openai/lib/streaming/_deltas.py
# License: Apache 2.0 (https://github.com/openai/openai-python/blob/main/LICENSE)
# Minimal local helpers (is_dict, is_list) added so we have no dependency on the SDK.

from __future__ import annotations


def _is_dict(x: object) -> bool:
    return isinstance(x, dict)


def _is_list(x: object) -> bool:
    return isinstance(x, list)


def accumulate_delta(
    acc: dict[object, object], delta: dict[object, object]
) -> dict[object, object]:
    """Merge a streaming chunk delta into an accumulated message/snapshot.

    Used to build a full chat completion message from SSE chunks: content and
    tool_calls (with partial function.arguments) are merged by index; strings
    are concatenated.
    """
    for key, delta_value in delta.items():
        if key not in acc:
            acc[key] = delta_value
            continue

        acc_value = acc[key]
        if acc_value is None:
            acc[key] = delta_value
            continue

        # the `index` property is used in arrays of objects so it should
        # not be accumulated like other values e.g.
        # [{'foo': 'bar', 'index': 0}]
        #
        # the same applies to `type` properties as they're used for
        # discriminated unions
        if key == "index" or key == "type":
            acc[key] = delta_value
            continue

        if isinstance(acc_value, str) and isinstance(delta_value, str):
            acc_value += delta_value
        elif isinstance(acc_value, (int, float)) and isinstance(
            delta_value, (int, float)
        ):
            acc_value += delta_value
        elif _is_dict(acc_value) and _is_dict(delta_value):
            acc_value = accumulate_delta(acc_value, delta_value)
        elif _is_list(acc_value) and _is_list(delta_value):
            # for lists of non-dictionary items we'll only ever get new entries
            # in the array, existing entries will never be changed
            if all(
                isinstance(x, (str, int, float)) for x in acc_value
            ):
                acc_value.extend(delta_value)
                continue

            for delta_entry in delta_value:
                if not _is_dict(delta_entry):
                    raise TypeError(
                        f"Unexpected list delta entry is not a dictionary: {delta_entry}"
                    )

                try:
                    index = delta_entry["index"]
                except KeyError as exc:
                    raise RuntimeError(
                        f"Expected list delta entry to have an `index` key; {delta_entry}"
                    ) from exc

                if not isinstance(index, int):
                    raise TypeError(
                        f"Unexpected, list delta entry `index` value is not an integer; {index}"
                    )

                try:
                    acc_entry = acc_value[index]
                except IndexError:
                    acc_value.insert(index, delta_entry)
                else:
                    if not _is_dict(acc_entry):
                        raise TypeError("not handled yet")

                    acc_value[index] = accumulate_delta(acc_entry, delta_entry)

        acc[key] = acc_value

    return acc
