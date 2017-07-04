import json
import requests

from tabulate import tabulate
from appscale_logger import AppScaleLogger


INCLUDE_NODE_LIST = {
  'node': ['memory', 'loadavg', 'partitions_dict'],
  'node.loadavg': ['last_1min', 'last_5min', 'last_15min'],
  'node.partition': ['used', 'total'],

}

INCLUDE_PROCESS_LIST = {
  'process': ['unified_service_name', 'application_id', 'monit_name', 'memory',
              'cpu', 'children_num', 'children_stats_sum'],
  'process.memory': ['unique'],
  'process.cpu': ['percent'],
  'process.children_stats_sum': ['memory', 'cpu']
}

INCLUDE_PROXY_LIST = {
  'proxy': ['unified_service_name', 'application_id', 'servers',
            'frontend', 'backend'],
  'proxy.servers': ['req_rate', 'req_tot', 'hrsp_5xx', 'hrsp_4xx',
                    'bin', 'bout', 'scur', 'qcur'],
  'proxy.frontend': ['req_rate', 'req_tot', 'hrsp_5xx', 'hrsp_4xx',
                     'bin', 'bout', 'scur'],
  'proxy.backend': ['qtime', 'rtime', 'qcur']
}


def encode_dict(d, codec='utf8'):
  ks = d.keys()
  for k in ks:
    val = d.pop(k)
    if isinstance(val, unicode):
      val = val.encode(codec)
    elif isinstance(val, dict):
      val = encode_dict(val, codec)
    if isinstance(k, unicode):
      k = k.encode(codec)
    d[k] = val
  return d

# get_nodes_stats():
#   _get_stats()
# get_processes_stats():
#   _get_stats()
# get_proxies_stats():
#   _get_stats()
# _get_stats(host, secret)


def get_stats(ip, secret, nodes=True, processes=False, proxies=True):
  """
  Returns stats from HERMES.
  """
  stats = {}

  url = "http://192.168.33.10:4378/stats/cluster/nodes"

  arguments = {
    'include_lists': INCLUDE_NODE_LIST
  }

  headers = {
    'Appscale-Secret': str(secret)
  }

  r = requests.get(url=url, data=json.dumps(arguments), headers=headers)
  # cont = r._content
  # dec = json.JSONDecoder()
  # nodes = json.JSONDecoder().decode(r._content)
  nodes = encode_dict(json.JSONDecoder().decode(r._content))

  stats["nodes"] = nodes      # response['stats]

  return stats


def get_marked(data, mark):
  """
  Returns:
    A string marked in red.
  """
  marks = {
    "red": "\033[91m",
    "green": "\033[92m",
    "bold": "\033[1m"
  }
  return marks[mark] + str(data) + "\033[0m"


def render_loadavg(loadavg):
  """
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

  
def render_partitions(partitions):
  """
  Returns:
    A string with information about node partitions
    in format: "partition1: used %, partition2: used %, ..."
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

  if len(partitions_info) > 3:
    partitions_info = partitions_info[:3] + ["..."]

  return ", ".join(partitions_info)


def render_memory(memory):
  """
  Returns:
    A string with information about node memory
    in format: "available % / available MB".
  """
  return "{}% ({} MB)".format(
    (100 * memory["available"] / memory["total"]),
    (memory["available"] / 1024 / 1024)
  )


def get_roles(roles, ip):
  return roles[ip]


def get_node_stats(nodes_stats, roles, specified_roles=None):
  """
  Obtaines useful information from nodes statistics and returns:
  IP, AVAILABLE MEMORY, LOADAVG, PARTITIONS USAGE values.
  Returns:
    A list of headers nodes statistics.
    A list of nodes statistics.
  """
  node_stats_headers = ["PRIVATE IP", "AVAILABLE MEMORY", "LOADAVG",
                        "PARTITIONS USAGE", "ROLES"]

  nodes_info = []
  for ip, node in nodes_stats.iteritems():
    rls = get_roles(roles=roles, ip=ip)
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
          render_partitions(partitions=node["partitions_dict"]),
          u", ".join(rls)
        ]
      if "shadow" in rls:
        node_info = [
          get_marked(ip, "bold"),
          get_marked(render_memory(memory=node["memory"]), "bold"),
          get_marked(render_loadavg(loadavg=node["loadavg"]), "bold"),
          get_marked(
            render_partitions(partitions=node["partitions_dict"]), "bold"),
          get_marked(u", ".join(rls), "bold")
        ]
      nodes_info.append(node_info)

  return node_stats_headers, \
         sorted(nodes_info, key=lambda n: n[0], reverse=False)


