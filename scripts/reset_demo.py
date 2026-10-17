"""Put the demo back to its starting point between takes.

Removes the shared work queue and the playbooks from the graph and deletes the saved approvals. Restart the server
afterwards (it keeps approvals in memory while it runs) and open the site in a private window for a fresh visitor.
"""

from __future__ import annotations

from plumbline.api.sessions import state_file
from plumbline.graph.client import connect
from plumbline.memory.replay import reset


def main() -> None:
    graph = connect()
    tasks = int(graph.query("MATCH (n) WHERE n:Task OR n:Playbook DETACH DELETE n").nodes_deleted)
    reset(graph)  # decision memory goes back to the loaded graph; the replay rebuilds it on the first request
    path = state_file()
    removed = bool(path and path.exists())
    if removed:
        path.unlink()
    print(f"removed {tasks} work-queue and playbook nodes; saved approvals {'deleted' if removed else 'were not present'}")
    print("now restart the server and open the site in a private window")


if __name__ == "__main__":
    main()
