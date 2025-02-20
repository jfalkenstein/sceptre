Feature: Dump template

  Scenario Outline: Dumping static templates
    Given the template for stack "1/A" is "<filename>"
    When the user dumps the template for stack "1/A"
    Then the output is the same as the contents of "<filename>" template

  Examples: Json, Yaml
    | filename                  |
    | valid_template.json       |
    | malformed_template.json   |
    | invalid_template.json     |
    | jinja/valid_template.json |
    | valid_template.yaml       |
    | valid_template_mark.yaml  |
    | valid_template_func.yaml  |
    | malformed_template.yaml   |
    | invalid_template.yaml     |
    | jinja/valid_template.yaml |

  Scenario: Generate template using a valid python template file that outputs json
    Given the template for stack "1/A" is "valid_template_json.py"
    When the user dumps the template for stack "1/A"
    Then the output is the same as the contents returned by "valid_template_json.py"

  Scenario: Generate template using a valid python template file that outputs json with ignore dependencies
    Given the template for stack "1/A" is "valid_template_json.py"
    When the user dumps the template for stack "1/A" with ignore dependencies
    Then the output is the same as the contents returned by "valid_template_json.py"

  Scenario: Generate template using a valid python template file that outputs yaml
    Given the template for stack "1/A" is "valid_template_yaml.py"
    When the user dumps the template for stack "1/A"
    Then the output is the same as the contents returned by "valid_template_yaml.py"

  Scenario Outline: Dumping erroneous python templates
    Given the template for stack "1/A" is "<filename>"
    When the user dumps the template for stack "1/A"
    Then a "<exception>" is raised

  Examples: Template Errors
    | filename                   | exception                   |
    | missing_sceptre_handler.py | TemplateSceptreHandlerError |
    | attribute_error.py         | AttributeError              |

  Scenario: Generate template using a template file with an unsupported extension
    Given the template for stack "1/A" is "template.unsupported"
    When the user dumps the template for stack "1/A"
    Then a "UnsupportedTemplateFileTypeError" is raised

  Scenario Outline: Rendering jinja templates
    Given the template for stack "7/A" is "<filename>"
    When the user dumps the template for stack "7/A"
    Then the output is the same as the contents of "<rendered_filename>" template

  Examples: Template file extensions
    | filename                    | rendered_filename     |
    | jinja/valid_template.j2     | valid_template.yaml   |

  Scenario Outline: Render jinja template which uses an invalid key
    Given the template for stack "7/A" is "<filename>"
    When the user dumps the template for stack "7/A"
    Then a "<exception>" is raised

  Examples: Render Errors
    | filename                                | exception          |
    | jinja/invalid_template_missing_key.j2   | UndefinedError     |
    | jinja/invalid_template_missing_attr.j2  | UndefinedError     |

  Scenario: Dumping static templates with file template handler
    Given the template for stack "13/A" is "valid_template.json"
    When the user dumps the template for stack "13/A"
    Then the output is the same as the contents of "valid_template.json" template
