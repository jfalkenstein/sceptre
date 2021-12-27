import logging
import sys
from functools import wraps

import click
import yaml

from boto3.exceptions import Boto3Error
from botocore.exceptions import BotoCoreError, ClientError
from jinja2.exceptions import TemplateError

from sceptre.exceptions import SceptreException
from sceptre.stack_status import StackStatus
from sceptre.stack_status_colourer import StackStatusColourer
from sceptre.cli.helpers.console_writer import write


def catch_exceptions(func):
    """
    Catches and simplifies expected errors thrown by sceptre.

    catch_exceptions should be used as a decorator.

    :param func: The function which may throw exceptions which should be
        simplified.
    :returns: The decorated function.
    """
    def logging_level():
        logger = logging.getLogger(__name__)
        return logger.getEffectiveLevel()

    @wraps(func)
    def decorated(*args, **kwargs):
        """
        Invokes ``func``, catches expected errors, prints the error message and
        exits sceptre with a non-zero exit code. In debug mode, the original
        exception is re-raised to assist debugging.
        """
        try:
            return func(*args, **kwargs)
        except (SceptreException, BotoCoreError, ClientError, Boto3Error,
                TemplateError) as error:
            if logging_level() == logging.DEBUG:
                raise
            write(error)
            sys.exit(1)

    return decorated


def confirmation(
    command, ignore, command_path, change_set=None
):
    if not ignore:
        msg = "Do you want to {} ".format(command)
        if change_set:
            msg = msg + "change set '{0}' for '{1}'".format(
                change_set, command_path
            )
        else:
            msg = msg + "'{0}'".format(command_path)
        click.confirm(msg, abort=True)


def setup_vars(var_file, var, merge_vars, debug, no_colour):
    """
    Handle --var-file and --var arguments before
    returning data for the user_variables as required
    by the ConfigReader and SceptreContext.

    :param var_file: the var_file list.
    :type var_file: List[Dict]
    :param var: the var list.
    :type var: List[str]
    :param merge_vars: Merge instead of
        overwrite duplicate keys.
    :type merge_vars: bool
    :param debug: debug mode.
    :type debug: bool
    :param no_colour: no_colour mode.
    :type no_colour: bool

    :returns: data for the user_variables.
    :rtype: Dict
    """
    logger = setup_logging(debug, no_colour)

    return_value = {}

    def _update_dict(variable):
        variable_key, variable_value = variable.split("=")
        keys = variable_key.split(".")

        def _nested_set(dic, keys, value):
            for key in keys[:-1]:
                dic = dic.setdefault(key, {})
            dic[keys[-1]] = value

        _nested_set(return_value, keys, variable_value)

    if var_file:
        for fh in var_file:
            parsed = yaml.safe_load(fh.read())

            if merge_vars:
                return_value = _deep_merge(parsed, return_value)
            else:
                return_value.update(parsed)

            # the rest of this block is for debug purposes only
            existing_keys = set(return_value.keys())
            new_keys = set(parsed.keys())
            overloaded_keys = existing_keys & new_keys  # intersection

            if overloaded_keys:
                message = "Duplicate variables encountered: "

                if merge_vars:
                    message += "{0}. Using values from: {1}.".format(
                        ", ".join(overloaded_keys), fh.name)
                else:
                    message += "{0}. Performing deep merge, {1} wins.".format(
                        ", ".join(overloaded_keys), fh.name)

                logger.debug(message)

    if var:
        # --var options overwrite --var-file options, unless a dict and --merge-vars.
        for variable in var:
            if isinstance(variable, dict) and merge_vars:
                return_value = _deep_merge(variable, return_value)
            else:
                _update_dict(variable)

    return return_value


def _deep_merge(source, destination):
    for key, value in source.items():
        if isinstance(value, dict):
            node = destination.setdefault(key, {})
            _deep_merge(value, node)
        else:
            destination[key] = value

    return destination


def stack_status_exit_code(statuses):
    if not all(
            status == StackStatus.COMPLETE
            for status in statuses):
        return 1
    else:
        return 0


def setup_logging(debug, no_colour):
    """
    Sets up logging.

    By default, the python logging module is configured to push logs to stdout
    as long as their level is at least INFO. The log format is set to
    "[%(asctime)s] - %(name)s - %(message)s" and the date format is set to
    "%Y-%m-%d %H:%M:%S".

    After this function has run, modules should:

    .. code:: python

        import logging

        logging.getLogger(__name__).info("my log message")

    :param debug: A flag indication whether to turn on debug logging.
    :type debug: bool
    :no_colour: A flag to indicating whether to turn off coloured output.
    :type no_colour: bool
    :returns: A logger.
    :rtype: logging.Logger
    """
    if debug:
        sceptre_logging_level = logging.DEBUG
        logging.getLogger("botocore").setLevel(logging.INFO)
    else:
        sceptre_logging_level = logging.INFO
        # Silence botocore logs
        logging.getLogger("botocore").setLevel(logging.CRITICAL)

    formatter_class = logging.Formatter if no_colour else ColouredFormatter

    formatter = formatter_class(
        fmt="[%(asctime)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    log_handler = logging.StreamHandler()
    log_handler.setFormatter(formatter)
    logger = logging.getLogger("sceptre")
    logger.addHandler(log_handler)
    logger.setLevel(sceptre_logging_level)
    return logger


def simplify_change_set_description(response):
    """
    Simplies the response from the AWS describe change set API.

    :param response: The original api response.
    :type response: dict
    :returns: A more concise description of the change set.
    :rtype: dict
    """
    desired_response_items = [
        "ChangeSetName",
        "CreationTime",
        "ExecutionStatus",
        "StackName",
        "Status",
        "StatusReason"
    ]
    desired_resource_changes = [
        "Action",
        "LogicalResourceId",
        "PhysicalResourceId",
        "Replacement",
        "ResourceType",
        "Scope"
    ]
    formatted_response = {
        k: v
        for k, v in response.items()
        if k in desired_response_items
    }
    formatted_response["Changes"] = [
        {
            "ResourceChange": {
                k: v
                for k, v in change["ResourceChange"].items()
                if k in desired_resource_changes
            }
        }
        for change in response["Changes"]
    ]
    return formatted_response


class ColouredFormatter(logging.Formatter):
    """
    ColouredFormatter add colours to all stack statuses that appear in log
    messages.
    """

    stack_status_colourer = StackStatusColourer()

    def format(self, record):
        """
        Colours and returns all stack statuses in ``record``.

        :param record: The log item to format.
        :type record: str
        :returns: str
        """
        response = super(ColouredFormatter, self).format(record)
        coloured_response = self.stack_status_colourer.colour(response)
        return coloured_response

