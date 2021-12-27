import json
from typing import Any, Callable

import click
import yaml
from tabulate import tabulate

from sceptre.cli.helpers.cfn_yaml_loader import CfnYamlLoader
from sceptre.stack_status_colourer import StackStatusColourer


PRIMITIVE_TYPES = (str, int, float, type(None), bool)


def write(var, output_format="json", no_colour=True):
    """
    Writes ``var`` to stdout. If output_format is set to "json" or "yaml",
    write ``var`` as a JSON or YAML string.

    :param var: The object to print
    :type var: object
    :param output_format: The format to print the output as. Allowed values: \
    "text", "json", "yaml"
    :type output_format: str
    :param no_colour: Whether to colour stack statuses
    :type no_colour: bool
    """
    if no_colour:
        writer = ConsoleWriter(output_format)
    else:
        colourer = StackStatusColourer()
        writer = ColouringConsoleWriter(output_format, colourer)

    writer.write(var)


class ConsoleWriter:
    def __init__(
        self,
        output_format: str,
        *,
        output_func=click.echo,
    ):
        self._stringify = getattr(self, f'_convert_to_{output_format}')
        self._output = output_func

    def write(self, value: Any):
        prepared_value = self._prepare_value_for_serialization(value)
        as_string = self._stringify(prepared_value)
        self._output(as_string)

    def _convert_to_json(self, value: Any):
        return json.dumps(value, indent=4,  sort_keys=True, default=lambda obj: str(obj))

    def _convert_to_yaml(self, value: Any):
        return yaml.safe_dump(value, default_flow_style=False, explicit_start=True)

    def _convert_to_text(self, value: Any):
        # If it's just a list of primitive values, we'll just put one on each line
        if isinstance(value, list) and all(isinstance(item, PRIMITIVE_TYPES) for item in value):
            return '\n'.join(str(item) for item in value)

        # If it's a list of dicts, we'll turn that to a table.
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return tabulate(value, headers='keys')

        # If it's a dict where the values are primitive types, we'll turn that into a two-column table
        if isinstance(value, dict) and all(isinstance(val, PRIMITIVE_TYPES) for val in value.values()):
            return tabulate(list(value.items()), headers=('key', 'value'))

        # in other cases, we'll fall back to yaml serialization
        return self._convert_to_yaml(value)

    def _prepare_value_for_serialization(self, value):
        if isinstance(value, dict):
            return {key: self._prepare_value_for_serialization(val) for key, val in value.items()}

        if isinstance(value, list):
            return [self._prepare_value_for_serialization(item) for item in value]

        if isinstance(value, str):
            try:
                # yaml is a superset of json, so the yaml loader will load both json and yaml. Also,
                # since yaml loads unquoted primative types as well, this is a fairly reliable way
                # to decode the string into python types, if they can be.
                # We don't further recurse on the loaded result because, at that point, we know that
                # the data can be serialized.
                return yaml.load(value, Loader=CfnYamlLoader)
            except Exception:
                # If it fails yaml loading, it's something not yaml/json compatible, in which case
                # just return the string.
                return value

        # For any other kind of data type, just return the value.
        return value


class ColouringConsoleWriter(ConsoleWriter):

    def __init__(self, output_format: str, colourer: StackStatusColourer, *, output_func=click.echo):
        super().__init__(output_format, output_func=output_func)
        self.colourer = colourer
        self._stringify = self._wrap_with_colouring(self._stringify)

    def _wrap_with_colouring(self, func_to_wrap: Callable[[Any], str]):
        def wrapper(value: Any):
            as_string = func_to_wrap(value)
            colored = self.colourer.colour(as_string)
            return colored

        return wrapper
