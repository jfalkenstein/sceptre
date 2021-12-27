from functools import partial

import six
import yaml


CFN_TAGS = [
    'Condition',
    'Ref',
]


CFN_FNS = [
    'And',
    'Base64',
    'Cidr',
    'Equals',
    'FindInMap',
    'GetAtt',
    'GetAZs',
    'If',
    'ImportValue',
    'Join',
    'Not',
    'Or',
    'Select',
    'Split',
    'Sub',
    'Transform',
]


def _getatt_constructor(loader, node):
    if isinstance(node.value, six.text_type):
        return node.value.split('.', 1)
    elif isinstance(node.value, list):
        seq = loader.construct_sequence(node)
        for item in seq:
            if not isinstance(item, six.text_type):
                raise ValueError(
                    "Fn::GetAtt does not support complex datastructures")
        return seq
    else:
        raise ValueError("Fn::GetAtt only supports string or list values")


def _tag_constructor(loader, tag_suffix, node):
    if tag_suffix not in CFN_FNS and tag_suffix not in CFN_TAGS:
        raise ValueError("Bad tag: !{tag_suffix}. Supported tags are: "
                         "{supported_tags}".format(
                             tag_suffix=tag_suffix,
                             supported_tags=", ".join(sorted(CFN_TAGS + CFN_FNS))
                         ))

    if tag_suffix in CFN_FNS:
        tag_suffix = "Fn::{tag_suffix}".format(tag_suffix=tag_suffix)

    data = {}
    yield data

    if tag_suffix == 'Fn::GetAtt':
        constructor = partial(_getatt_constructor, (loader, ))
    elif isinstance(node, yaml.ScalarNode):
        constructor = loader.construct_scalar
    elif isinstance(node, yaml.SequenceNode):
        constructor = loader.construct_sequence
    elif isinstance(node, yaml.MappingNode):
        constructor = loader.construct_mapping

    data[tag_suffix] = constructor(node)


class CfnYamlLoader(yaml.SafeLoader):
    pass


CfnYamlLoader.add_multi_constructor("!", _tag_constructor)
