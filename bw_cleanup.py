#!/usr/bin/env python3
"""
Bitwarden Account Cleanup Script
Requires: bw CLI installed and logged in, or will prompt to log in.

Strategy: Instead of deleting anything, flagged items are moved into
review folders (e.g. "Cleanup: Duplicates") so you can inspect them
in the Bitwarden app and decide what to do.
"""

import base64
import json
import subprocess
import sys
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from getpass import getpass

# ── ANSI colors ────────────────────────────────────────────────────────────────
R = "\033[31m"; G = "\033[32m"; Y = "\033[33m"; B = "\033[34m"
BOLD = "\033[1m"; DIM = "\033[2m"; RST = "\033[0m"
C = "\033[36m"

def h1(msg):   print(f"\n{BOLD}{B}{'═'*60}{RST}\n{BOLD}{B}  {msg}{RST}\n{BOLD}{B}{'═'*60}{RST}")
def h2(msg):   print(f"\n{BOLD}{C}── {msg} {'─'*(max(0,55-len(msg)))}{RST}")
def ok(msg):   print(f"  {G}✔{RST}  {msg}")
def warn(msg): print(f"  {Y}⚠{RST}  {msg}")
def err(msg):  print(f"  {R}✘{RST}  {msg}")
def info(msg): print(f"  {DIM}{msg}{RST}")

# ── Bitwarden helpers ──────────────────────────────────────────────────────────

def bw(args, stdin=None, check=True):
    env = os.environ.copy()
    result = subprocess.run(
        ["bw"] + args,
        capture_output=True, text=True,
        input=stdin, env=env,
    )
    if check and result.returncode != 0:
        err(f"bw error: {result.stderr.strip()}")
        sys.exit(1)
    return result.stdout.strip()

def bw_encode(obj):
    """Return the base64-encoded JSON string that bw edit/create expect via stdin."""
    return base64.b64encode(json.dumps(obj).encode()).decode()

def ensure_unlocked():
    if os.environ.get("BW_SESSION"):
        return
    status_raw = bw(["status"], check=False)
    try:
        status = json.loads(status_raw)
    except Exception:
        status = {}
    vault_status = status.get("status", "unauthenticated")
    if vault_status == "unauthenticated":
        print("You are not logged in to Bitwarden.")
        email = input("Email: ").strip()
        password = getpass("Master password: ")
        session = bw(["login", email, password, "--raw"])
        os.environ["BW_SESSION"] = session
        ok("Logged in successfully.")
    elif vault_status == "locked":
        print("Vault is locked. Enter your master password to unlock.")
        password = getpass("Master password: ")
        session = bw(["unlock", password, "--raw"])
        os.environ["BW_SESSION"] = session
        ok("Vault unlocked.")
    else:
        ok(f"Vault already unlocked (status: {vault_status}).")

def load_items():
    return json.loads(bw(["list", "items", "--session", os.environ["BW_SESSION"]]))

def load_folders():
    return json.loads(bw(["list", "folders", "--session", os.environ["BW_SESSION"]]))

def get_uri(item):
    try:
        return item["login"]["uris"][0]["uri"] or ""
    except (KeyError, IndexError, TypeError):
        return ""

def get_username(item):
    try:
        return (item["login"].get("username") or "").strip()
    except (KeyError, TypeError):
        return ""

def get_password(item):
    try:
        return (item["login"].get("password") or "").strip()
    except (KeyError, TypeError):
        return ""

def get_name(item):
    return item.get("name", "(no name)")

def domain(uri):
    uri = re.sub(r"^https?://", "", uri.strip())
    uri = re.sub(r"/.*", "", uri)
    return re.sub(r"^www\.", "", uri).lower()

# ── Folder management ─────────────────────────────────────────────────────────

CLEANUP_FOLDERS = {
    "duplicates":  "Cleanup: Duplicates",
    "reused":      "Cleanup: Reused Passwords",
    "weak":        "Cleanup: Weak Passwords",
    "incomplete":  "Cleanup: Incomplete",
    "stale":       "Cleanup: Stale",
}

_folder_cache = {}  # name -> id

def get_or_create_folder(name, folders):
    """Return folder id for name, creating it if it doesn't exist."""
    if name in _folder_cache:
        return _folder_cache[name]
    # Check existing folders
    match = next((f for f in folders if f["name"] == name), None)
    if match:
        _folder_cache[name] = match["id"]
        return match["id"]
    # Create it
    raw = bw(["create", "folder", "--session", os.environ["BW_SESSION"]],
             stdin=bw_encode({"name": name}))
    folder = json.loads(raw)
    _folder_cache[name] = folder["id"]
    folders.append(folder)
    ok(f"Created folder '{name}'.")
    return folder["id"]

def move_item_to_folder(item, folder_id):
    """Set folderId on item and push the edit to Bitwarden."""
    item = dict(item)
    item["folderId"] = folder_id
    bw(["edit", "item", item["id"], "--session", os.environ["BW_SESSION"]],
       stdin=bw_encode(item))
    return item

