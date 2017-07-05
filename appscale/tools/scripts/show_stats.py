import sys
import traceback

from .. import version_helper
from ..appscale_stats import show_stats
from ..local_state import LocalState
from ..parse_args import ParseArgs


version_helper.ensure_valid_python_is_used()


def main():
  """
  Execute appscale-describe-instances script.
  """
  options = ParseArgs(sys.argv[1:], "appscale-show-stats").args
  try:
    show_stats(options)
    sys.exit(0)
  except Exception, e:
    LocalState.generate_crash_log(e, traceback.format_exc())
    sys.exit(1)
