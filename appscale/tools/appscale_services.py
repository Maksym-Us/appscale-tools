import requests

from appscale_logger import AppScaleLogger
from local_state import LocalState
from render_helper import print_table
from requests.packages.urllib3.exceptions import InsecureRequestWarning


APPS_PATH = "/v1/apps"
SERVICES_PATH = "/v1/apps/{app}/services"
VERSIONS_PATH = "/v1/apps/{app}/services/{service}/versions"


def get_response(host, secret, path):
  """
  Returns a request's response.

  Args:
    host: A string specifying the login host.
    secret: A string specifying the secret key.
    path: A string specifying a path to request
      to apps, services or versions node.
  Returns:
    A dict specifying information from the requested node.
  """
  headers = {
    'Appscale-Secret': secret
  }

  administration_port = "17441"
  url = "https://{host}:{port}{path}".format(
    host=host,
    port=administration_port,
    path=path
  )

  resp = requests.get(
    url=url,
    headers=headers,
    verify=False
  )

  resp.raise_for_status()
  return resp.json()


def sort_services(services):
  """
  Sorts services by project ID, service ID, version and ports.

  Args:
    services: A list specifying the services information.
  Returns:
    A list specifying the sorted services information.
  """
  return sorted(services,
                key=lambda app: (app[0], app[1], app[2], app[3], app[4]))


def print_services(options):
  """
  Prints an information about project's services.

  Args:
    options: A Namespace that has fields for each parameter that can be
      passed in via the command-line interface.
  """
  login_host = LocalState.get_login_host(keyname=options.keyname)
  secret = LocalState.get_secret_key(keyname=options.keyname)

  table_name = "SERVICES INFO"
  services_headers = ["APPLICATION", "SERVICE", "VERSION", "HTTP", "HTTPS"]
  services_dict = {}

  try:
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    apps = get_response(host=login_host, secret=secret, path=APPS_PATH)

    for app in apps:
      services = get_response(
        host=login_host, secret=secret, path=SERVICES_PATH.format(app=app))

      for service in services:
        versions = get_response(
          host=login_host, secret=secret,
          path=VERSIONS_PATH.format(app=app, service=service))

        services_dict[app] = app_info = {}
        app_info[service] = versions

  except requests.HTTPError as e:
    AppScaleLogger.warn("Failed to get services info.")
    AppScaleLogger.warn(e)

  services_info = []
  for app, app_info in services_dict.iteritems():
    for service, service_info in app_info.iteritems():
      for version, version_info in service_info.iteritems():
        services_info.append([
          app,
          service,
          version,
          version_info["http_port"],
          version_info["https_port"]
        ])

  print_table(
    table_name=table_name,
    headers=services_headers,
    data=sort_services(services_info)
  )
