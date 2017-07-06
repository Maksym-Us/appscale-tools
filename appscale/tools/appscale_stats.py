import requests

from appcontroller_client import AppControllerClient
from local_state import LocalState

from tabulate import tabulate
from appscale_logger import AppScaleLogger


# Fields needed to nodes statistics
INCLUDE_NODE_LIST = {
  'node': ['memory', 'loadavg', 'partitions_dict'],
  'node.loadavg': ['last_1min', 'last_5min', 'last_15min'],
  'node.partition': ['used', 'total'],

}

# Fields needed to processes statistics
INCLUDE_PROCESS_LIST = {
  'process': ['unified_service_name', 'application_id', 'monit_name', 'memory',
              'cpu', 'children_num', 'children_stats_sum'],
  'process.memory': ['unique'],
  'process.cpu': ['percent'],
  'process.children_stats_sum': ['memory', 'cpu']
}

# Fields needed list to processes statistics
INCLUDE_NODE_LIST_FOR_PROCESSES = {
  'node': ['cpu'],
  'node.cpu': ['count']
}

# Fields needed list to proxies statistics
INCLUDE_PROXY_LIST = {
  'proxy': ['unified_service_name', 'application_id', 'servers_count',
            'frontend', 'backend'],
  'proxy.frontend': ['req_rate', 'req_tot', 'hrsp_5xx', 'hrsp_4xx',
                     'bin', 'bout', 'scur'],
  'proxy.backend': ['qtime', 'rtime', 'qcur']
}


def _get_stats(keyname, stats_kind, include_lists):
  """
  Returns statistics from Hermes.

  Args:
    keyname: A string representing an identifier from AppScaleFile.
    path: A string representing one of 'nodes', 'processes' or 'proxies'.
    include_lists: A list representing a list of desired fields.
  """
  login_host = LocalState.get_login_host(keyname=keyname)
  secret = LocalState.get_secret_key(keyname=keyname)
  hermes_port = "17441"
  stats_path = "/stats/cluster/{stats_kind}".format(stats_kind=stats_kind)

  headers = {
    'Appscale-Secret': str(secret)
  }

  data = {
    'include_lists': include_lists
  }

  url = "https://{ip}:{port}{path}".format(
    ip=login_host,
    port=hermes_port,
    path=stats_path
  )

  resp = requests.get(url=url, headers=headers, json=data).json()

  return resp["stats"], resp["failures"]


def show_stats(options):
  """
  Prints nodes, processes and/or proxies statistics nicely.

  Args:
    options: A Namespace that has fields for each parameter that can be
      passed in via the command-line interface.
  """
  failures = {}

  if "nodes" in options.show:
    nodes_header, nodes_stats, nodes_failures = get_node_stats(
      keyname=options.keyname,
      specified_roles=options.roles,
      verbose=options.verbose)
    print_table(
      table_name="NODES STATISTICS",
      headers=nodes_header,
      data=nodes_stats
    )
    if nodes_failures:
      failures["nodes"] = nodes_failures

  if "processes" in options.show:
    if "name" in options.order_processes:
      order = 0 if not options.verbose else 1   # see processes_header
    elif "mem" in options.order_processes:
      order = 2
    elif "cpu" in options.order_processes:
      order = 3

    processes_header, processes_stats, processes_failures = (
      get_proc_stats(keyname=options.keyname)
      if options.verbose
      else get_proc_stats_sum(keyname=options.keyname)
    )
    processes_stats = sort_proc_stats(
      proc_stats=processes_stats,
      column=order,
      top=options.top,
      reverse=False if "name" in options.order_processes else True
    )
    print_table(
      table_name="SUMMARY PROCESSES STATISTICS"
      if not options.verbose else "PROCESSES STATISTICS",
      headers=processes_header,
      data=processes_stats
    )
    if processes_failures:
      failures["processes"] = processes_failures

  if "proxies" in options.show:
    proxies_header, proxies_stats, proxies_failures = get_prox_stats(
      keyname=options.keyname,
      verbose=options.verbose,
      apps_filter=options.apps_only
    )
    proxies_stats = sort_prox_stats(
      prox_stats=proxies_stats,
      column=0
    )
    print_table(
      table_name="PROXIES STATISTICS",
      headers=proxies_header,
      data=proxies_stats
    )
    if proxies_failures:
      failures["proxies"] = proxies_failures

  if failures:
    print_failures(failures=failures)


