"""tools/data_branch.sh against a real git remote.

`main` requires pull requests, so the workflow's push of data/meetings.json to
it is rejected (GH006) and the deploy is skipped -- every run, because
store.save() stamps generated_at each time (issue #4). The store lives on an
unprotected `data` branch instead: restore overlays it before the build,
persist pushes it back only when the MEETINGS changed, not the timestamp. The
copy on main is the seed.

Shape borrowed from civic-watch's tests/test_state_branch.py: a bare repo as
origin, shallow clones as actions/checkout, the real script driving both verbs.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "tools", "data_branch.sh")

SEED = {"generated_at": "2026-09-01T00:00:00+00:00",
        "meetings": [{"uid": "a", "body": "County Board"}]}


def git(*args, cwd, **kw):
    return subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True, **kw)


@unittest.skipUnless(shutil.which("git") and shutil.which("bash"), "needs git and bash")
class DataBranchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.remote = os.path.join(self.tmp, "origin.git")
        git("init", "--bare", "--initial-branch=main", self.remote, cwd=self.tmp)
        seed = os.path.join(self.tmp, "seed")
        git("clone", self.remote, seed, cwd=self.tmp)
        self.write(seed, SEED)
        git("add", "data/meetings.json", cwd=seed)
        git("commit", "-m", "seed", cwd=seed)
        git("push", "origin", "main", cwd=seed)

    def write(self, root, data):
        path = os.path.join(root, "data", "meetings.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)   # store.save()'s shape
            fh.write("\n")

    def read(self, root):
        with open(os.path.join(root, "data", "meetings.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def checkout(self, name):
        wt = os.path.join(self.tmp, name)
        git("clone", "--depth=1", "--branch=main", "file://" + self.remote, wt, cwd=self.tmp)
        return wt

    def run_script(self, wt, verb, check=True):
        return subprocess.run(["bash", SCRIPT, verb], cwd=wt, check=check,
                              capture_output=True, text=True)

    def branch_log(self):
        return git("log", "--format=%H", "data", cwd=self.remote).stdout.split()

    # --- restore -------------------------------------------------------------

    def test_restore_uses_the_seed_when_no_branch_exists(self):
        wt = self.checkout("first")
        res = self.run_script(wt, "restore")
        self.assertIn("no 'data' branch yet", res.stdout)
        self.assertEqual(self.read(wt), SEED)

    def test_persist_creates_the_branch_and_a_fresh_runner_restores_it(self):
        wt = self.checkout("first")
        self.run_script(wt, "restore")
        grown = {"generated_at": "2026-09-23T13:00:00+00:00",
                 "meetings": SEED["meetings"] + [{"uid": "b", "body": "Plan Commission"}]}
        self.write(wt, grown)
        res = self.run_script(wt, "persist")
        self.assertIn("pushed", res.stdout)
        self.assertEqual(len(self.branch_log()), 1)

        nxt = self.checkout("second")
        self.assertEqual(self.read(nxt), SEED, "main still carries the seed")
        self.run_script(nxt, "restore")
        self.assertEqual(self.read(nxt), grown, "the runner sees the persisted store")

    # --- persist -------------------------------------------------------------

    def test_a_timestamp_only_change_pushes_nothing(self):
        """store.save() bumps generated_at every run; that must not be a commit."""
        wt = self.checkout("first")
        self.write(wt, {**SEED, "generated_at": "2026-09-23T13:00:00+00:00"})
        self.run_script(wt, "persist")                       # branch born
        before = self.branch_log()
        self.write(wt, {**SEED, "generated_at": "2026-09-24T13:00:00+00:00"})
        res = self.run_script(wt, "persist")
        self.assertIn("no data change", res.stdout)
        self.assertEqual(self.branch_log(), before)

    def test_a_meeting_change_pushes_a_child_commit(self):
        wt = self.checkout("first")
        self.write(wt, SEED)
        self.run_script(wt, "persist")
        self.write(wt, {**SEED, "meetings": SEED["meetings"] + [{"uid": "c", "body": "Council"}]})
        self.run_script(wt, "persist")
        log = self.branch_log()
        self.assertEqual(len(log), 2)
        parents = git("log", "-1", "--format=%P", "data", cwd=self.remote).stdout.split()
        self.assertEqual(parents, [log[1]], "second commit descends from the first")

    def test_persist_refuses_when_the_store_is_missing(self):
        wt = self.checkout("first")
        os.remove(os.path.join(wt, "data", "meetings.json"))
        res = self.run_script(wt, "persist", check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("missing", res.stdout)

    def test_the_branch_explains_itself(self):
        wt = self.checkout("first")
        self.write(wt, SEED)
        self.run_script(wt, "persist")
        readme = git("show", "data:README.md", cwd=self.remote).stdout
        self.assertIn("Machine-written", readme)
        self.assertIn("data/meetings.json", readme)


if __name__ == "__main__":
    unittest.main()
