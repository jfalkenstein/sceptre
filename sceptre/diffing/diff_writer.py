import datetime
import itertools
import json
from abc import abstractmethod
from functools import singledispatch
from typing import TextIO, Generic, List

import cfn_flip
import yaml
from deepdiff import DeepDiff
from deepdiff.helper import json_convertor_default

from sceptre.diffing.stack_differ import StackConfiguration, StackDiff, DiffType

deepdiff_json_defaults = {
    datetime.date: lambda x: x.isoformat(),
    StackConfiguration: lambda x: dict(x._asdict())
}


class DiffWriter(Generic[DiffType]):
    """A component responsible for taking a StackDiff and writing it in a way that is useful and
    readable. This is an abstract base class, so the abstract methods need to be implemented to
    create a DiffWriter for a given DiffType.
    """
    # We'll lengthen these to full width when we compute outputs
    STAR_BAR = '*' * 80
    LINE_BAR = '-' * 80

    def __init__(self, stack_diff: StackDiff, output_stream: TextIO, output_format: str):
        """Initializes the DiffWriter

        :param stack_diff: The diff this writer will be outputting
        :param output_stream: The stream this writer should output to; Generally, this will be
            stdout
        :param output_format: Output format specified for the base Sceptre cli command; This should
            be one of "yaml", "json", or "text"
        """
        self.stack_name = stack_diff.stack_name
        self.stack_diff = stack_diff

        self.template_diff = stack_diff.template_diff
        self.config_diff = stack_diff.config_diff
        self.is_deployed = stack_diff.is_deployed

        self.collected_lines: List[str] = []

        self.output_stream = output_stream
        self.output_format = output_format

    @property
    def has_difference(self) -> bool:
        return self.has_config_difference or self.has_template_difference

    def write(self):
        """Writes the diff to the output stream."""
        self._output(self.STAR_BAR)
        if not self.has_difference:
            self._output(f"No difference to deployed stack {self.stack_name}")
            return

        self._output(f"--> Difference detected for stack {self.stack_name}!")

        if not self.is_deployed:
            self._write_new_stack_details()
            return

        self._output(self.LINE_BAR)
        self._write_config_difference()
        self._output(self.LINE_BAR)
        self._write_template_difference()

        self._output_to_stream()

    def compute_max_line_length(self) -> int:
        return len(max(
            itertools.chain.from_iterable(line.splitlines() for line in self.collected_lines),
            key=len
        ))

    def _write_new_stack_details(self):
        stack_config_text = self._dump_stack_config(self.stack_diff.generated_config)
        self._output(
            'This stack is not deployed yet!',
            self.LINE_BAR,
            'New Config:',
            '',
            stack_config_text,
            self.LINE_BAR,
            'New Template:',
            '',
            self.stack_diff.generated_template
        )
        return

    def _output(self, *lines: str):
        lines_with_breaks = [f'{line}\n' for line in lines]
        self.collected_lines.extend(lines_with_breaks)

    def _dump_stack_config(self, stack_config: StackConfiguration) -> str:
        stack_config_dict = dict(stack_config._asdict())
        dumped = self._dump_dict(stack_config_dict)
        return dumped

    def _dump_dict(self, dict_to_dump: dict) -> str:
        if self.output_format == "json":
            # There's not really a viable way to dump a template as "text" -> YAML is very readable
            dumper = cfn_flip.dump_json
        else:
            dumper = cfn_flip.dump_yaml

        dumped = dumper(dict_to_dump)
        return dumped

    def _write_config_difference(self):
        if not self.has_config_difference:
            self._output("No stack config difference")
            return

        diff_text = self.dump_diff(self.config_diff)
        self._output(
            'Config difference:',
            '',
            diff_text
        )

    def _write_template_difference(self):
        if not self.has_template_difference:
            self._output('No template difference')
            return

        diff_text = self.dump_diff(self.template_diff)
        self._output(
            'Template difference:',
            '',
            diff_text
        )

    def _output_to_stream(self):
        max_line_length = self.compute_max_line_length()
        full_length_star_bar = '*' * max_line_length
        full_length_line_bar = '-' * max_line_length
        for line in self.collected_lines:
            if self.STAR_BAR in line:
                line = line.replace(self.STAR_BAR, full_length_star_bar)
            elif self.LINE_BAR in line:
                line = line.replace(self.LINE_BAR, full_length_line_bar)
            self.output_stream.write(line)

    @abstractmethod
    def dump_diff(self, diff: DiffType) -> str:
        """"Implement this method to write the DiffType to string"""

    @property
    @abstractmethod
    def has_config_difference(self) -> bool:
        """Implement this to indicate whether or not there is a config difference"""

    @property
    @abstractmethod
    def has_template_difference(self) -> bool:
        """Implement this to indicate whether or not there is a template difference"""


class DeepDiffWriter(DiffWriter[DeepDiff]):
    """A DiffWriter for StackDiffs where the DiffType is a DeepDiff object."""

    @property
    def has_config_difference(self) -> bool:
        return len(self.config_diff) > 0

    @property
    def has_template_difference(self) -> bool:
        return len(self.template_diff) > 0

    def dump_diff(self, diff: DeepDiff) -> str:
        diff_as_dict = diff.to_dict()
        diff_with_root_keys_removed = self._remove_root_key_prefixes_recursively(diff_as_dict)
        # json.dumps lets you specify default serializations, yaml doesn't, so we definitely want to
        # use the json dumper to create the diff FIRST. This provides a useful way to ensure all
        # values are in a form that can be serialized.
        jsonified = json.dumps(
            diff_with_root_keys_removed,
            default=json_convertor_default(
                default_mapping=deepdiff_json_defaults
            ),
            indent=4
        )
        if self.output_format == 'json':
            return jsonified

        # We use the json and flip it to yaml because we know everything has been made serializable
        # here.
        loaded = json.loads(jsonified)
        return yaml.dump(loaded)

    def _remove_root_key_prefixes_recursively(self, obj):
        """Removes the "root" prefix off all the keys generated by DeepDiff. This should make for
        a more readable diff without every key beginning with this prefix.
        """
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                new_key = key[4:] if isinstance(key, str) and key.startswith('root') else key
                new_value = self._remove_root_key_prefixes_recursively(value)
                result[new_key] = new_value
            return result
        elif isinstance(obj, list):
            return [self._remove_root_key_prefixes_recursively(item) for item in obj]

        return obj


class DiffLibWriter(DiffWriter[List[str]]):
    """A DiffWriter for StackDiffs where the DiffType is a a list of strings."""

    @property
    def has_config_difference(self) -> bool:
        return len(self.config_diff) > 0

    @property
    def has_template_difference(self) -> bool:
        return len(self.template_diff) > 0

    def dump_diff(self, diff: List[str]) -> str:
        # Difflib doesn't care about the output format since it only outputs strings. We would have
        # accounted for the output format in the differ itself rather than here.
        return '\n'.join(diff)