def get_marked(data, mark):
  """
  Args:
    data: An object to be marked in.
    mark: A string representing one of marks ('red', 'green' or 'bold').

  Returns:
    A string marked in.
  """
  marks = {
    "red": "\033[91m",
    "green": "\033[92m",
    "bold": "\033[1m"
  }
  return marks[mark] + str(data) + "\033[0m"


def render_loadavg(loadavg):
  """
  Args:
    loadavg: A dict representing a list of loadavg values.

  Returns:
    A string with information about node loadavg
    last 1, 5 and 15 minuts in format: "last 1min / last 5min / last 15min"
    and marked in red if loadavg is more than 2.0.
  """
  limit_value = 2.0
  last_1 = loadavg["last_1min"]
  last_5 = loadavg["last_5min"]
  last_15 = loadavg["last_15min"]
  return "{} / {} / {}".format(
    last_1 if last_1 < limit_value else get_marked(last_1, "red"),
    last_5 if last_5 < limit_value else get_marked(last_5, "red"),
    last_15 if last_15 < limit_value else get_marked(last_15, "red")
  )


def render_partitions(partitions, verbose):
  """
  Args:
    partitions: A dict representing a list of partition values.
    verbose: A boolean - show all partitions if True,
      only three partitions if False.

  Returns:
    A string with information about node partitions
    in format: "partition1: used %, partition2: used %, ..." if not verbose
    and marked in red if partition is used more than 90%.
  """
  part_list = [[part, 100 * value["used"] / value["total"]]
               for part, value in
               partitions.iteritems()]  # calculate percents

  # sort from more used to less used
  part_list.sort(key=lambda p: p[1], reverse=True)

  partitions_info = [
    "'{}': {}%".format(part[0], part[1])
    if part[1] < 90
    else get_marked("'{}': {}%".format(part[0], part[1]), "red")
    for part in part_list
  ]

  if not verbose:
    if len(partitions_info) > 3:
      partitions_info = partitions_info[:3] + ["..."]

  return ", ".join(partitions_info)


def render_memory(memory):
  """
  Args:
    memory: A dict representing a list of memory values.

  Returns:
    A string with information about node memory
    in format: "available % / available MB".
  """
  return "{}% ({} MB)".format(
    (100 * memory["available"] / memory["total"]),
    (memory["available"] / 1024 / 1024)
  )


def get_node_stats(keyname, specified_roles=None, verbose=False):
  """
  Obtaines useful information from nodes statistics and returns:
  IP, AVAILABLE MEMORY, LOADAVG, PARTITIONS USAGE values.

  Args:
    keyname: A string representing an identifier from AppScaleFile.
    specified_roles: A list representing specified roles
      shown nodes should contain.
    verbose: A boolean - show all partitions if True,
      only three partitions if False.

  Returns:
    A list of headers nodes statistics.
    A list of nodes statistics.
  """
  node_stats_headers = ["PRIVATE IP", "AVAILABLE MEMORY", "LOADAVG",
                        "PARTITIONS USAGE", "ROLES"]

  nodes_stats, failures = _get_stats(
    keyname=keyname,
    stats_kind="nodes",
    include_lists=INCLUDE_NODE_LIST
  )

  login_host = LocalState.get_login_host(keyname=keyname)
  login_acc = AppControllerClient(
    login_host,
    LocalState.get_secret_key(keyname)
  )
  all_private_ips = login_acc.get_all_private_ips()
  cluster_stats = login_acc.get_cluster_stats()
  roles_data = {
    ip:
      next(
        n["roles"] for n in cluster_stats if n["private_ip"] == ip
      )
    for ip in all_private_ips
  }

  nodes_info = []
  for ip, node in nodes_stats.iteritems():
    rls = roles_data[ip]
    show = True

    if specified_roles:
      matches = [r for r in specified_roles if r in rls]
      if not matches:
        show = False

    if show:
      if "shadow" not in rls:
        node_info = [
          ip,
          render_memory(memory=node["memory"]),
          render_loadavg(loadavg=node["loadavg"]),
          render_partitions(partitions=node["partitions_dict"], verbose=verbose),
          u", ".join(rls)
        ]
      if "shadow" in rls:
        node_info = [
          get_marked(ip, "bold"),
          get_marked(render_memory(memory=node["memory"]), "bold"),
          get_marked(render_loadavg(loadavg=node["loadavg"]), "bold"),
          get_marked(
            render_partitions(partitions=node["partitions_dict"],
                              verbose=verbose), "bold"
          ),
          get_marked(u", ".join(rls), "bold")
        ]
      nodes_info.append(node_info)

  return node_stats_headers,\
         sorted(nodes_info, key=lambda n: n[0], reverse=False),\
         failures


