"""Installed YAML extensions still configure each fresh parser instance."""

import importlib
import sys
from types import ModuleType

from ruamel.yaml import YAML
from ruamel.yaml.constructor import SafeConstructor

import hermes_yaml as yaml


def test_extension_initializes_each_parser_with_current_settings(monkeypatch):
    extension = ModuleType("hermes_test_yaml_extension")
    extension.typ = "safe"
    settings = {"label": "first"}

    def initialize(parser):
        label = settings["label"]

        class ExtensionConstructor(SafeConstructor):
            pass

        ExtensionConstructor.add_constructor(
            "!extension", lambda constructor, node: {
                "label": label, "value": constructor.construct_scalar(node),
            })
        parser.Constructor = ExtensionConstructor

    extension.init_typ = initialize
    try:
        with monkeypatch.context() as patch:
            patch.setitem(sys.modules, extension.__name__, extension)
            patch.setattr(YAML, "official_plug_ins", lambda self: [extension.__name__])
            importlib.reload(yaml)
            assert yaml.safe_load("entry: !extension alpha\nflag: off\n") == {
                "entry": {"label": "first", "value": "alpha"}, "flag": False,
            }
            settings["label"] = "second"
            assert yaml.safe_load("entry: !extension beta\nflag: yes\n") == {
                "entry": {"label": "second", "value": "beta"}, "flag": True,
            }
    finally:
        importlib.reload(yaml)