def sort_proc_stats(proc_stats, column, top=None, reverse=True):
  """
  Returns sorted input list with reverse is False.
  Args:
    data_list: A list of proxies statistics.
    column: An int is a column number the list should be sorted by.
    top: A list of instances to be printed.
  """
  if not top:
    top = len(proc_stats)

  return sorted(proc_stats, key=lambda p: p[column], reverse=reverse)[:top]

def sort_prox_stats(prox_stats, column):
  """
  Returns sorted input list with reverse is False.
  Args:
    data_list: A list of proxies statistics.
    column: An int is a column number the list should be sorted by.
  """
  return sorted(prox_stats, key=lambda p: p[column], reverse=False)

def get_proc_stats(proc_stats, instances=False):
  """
  Obtains useful information from processes statistics and returns:
  IP, MONIT NAME, UNIQUE MEMORY (MB), CPU (%) values.
  Returns:
    A list of headers processes statistics.
    A list of processes statistics.
  """
  proc_stats_headers = ["PRIVATE IP", "MONIT NAME",
                        "UNIQUE MEMORY (MB)", "CPU (%)"]

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

  return proc_stats_headers, proc_info

def get_proc_stats_sum(processes_stats, nodes_stats):
  """
  Obtains useful information from processes summary statistics and returns:
  SERVICE (ID), UNIQUE MEMORY SUM (MB), CPU PER 1 PROCESS (%),
  CPU PER 1 CORE (%), CPU SUM (%) values.
  Args:
    processes_stats: A dict of a processes statistics.
    cpu_count: An int - cpu count.
  Returns:
    A list of headers processes summary statistics.
    A list of processes summary statistics.
  """
  cpu_count = sum(int(node["cpu"]["count"])
                  for node in nodes_stats.itervalues())

  procs_info = []
  proc_list = []
  added = set()

  proc_stats_sum_headers = ["SERVICE (ID)", "INSTANCES",
                            "UNIQUE MEMORY SUM (MB)", "CPU SUM (%)",
                            "CPU PER 1 PROCESS (%)", "CPU PER 1 CORE (%)"]

  for proc in processes_stats.itervalues():
    proc_list += proc["processes_stats"]

  for proc in proc_list:
    name = proc["unified_service_name"]
    id = proc["application_id"]
    name_id = name + (" ({})".format(id) if id else "")
    if name_id in added:  # if calculating with process has been made
      continue

    grouped_procs = [p for p in proc_list
                     if p["unified_service_name"] == name
                     and p["application_id"] == id]

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

  return proc_stats_sum_headers, procs_info

def get_prox_stats(proxies_stats, verbose=False, apps_filter=False):
  """
  Obtains useful information from processes summary statistics and returns:
  SERVICE (ID), UNIQUE MEMORY SUM (MB), CPU PER 1 PROCESS (%),
  CPU PER 1 CORE (%), CPU SUM (%) values.
  Args:
    proxies_stats: A dict of a proxies statistics.
    verbose: A bool - verbose or not verbose mode.
    apps_filter: A bool - show all services or applications only.
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
      uniq_proxies[service_name_id]["servers"] = set()
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

    uniq_proxies[service_name_id]["servers"].update(set(
      server["svname"] for server in node["servers"]
    ))

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
    prox.append(len(value["servers"]))
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
          if verbose else prox_stats_headers), prox_info

def get_core_count(node_stats):
  """
  Returns a core count of node.
  """
  return sum(int(node["cpu"]["count"]) for node in node_stats.itervalues())

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
      get_marked((("=") * ((i - len(table_name) - 2) / 2))
                     + " " + table_name + " "
                     + (("=") * (((i - len(table_name) - 2) / 2)
                                 + (1 if i % 2 == 1 else 0))), "green"))
    AppScaleLogger.log(t + "\n")