def sort_proc_stats(proc_stats, column, top=0, reverse=True):
  """
  Returns sorted input list with reverse is False.

  Args:
    proc_stats: A list of processes statistics.
    column: An int representing a column number the list should be sorted by.
    top: An int representing a process count to be printed.
    reverse: A boolean to reverse or not reverse sorted data.
  """
  if top <= 0:
    top = len(proc_stats)

  return sorted(proc_stats, key=lambda p: p[column], reverse=reverse)[:top]


def sort_prox_stats(prox_stats, column):
  """
  Args:
    prox_stats: A list of proxies statistics.
    column: An int is a column number the list should be sorted by.

  Returns:
    A list sorted by specified column.
  """
  return sorted(prox_stats, key=lambda p: p[column], reverse=False)


def get_proc_stats(keyname):
  """
  Obtains useful information from processes statistics and returns:
  IP, MONIT NAME, UNIQUE MEMORY (MB), CPU (%) values.

  Args:
    keyname: A string representing an identifier from AppScaleFile.

  Returns:
    A list of headers processes statistics.
    A list of processes statistics.
  """
  proc_stats_headers = ["PRIVATE IP", "MONIT NAME",
                        "UNIQUE MEMORY (MB)", "CPU (%)"]

  proc_stats, failures = _get_stats(
    keyname=keyname,
    stats_kind="processes",
    include_lists=INCLUDE_PROCESS_LIST
  )

  proc_info = []
  for ip, node in proc_stats.iteritems():
    stat = node.get("processes_stats")
    for proc in stat:
      memory_unique = int(proc["memory"]["unique"])
      cpu_percent = float(proc["cpu"]["percent"])
      if proc["children_num"] > 0:
        child = proc["children_stats_sum"]
        memory_unique += int(child["memory"]["unique"])
        cpu_percent += float(child["cpu"]["percent"])
      proc_info.append([
        ip,
        proc["monit_name"],
        memory_unique / 1024 / 1024,  # row[2] from B to MB
        cpu_percent
      ])

  return proc_stats_headers, proc_info, failures


