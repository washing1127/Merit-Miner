"""Flet 0.84 compatibility shim — allows old-style kwargs that are now properties."""

import flet as ft

_MOVED_KWARGS: dict[type, list[str]] = {
    ft.Card: ["color", "elevation"],
    ft.Container: ["color"],
    ft.IconButton: ["tooltip", "disabled"],
    ft.TextField: [
        "label", "hint_text", "prefix_icon", "border_radius", "border_color",
        "content_padding", "prefix", "multiline", "min_lines", "max_lines",
        "autofocus", "error_text", "keyboard_type", "can_reveal_password", "password",
    ],
    ft.Button: ["text"],
    ft.FilledButton: ["text"],
    ft.OutlinedButton: ["text"],
    ft.TextButton: ["text", "data"],
    ft.SnackBar: ["open"],
    ft.ProgressRing: ["width", "height"],
    ft.FloatingActionButton: ["tooltip"],
}


def _patch_class(cls: type, moved_kwargs: list[str]):
    original_init = cls.__init__

    def patched_init(self, *args, **kwargs):
        deferred = {}
        for key in moved_kwargs:
            if key in kwargs:
                deferred[key] = kwargs.pop(key)
        original_init(self, *args, **kwargs)
        for key, value in deferred.items():
            setattr(self, key, value)

    cls.__init__ = patched_init


def apply():
    for cls, kwargs in _MOVED_KWARGS.items():
        _patch_class(cls, kwargs)