def tag_items(items_to_tag, folder_key, folders, already_moved):
    """
    Move items_to_tag into the appropriate cleanup folder.
    Skips items already moved in this run.
    Returns count of newly moved items.
    """
    folder_name = CLEANUP_FOLDERS[folder_key]
    folder_id = get_or_create_folder(folder_name, folders)
    moved = 0
    for item in items_to_tag:
        if item["id"] in already_moved:
            continue
        if item.get("folderId") == folder_id:
            info(f"Already in folder: {get_name(item)}")
            already_moved.add(item["id"])
            continue
        move_item_to_folder(item, folder_id)
        ok(f"→ '{folder_name}': {get_name(item)}")
        already_moved.add(item["id"])
        moved += 1
    return moved

# ── Analysis functions ─────────────────────────────────────────────────────────

def find_duplicates(items):
    groups = defaultdict(list)
    for item in items:
        if item.get("type") != 1:
            continue
        d = domain(get_uri(item)) or "(no url)"
        u = get_username(item).lower()
        groups[(d, u)].append(item)
    return {k: v for k, v in groups.items() if len(v) > 1}

def find_reused_passwords(items):
    groups = defaultdict(list)
    for item in items:
        if item.get("type") != 1:
            continue
        pwd = get_password(item)
        if pwd:
            groups[pwd].append(item)
    return {k: v for k, v in groups.items() if len(v) > 1}

def find_weak_passwords(items, min_length=12):
    return [
        item for item in items
        if item.get("type") == 1 and 0 < len(get_password(item)) < min_length
    ]

def parse_bw_date(date_str):
    """Parse Bitwarden's ISO date string to a UTC-aware datetime, or None."""
    if not date_str:
        return None
    try:
        # Bitwarden uses e.g. "2019-04-12T08:33:20.123Z"
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None

def find_stale(items, revision_years=3, creation_years=5):
    """
    Flag logins that haven't been touched in a while:
      - revisionDate older than revision_years  (or)
      - no revisionDate but creationDate older than creation_years
    Returns list of (item, age_description) tuples.
    """
    now = datetime.now(timezone.utc)
    result = []
    for item in items:
        if item.get("type") != 1:
            continue
        revised = parse_bw_date(item.get("revisionDate"))
        created = parse_bw_date(item.get("creationDate"))
        if revised:
            age_days = (now - revised).days
            threshold_days = revision_years * 365
            if age_days > threshold_days:
                years = age_days // 365
                result.append((item, f"not revised in {years}y  (last: {revised.strftime('%Y-%m-%d')})"))
        elif created:
            age_days = (now - created).days
            threshold_days = creation_years * 365
            if age_days > threshold_days:
                years = age_days // 365
                result.append((item, f"no revision date, created {years}y ago  ({created.strftime('%Y-%m-%d')})"))
    return result

def find_incomplete(items):
    result = []
    for item in items:
        if item.get("type") != 1:
            continue
        issues = []
        if not get_uri(item):      issues.append("no URL")
        if not get_username(item): issues.append("no username")
        if not get_password(item): issues.append("no password")
        if issues:
            result.append((item, issues))
    return result

# ── Display helpers ────────────────────────────────────────────────────────────

def print_item(item, index=None, total=None):
    prefix = f"[{index}/{total}] " if index and total else ""
    print(f"\n  {BOLD}{prefix}{get_name(item)}{RST}")
    uri  = get_uri(item)
    user = get_username(item)
    pwd  = get_password(item)
    if uri:  info(f"URL:      {uri}")
    if user: info(f"Username: {user}")
    if pwd:  info(f"Password: {'*' * min(len(pwd), 20)}  (len={len(pwd)})")

def confirm(prompt):
    while True:
        c = input(f"  {BOLD}{prompt} [y/n]:{RST} ").strip().lower()
        if c in ("y", "n"):
            return c == "y"

# ── Sections ──────────────────────────────────────────────────────────────────

def section_duplicates(items, folders, already_moved):
    h1("1. Duplicate Entries")
    dupes = find_duplicates(items)
    if not dupes:
        ok("No duplicates found.")
        return

    flagged = [item for group in dupes.values() for item in group]
    total_groups = len(dupes)
    print(f"  Found {len(flagged)} item(s) across {total_groups} duplicate group(s):\n")

    for gi, ((d, u), group) in enumerate(dupes.items(), 1):
        h2(f"Group {gi}/{total_groups}: {d} / {u or '(no username)'}")
        for i, item in enumerate(group, 1):
            print_item(item, i, len(group))

    print()
    if confirm(f"Move all {len(flagged)} duplicate item(s) to '{CLEANUP_FOLDERS['duplicates']}'?"):
        n = tag_items(flagged, "duplicates", folders, already_moved)
        ok(f"Moved {n} item(s).")
    else:
        info("Skipped.")


