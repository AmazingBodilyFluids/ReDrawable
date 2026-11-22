"""CI only (GitHub's macOS runners have SIP off): allow the given programs to post input events
and use Accessibility, by adding rows to the TCC databases, so check_events.py can run unattended.
Never needed or used on a user's Mac, where macOS asks the user instead.

    sudo python3 mac/ci_grant.py /path/to/program [...]
"""
import os
import sqlite3
import sys
import time

DBS = ["/Library/Application Support/com.apple.TCC/TCC.db",
       os.path.expanduser("~%s/Library/Application Support/com.apple.TCC/TCC.db" % os.environ.get("SUDO_USER", ""))]
SERVICES = ["kTCCServiceAccessibility", "kTCCServicePostEvent", "kTCCServiceListenEvent"]

for db in DBS:
    if not os.path.exists(db):
        print("no", db)
        continue
    con = sqlite3.connect(db)
    cols = [r[1] for r in con.execute("PRAGMA table_info(access)")]
    for client in sys.argv[1:]:
        for svc in SERVICES:
            row = {"service": svc, "client": client, "client_type": 1, "auth_value": 2, "auth_reason": 4,
                   "auth_version": 1, "allowed": 1, "prompt_count": 1, "flags": 0, "indirect_object_identifier": "UNUSED",
                   "last_modified": int(time.time()), "boot_uuid": "UNUSED", "pid": None, "pid_version": None,
                   "last_reminded": 0, "indirect_object_identifier_type": 0}
            use = [c for c in cols if c in row]
            try:
                con.execute("INSERT OR REPLACE INTO access (%s) VALUES (%s)" % (",".join(use), ",".join("?" * len(use))),
                            [row[c] for c in use])
                print("granted", svc, client, "in", db)
            except sqlite3.Error as ex:
                print("couldn't grant", svc, client, "in", db, ex)
    con.commit()
