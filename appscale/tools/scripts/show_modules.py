import sys
import traceback

from appscale.tools import version_helper
from appscale.tools.local_state import LocalState
from appscale.tools.parse_args import ParseArgs
from appscale.tools.appscale_modules import show_modules


version_helper.ensure_valid_python_is_used()


def main():
  """
  Execute appscale-modules script.
  """
  options = ParseArgs(sys.argv[1:], "appscale-show-modules")
  try:
    show_modules(options)
    sys.exit(0)
  except Exception, e:
    LocalState.generate_crash_log(e, traceback.format_exc())
    sys.exit(1)