def section_reused_passwords(items, folders, already_moved):
    h1("2. Reused Passwords")
    groups = find_reused_passwords(items)
    if not groups:
        ok("No reused passwords found.")
        return

    flagged = [item for group in groups.values() for item in group]
    print(f"  Found {len(flagged)} item(s) sharing passwords across {len(groups)} group(s):\n")

    for gi, (_, group) in enumerate(groups.items(), 1):
        h2(f"Shared password group {gi}/{len(groups)}  ({len(group)} accounts)")
        for i, item in enumerate(group, 1):
            print_item(item, i, len(group))

    print()
    if confirm(f"Move all {len(flagged)} item(s) to '{CLEANUP_FOLDERS['reused']}'?"):
        n = tag_items(flagged, "reused", folders, already_moved)
        ok(f"Moved {n} item(s).")
    else:
        info("Skipped.")


def section_weak_passwords(items, folders, already_moved):
    h1("3. Weak Passwords  (< 12 characters)")
    weak = find_weak_passwords(items)
    if not weak:
        ok("No weak passwords found.")
        return

    print(f"  Found {len(weak)} item(s) with short passwords:\n")
    for i, item in enumerate(weak, 1):
        print_item(item, i, len(weak))
        info(f"Password length: {len(get_password(item))}")

    print()
    if confirm(f"Move all {len(weak)} item(s) to '{CLEANUP_FOLDERS['weak']}'?"):
        n = tag_items(weak, "weak", folders, already_moved)
        ok(f"Moved {n} item(s).")
    else:
        info("Skipped.")


def section_incomplete(items, folders, already_moved):
    h1("4. Incomplete Entries")
    incomplete = find_incomplete(items)
    if not incomplete:
        ok("All login entries appear complete.")
        return

    flagged = [item for item, _ in incomplete]
    print(f"  Found {len(flagged)} item(s) with missing fields:\n")
    for i, (item, issues) in enumerate(incomplete, 1):
        print_item(item, i, len(incomplete))
        warn("Issues: " + ", ".join(issues))

    print()
    if confirm(f"Move all {len(flagged)} item(s) to '{CLEANUP_FOLDERS['incomplete']}'?"):
        n = tag_items(flagged, "incomplete", folders, already_moved)
        ok(f"Moved {n} item(s).")
    else:
        info("Skipped.")


def section_stale(items, folders, already_moved):
    h1("5. Stale Accounts")
    print(f"  Rules:")
    print(f"    • Revised date exists but older than 3 years")
    print(f"    • No revised date and created more than 5 years ago")
    stale = find_stale(items)
    if not stale:
        ok("No stale accounts found.")
        return

    flagged = [item for item, _ in stale]
    print(f"\n  Found {len(flagged)} stale item(s):\n")
    for i, (item, reason) in enumerate(stale, 1):
        print_item(item, i, len(stale))
        info(reason)

    print()
    if confirm(f"Move all {len(flagged)} item(s) to '{CLEANUP_FOLDERS['stale']}'?"):
        n = tag_items(flagged, "stale", folders, already_moved)
        ok(f"Moved {n} item(s).")
    else:
        info("Skipped.")


def section_summary(items, already_moved):
    h1("Summary")
    login_items = [i for i in items if i.get("type") == 1]
    print(f"  Total login items:    {len(login_items)}")
    print(f"  Items flagged/moved:  {len(already_moved)}")
    print()
    for key, name in CLEANUP_FOLDERS.items():
        count = sum(1 for i in login_items
                    if i.get("folderId") and i["id"] in already_moved
                    and _folder_cache.get(name) == i.get("folderId"))
        if count:
            warn(f"{count} item(s) in '{name}'")
    if already_moved:
        print()
        info("Open Bitwarden and review the 'Cleanup: *' folders.")
        info("Delete or update items there at your own pace.")
        info("When done, run: bw sync")
    else:
        ok("Nothing flagged — vault looks clean!")
    print()
    info("Run 'bw sync' to push folder changes to the server.")
    info("Run 'bw logout' when you're done.")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    h1("Bitwarden Vault Cleanup")
    print("  Flagged items will be moved into review folders:")
    for name in CLEANUP_FOLDERS.values():
        print(f"    • {name}")
    print()
    print(f"  {Y}Nothing is deleted. You review and act at your own pace.{RST}")
    print()

    ensure_unlocked()

    print("\n  Loading vault...")
    items = load_items()
    folders = load_folders()
    login_count = sum(1 for i in items if i.get("type") == 1)
    ok(f"Loaded {len(items)} items ({login_count} logins, {len(folders)} folders).")

    already_moved = set()  # track item ids moved in this run

    section_duplicates(items, folders, already_moved)
    section_reused_passwords(items, folders, already_moved)
    section_weak_passwords(items, folders, already_moved)
    section_incomplete(items, folders, already_moved)
    section_stale(items, folders, already_moved)
    section_summary(items, already_moved)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Y}Interrupted. Run 'bw sync' to push any changes made so far.{RST}\n")
        sys.exit(0)