def get_proc_stats_sum(keyname):
  """
  Obtains useful information from processes summary statistics and returns:
  SERVICE (ID), INSTANCES, UNIQUE MEMORY SUM (MB),
  CPU SUM (%), CPU PER 1 PROCESS (%), CPU PER 1 CORE (%) values.

  Args:
    keyname: A string representing an identifier from AppScaleFile.

  Returns:
    A list of headers processes summary statistics.
    A list of processes summary statistics.
  """
  nodes_stats, nodes_failures = _get_stats(
    keyname=keyname,
    stats_kind='nodes',
    include_lists=INCLUDE_NODE_LIST_FOR_PROCESSES
  )
  print nodes_stats
  cpu_count = sum(
    int(node["cpu"]["count"])
    for node in nodes_stats.itervalues()
  )

  procs_info = []
  proc_list = []
  added = set()

  proc_stats_sum_headers = ["SERVICE (ID)", "INSTANCES",
                            "UNIQUE MEMORY SUM (MB)", "CPU SUM (%)",
                            "CPU PER 1 PROCESS (%)", "CPU PER 1 CORE (%)"]

  processes_stats, failures = _get_stats(
    keyname=keyname,
    stats_kind="processes",
    include_lists=INCLUDE_PROCESS_LIST
  )

  for proc in processes_stats.itervalues():
    proc_list += proc["processes_stats"]

  for proc in proc_list:
    name = proc["unified_service_name"]
    app_id = proc["application_id"]
    name_id = name + (" ({})".format(app_id) if app_id else "")
    if name_id in added:  # if calculating with process has been made
      continue

    grouped_procs = [p for p in proc_list
                     if p["unified_service_name"] == name
                     and p["application_id"] == app_id]

    added.add(name_id)
    unique_memory = 0
    cpu_percent = 0

    for p in grouped_procs:
      unique_memory += int(p["memory"]["unique"])
      cpu_percent += float(p["cpu"]["percent"])
      if p["children_num"] > 0:
        child = p["children_stats_sum"]
        unique_memory += int(child["memory"]["unique"])
        cpu_percent += float(child["cpu"]["percent"])

    avg_cpu_per_process = cpu_percent / len(grouped_procs)
    cpu_percent_cpu_count = cpu_percent / cpu_count

    procs_info.append([
      name_id,
      len(grouped_procs),
      unique_memory / 1024 / 1024,  # row[2] from B to MB
      cpu_percent,
      avg_cpu_per_process,
      cpu_percent_cpu_count
    ])

  return proc_stats_sum_headers, procs_info, failures


def get_prox_stats(keyname, verbose=False, apps_filter=False):
  """
  Obtains useful information from processes summary statistics and returns:
  SERVICE (ID), UNIQUE MEMORY SUM (MB), CPU PER 1 PROCESS (%),
  CPU PER 1 CORE (%), CPU SUM (%) values.

  Args:
    keyname: A string representing an identifier from AppScaleFile.
    verbose: A boolean - verbose or not verbose mode.
    apps_filter: A boolean - show all services or applications only.

  Returns:
    A list of headers proxies statistics.
    A list of proxies statistics.
  """
  prox_stats_headers = ["SERVICE | ID", "SERVERS", "REQ RATE / REQ TOTAL",
                        "5xx / 4xx", "QUEUE CUR"]

  prox_stats_headers_verbose = ["SERVICE (ID)", "SERVERS",
                                "REQ RATE / REQ TOTAL",
                                "5xx / 4xx", "BYTES IN / BYTES OUT",
                                "SESSION CUR / QUEUE CUR", "QTIME / RTIME"]

  prox_info = []
  proxies = []
  uniq_proxies = {}

  proxies_stats, failures = _get_stats(
    keyname=keyname,
    stats_kind="proxies",
    include_lists=INCLUDE_PROXY_LIST
  )

  for node in proxies_stats.itervalues():
    proxies += node[
      "proxies_stats"]  # proxies += list of dicts with statistic

  for node in proxies:
    if apps_filter:
      if "application" != node["unified_service_name"]:
        continue
    service_name_id = node["unified_service_name"] \
                      + (" | " + node["application_id"]
                         if node["application_id"]
                         else "")

    if not service_name_id in uniq_proxies:
      uniq_proxies[service_name_id] = {}
      uniq_proxies[service_name_id]["servers_count"] = set()
      uniq_proxies[service_name_id]["req_rate"] = 0
      uniq_proxies[service_name_id]["req_tot"] = 0
      uniq_proxies[service_name_id]["hrsp_5xx"] = 0
      uniq_proxies[service_name_id]["hrsp_4xx"] = 0

      if verbose:
        uniq_proxies[service_name_id]["bin"] = 0
        uniq_proxies[service_name_id]["bout"] = 0
        uniq_proxies[service_name_id]["scur"] = 0
      uniq_proxies[service_name_id]["qcur"] = 0

      if verbose:
        if "qtime" and "rtime" in node["backend"]:
          uniq_proxies[service_name_id]["qtime"] = 0
          uniq_proxies[service_name_id]["rtime"] = 0

    uniq_proxies[service_name_id]["servers_count"] = node["servers_count"]

    uniq_proxies[service_name_id]["req_rate"] += node["frontend"]["req_rate"]
    uniq_proxies[service_name_id]["req_tot"] += node["frontend"]["req_tot"]
    uniq_proxies[service_name_id]["hrsp_5xx"] += node["frontend"]["hrsp_5xx"]
    uniq_proxies[service_name_id]["hrsp_4xx"] += node["frontend"]["hrsp_4xx"]

    if verbose:
      uniq_proxies[service_name_id]["bin"] += node["frontend"]["bin"]
      uniq_proxies[service_name_id]["bout"] += node["frontend"]["bout"]
      uniq_proxies[service_name_id]["scur"] += node["frontend"]["scur"]

    uniq_proxies[service_name_id]["qcur"] += node["backend"]["qcur"]

    if verbose:
      if "qtime" and "rtime" in node["backend"]:
        uniq_proxies[service_name_id]["qtime"] += node["backend"]["qtime"]
        uniq_proxies[service_name_id]["rtime"] += node["backend"]["rtime"]

  for key, value in uniq_proxies.iteritems():
    prox = []
    prox.append(key if not key.startswith("application")
                else key.replace("application", "app", 1))
    prox.append(value["servers_count"])
    prox.append(str(value["req_rate"]) + " / " + str(value["req_tot"]))
    prox.append("{} / {}".format(
      value["hrsp_5xx"] if not value["hrsp_5xx"]
      else get_marked(value["hrsp_5xx"], "red"),
      value["hrsp_4xx"] if not value["hrsp_4xx"]
      else get_marked(value["hrsp_4xx"], "red")
    ))

    if verbose:
      prox.append(str(value["bin"]) + " / " + str(value["bout"]))

    prox.append(
      ((str(value["scur"]) + " / ") if verbose else "") + str(value["qcur"])
    )

    if verbose:
      if "qtime" and "rtime" in value:
        prox.append(str(value["qtime"]) + " / " + str(value["rtime"]))
    prox_info.append(prox)

  return (prox_stats_headers_verbose
          if verbose else prox_stats_headers), prox_info, failures


def print_table(table_name, headers, data):
  """
  Prints a list of statistics with specified header.

  Args:
    table_name: A string is a name of table.
    headers: A list of headers of statistics.
    data: A list of statistics.
  """
  if data:
    t = tabulate(data, headers=headers, tablefmt='simple',
                 floatfmt=".1f", numalign="right", stralign="left")
    first_n = t.find("\n")
    i = t.find("\n", first_n + 1) - first_n - 1
    AppScaleLogger.log(
      get_marked((("=") * ((i - len(table_name) - 2) / 2))
                     + " " + table_name + " "
                     + (("=") * (((i - len(table_name) - 2) / 2)
                                 + (1 if i % 2 == 1 else 0))), "green"))
    AppScaleLogger.log(t + "\n")
  else:
    t = tabulate(data, headers=headers, tablefmt='simple',
                 floatfmt=".1f", numalign="right", stralign="left")
    first_n = t.find("\n")
    i = len(t) - first_n - 1
    AppScaleLogger.log(
      get_marked(("=" * ((i - len(table_name) - 2) / 2))
                 + " " + table_name + " "
                 + ("=" * (((i - len(table_name) - 2) / 2)
                           + (1 if i % 2 == 1 else 0))), "green"))
    AppScaleLogger.log(t + "\n")


def print_failures(failures):
  stats_kinds = {
    "nodes": "Node",
    "processes": "Process",
    "proxies": "Proxy"
  }

  AppScaleLogger.warn("There are some failures while getting stats:")
  for kind, fails in failures.iteritems():
    for ip, failure in fails.iteritems():
      AppScaleLogger.warn(
        "  {stats_kind} stats from {ip}: {failure}".format(
          stats_kind=stats_kinds[kind],
          ip=ip,
          failure=failure
        )
      )
