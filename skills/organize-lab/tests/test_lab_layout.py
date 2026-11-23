from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("lab_layout", SCRIPTS / "lab_layout.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules["lab_layout"] = MODULE
SPEC.loader.exec_module(MODULE)


def _fs_case_sensitive() -> bool:
    """False on typical macOS APFS (case-insensitive); True on Linux CI."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "aBcDeFgH").write_text("x", encoding="utf-8")
        return not (root / "abcdefgh").exists()


_CASE_SENSITIVE = _fs_case_sensitive()
_SKIP_CASE = unittest.skipUnless(
    _CASE_SENSITIVE,
    "needs a case-sensitive filesystem (report.md vs REPORT.md)",
)

LAB = "2026-07-01-alpha"
OTHER = "2026-07-02-beta"
COPIED = (f"# Copied\n\n> Transcribed verbatim on 2026-09-27 from `old/notes.md` at abc1234.\n"
          f"> Only this header was added.\n\nSee labs/{LAB}/run.py.\n")

RUN_PY = '''"""Alpha driver."""
import os
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "lib" / "src"))
import helpers
QUEUE = HERE / "queue.json"
BUF = HERE / "buffers" / "x.npz"
OUT = HERE / "results"
VAL = Path(__file__).with_name("queue.json")
SIB = Path(__file__).with_name("helpers.py")
OTHER = os.path.join(os.path.dirname(__file__), "results")
SELF = os.path.abspath(__file__)
'''

LAUNCH_SH = '''#!/bin/bash
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LAB="$(cd "$(dirname "$0")" && pwd)"
"$ROOT/.venv/bin/python" "$LAB/run.py" > "$LAB/run.log"
nohup python labs/2026-07-01-alpha/run.py &
'''

REPORT = f"""# Alpha

See [the driver](run.py), [queue](queue.json), [design](design/plan.md), [log](run.log), [results](results/summary.json).

Command: `.venv/bin/python labs/{LAB}/run.py`.
"""


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class LayoutTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        git(self.root, "init", "-q")
        files = {
            ".gitignore": "labs/**/data/\nlabs/**/logs/\nlabs/**/results/\nlabs/**/buffers/\nlabs/**/*.png\n.tmp/\n",
            f"labs/{LAB}/lab.json": json.dumps({
                "id": LAB, "title": "Alpha", "stage": "complete", "summary": "S.", "current_focus": "",
                "next_action": "", "created": "2026-07-01", "updated": "2026-07-02", "report": "report.md",
                "plan": None, "readme": "README.md", "references": [], "discussion": [], "parents": [],
            }, indent=2) + "\n",
            f"labs/{LAB}/report.md": REPORT,
            f"labs/{LAB}/README.md": "[report](report.md) and [code](run.py) and [wiki](../../wiki/page.md)\n",
            f"labs/{LAB}/run.py": RUN_PY,
            f"labs/{LAB}/helpers.py": "X = 1\n",
            f"labs/{LAB}/launch.sh": LAUNCH_SH,
            f"labs/{LAB}/queue.json": "[]\n",
            f"labs/{LAB}/run.log": f"ran labs/{LAB}/run.py\n",
            f"labs/{LAB}/curve.png": "png\n",
            f"labs/{LAB}/design/plan.md": "# Design\n\n[report](../report.md)\n",
            f"labs/{LAB}/results/summary.json": "{}\n",
            f"labs/{LAB}/buffers/x.npz": "npz\n",
            f"labs/{OTHER}/lab.json": json.dumps({
                "id": OTHER, "title": "Beta", "stage": "active", "summary": "S.", "current_focus": "",
                "next_action": "Run.", "created": "2026-07-02", "updated": "2026-07-02", "references": [],
                "discussion": [], "parents": [],
            }, indent=2) + "\n",
            f"labs/{OTHER}/REPORT.md": f"Uses `labs/{LAB}/run.py`.\n",
            f"labs/{OTHER}/PLAN.md": "# Plan\n",
            "wiki/page.md": f"[alpha](../labs/{LAB}/report.md), `labs/{LAB}/run.py`, and `labs/{LAB}/run.py.bak`.\n",
            "notes/paper.md": f"See labs/{LAB}/report.md.\n",
            "extras/rows.csv": f"labs/{LAB}/run.py,1\n",
            "wiki/copied.md": COPIED,
        }
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        untracked = {f"labs/{LAB}/curve.png", f"labs/{LAB}/results/summary.json", f"labs/{LAB}/buffers/x.npz"}
        git(self.root, "add", "--", *[rel for rel in files if rel not in untracked])
        old = time.time() - 3 * 3600
        for path in self.root.rglob("*"):
            if ".git" not in path.parts:
                os.utime(path, (old, old))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def cli(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = MODULE.main(["--root", str(self.root), *args])
        return code, out.getvalue()

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")


class PlanTests(LayoutTestCase):
    def test_plan_moves_misplaced_files_out_of_lab_directories(self) -> None:
        lab = self.root / "labs" / OTHER
        for rel in ("results/sweep/curve.png", "results/sweep/summary.md", "results/ok.json"):
            (lab / rel).parent.mkdir(parents=True, exist_ok=True)
            (lab / rel).write_text("x\n", encoding="utf-8")
        tracked = {"results/sweep/curve.png", "results/sweep/summary.md", "results/ok.json", "REPORT.md", "PLAN.md"}
        moves, review = MODULE.plan_lab(lab, tracked=tracked)
        self.assertEqual(review, [])
        self.assertEqual(
            sorted((m.src, m.dst) for m in moves),
            [("results/sweep/curve.png", "figures/sweep/curve.png"),
             ("results/sweep/summary.md", "notes/sweep/summary.md")],
        )

    @_SKIP_CASE
    def test_plan_puts_every_root_entry_in_its_place(self) -> None:
        moves, review = MODULE.plan_lab(self.root / "labs" / LAB)
        self.assertEqual(review, [])
        self.assertEqual(
            {(m.src, m.dst) for m in moves},
            {
                ("report.md", "REPORT.md"), ("README.md", "notes/overview.md"), ("run.py", "scripts/run.py"),
                ("helpers.py", "scripts/helpers.py"), ("launch.sh", "scripts/launch.sh"),
                ("queue.json", "configs/queue.json"), ("run.log", "logs/run.log"), ("curve.png", "figures/curve.png"),
                ("design", "notes/design"), ("buffers", "data/buffers"),
            },
        )

    @_SKIP_CASE
    def test_rename_only_plans_the_report(self) -> None:
        moves, _ = MODULE.plan_lab(self.root / "labs" / LAB, rename_only=True)
        self.assertEqual([(m.src, m.dst) for m in moves], [("report.md", "REPORT.md")])

    def test_collisions_are_left_for_review(self) -> None:
        (self.root / "labs" / LAB / "scripts").mkdir()
        (self.root / "labs" / LAB / "scripts" / "run.py").write_text("x\n", encoding="utf-8")
        moves, review = MODULE.plan_lab(self.root / "labs" / LAB)
        self.assertNotIn("run.py", {m.src for m in moves})
        self.assertIn(f"{LAB}/run.py: scripts/run.py already exists; left in place", review)


class TidyTests(LayoutTestCase):
    def tidy(self, *extra: str) -> tuple[int, str]:
        self.cli("tidy", LAB, "--protect", OTHER, *extra)
        return self.cli("tidy", LAB, "--protect", OTHER, "--apply", *extra)

    def test_apply_needs_a_preview(self) -> None:
        code, out = self.cli("tidy", LAB, "--apply")
        self.assertEqual(code, 1)
        self.assertIn("no preview", out)
        self.assertTrue((self.root / "labs" / LAB / "run.py").exists())

    @_SKIP_CASE
    def test_tidy_moves_patches_and_rewrites(self) -> None:
        code, out = self.tidy()
        lab = f"labs/{LAB}"
        for rel in ("REPORT.md", "notes/overview.md", "scripts/run.py", "scripts/helpers.py", "scripts/launch.sh",
                    "configs/queue.json", "logs/run.log", "figures/curve.png", "notes/design/plan.md", "data/buffers/x.npz"):
            self.assertTrue((self.root / lab / rel).exists(), rel)
        self.assertIn(f"{lab}/scripts/run.py", git(self.root, "ls-files", lab))

        run = self.read(f"{lab}/scripts/run.py")
        self.assertIn("HERE = Path(__file__).resolve().parent.parent\n", run)
        self.assertIn("ROOT = Path(__file__).resolve().parents[3]\n", run)
        self.assertIn("sys.path.insert(0, str(Path(__file__).resolve().parent))\n", run)
        self.assertIn('QUEUE = HERE / "configs/queue.json"\n', run)
        self.assertIn('BUF = HERE / "data/buffers" / "x.npz"\n', run)
        self.assertIn('OUT = HERE / "results"\n', run)
        self.assertIn('VAL = Path(__file__).resolve().parents[1] / "configs/queue.json"\n', run)
        self.assertIn('SIB = Path(__file__).with_name("helpers.py")\n', run)
        self.assertIn('OTHER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")\n', run)
        self.assertIn(f"REVIEW  {lab}/scripts/run.py:16: __file__ use not adjusted", out)

        launch = self.read(f"{lab}/scripts/launch.sh")
        self.assertIn('ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"', launch)
        self.assertIn('LAB="$(cd "$(dirname "$0")/.." && pwd)"', launch)
        self.assertIn('"$LAB/scripts/run.py" > "$LAB/logs/run.log"', launch)
        self.assertIn(f"python labs/{LAB}/scripts/run.py &", launch)

        report = self.read(f"{lab}/REPORT.md")
        self.assertIn("[the driver](scripts/run.py), [queue](configs/queue.json), [design](notes/design/plan.md), "
                      "[log](logs/run.log), [results](results/summary.json)", report)
        self.assertIn(f"`.venv/bin/python labs/{LAB}/scripts/run.py`", report)
        self.assertEqual(self.read(f"{lab}/notes/overview.md"),
                         "[report](../REPORT.md) and [code](../scripts/run.py) and [wiki](../../../wiki/page.md)\n")
        self.assertEqual(self.read(f"{lab}/notes/design/plan.md"), "# Design\n\n[report](../../REPORT.md)\n")
        self.assertEqual(self.read("wiki/page.md"),
                         f"[alpha](../labs/{LAB}/REPORT.md), `labs/{LAB}/scripts/run.py`, and `labs/{LAB}/run.py.bak`.\n")

        self.assertEqual(self.read(f"{lab}/logs/run.log"), f"ran labs/{LAB}/run.py\n")
        self.assertEqual(self.read("extras/rows.csv"), f"labs/{LAB}/run.py,1\n")
        self.assertEqual(self.read("wiki/copied.md"), COPIED)
        self.assertEqual(self.read("notes/paper.md"), f"See labs/{LAB}/report.md.\n")
        self.assertEqual(self.read(f"labs/{OTHER}/REPORT.md"), f"Uses `labs/{LAB}/run.py`.\n")
        self.assertIn("LEFT    notes/paper.md", out)
        self.assertIn(f"LEFT    labs/{OTHER}/REPORT.md", out)

        record = json.loads(self.read(f"{lab}/lab.json"))
        self.assertFalse({"report", "plan", "readme"} & set(record))
        self.assertIn("!/logs/run.log", self.read(f"{lab}/.gitignore"))
        ignored = subprocess.run(["git", "-C", str(self.root), "check-ignore", "--no-index", f"{lab}/logs/run.log"],
                                 capture_output=True, text=True).stdout
        self.assertEqual(ignored, "")
        catalog = json.loads(self.read("labs/labs.json"))
        self.assertEqual([entry["id"] for entry in catalog["labs"]], [OTHER, LAB])
        self.assertEqual(code, 1)  # review items remain

    def test_code_folder_moves_whole_and_importers_follow(self) -> None:
        extra = {
            f"labs/{LAB}/sandbox/grpo/job.py": (
                "import sys\nfrom pathlib import Path\n"
                "SANDBOX = Path(__file__).resolve().parent\n"
                "LAB_DIR = SANDBOX.parents[1]\n"
                "for p in (SANDBOX, LAB_DIR):\n    sys.path.insert(0, str(p))\n"
                "import helpers\n"
                'OUT = SANDBOX / "results"\n'
                'QUEUE = LAB_DIR / "queue.json"\n'),
            f"labs/{LAB}/sandbox/grpo/run.sh": (
                '#!/bin/bash\nHERE="$(cd "$(dirname "$0")" && pwd)"\nLAB="$(cd "$HERE/../.." && pwd)"\n'),
            "extras/use_alpha.py": (
                "import sys\nfrom pathlib import Path\n"
                "ROOT = Path(__file__).resolve().parents[1]\n"
                f'ALPHA = ROOT / "labs" / "{LAB}"\n'
                "sys.path.insert(0, str(ALPHA))\n"
                "import helpers\n"
                'SPEC = ALPHA / "helpers.py"\n'),
        }
        old = time.time() - 3 * 3600
        for rel, text in extra.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            os.utime(path, (old, old))
        self.tidy()
        job = self.read(f"labs/{LAB}/scripts/sandbox/grpo/job.py")
        self.assertIn("SANDBOX = Path(__file__).resolve().parent\n", job)
        self.assertIn("LAB_DIR = SANDBOX.parents[2]\n", job)
        self.assertIn('for p in (SANDBOX, LAB_DIR / "scripts"):\n', job)
        self.assertIn('QUEUE = LAB_DIR / "configs/queue.json"\n', job)
        run = self.read(f"labs/{LAB}/scripts/sandbox/grpo/run.sh")
        self.assertIn('HERE="$(cd "$(dirname "$0")" && pwd)"\nLAB="$(cd "$HERE/../../.." && pwd)"\n', run)
        use = self.read("extras/use_alpha.py")
        self.assertIn('sys.path.insert(0, str(ALPHA / "scripts"))\n', use)
        self.assertIn('SPEC = ALPHA / "scripts/helpers.py"\n', use)
        (self.root / "extras" / "bad.py").write_text("import no_such_module_here\n", encoding="utf-8")
        imports = [line for line in self.cli("check", "--imports")[1].splitlines() if line.startswith("IMPORT")]
        self.assertEqual(imports, ["IMPORT  extras/bad.py:1: import no_such_module_here"])

    def test_changed_after_preview_is_skipped(self) -> None:
        self.cli("tidy", LAB)
        path = self.root / "labs" / LAB / "queue.json"
        path.write_text("[1]\n", encoding="utf-8")
        old = time.time() - 3 * 3600
        os.utime(path, (old, old))
        _, out = self.cli("tidy", LAB, "--apply")
        self.assertIn(f"labs/{LAB}/queue.json: changed after the preview; skipped", out)
        self.assertTrue(path.exists())
        self.assertTrue((self.root / "labs" / LAB / "scripts" / "run.py").exists())

    def test_recent_writes_refuse_the_lab(self) -> None:
        (self.root / "labs" / LAB / "run.log").write_text("still running\n", encoding="utf-8")
        code, out = self.cli("tidy", LAB)
        self.assertEqual(code, 1)
        self.assertIn(f"REFUSED labs/{LAB}: labs/{LAB}/run.log changed 0 min ago", out)
        code, out = self.cli("tidy", LAB, "--allow-recent")
        self.assertNotIn("REFUSED", out)

    def test_protected_labs_are_refused(self) -> None:
        code, out = self.cli("tidy", OTHER, "--protect", OTHER)
        self.assertIn(f"REFUSED labs/{OTHER}: protected", out)

    @_SKIP_CASE
    def test_rename_only_apply(self) -> None:
        self.cli("tidy", LAB, "--rename-only")
        self.cli("tidy", LAB, "--rename-only", "--apply")
        self.assertTrue((self.root / "labs" / LAB / "REPORT.md").exists())
        self.assertTrue((self.root / "labs" / LAB / "run.py").exists())
        self.assertEqual(self.read(f"labs/{LAB}/README.md"),
                         "[report](REPORT.md) and [code](run.py) and [wiki](../../wiki/page.md)\n")
        self.assertIn(f"labs/{LAB}/REPORT.md", self.read("wiki/page.md"))

    def test_move_promotes_a_note(self) -> None:
        self.cli("move", LAB, "design/plan.md", "PLAN.md")
        self.cli("move", LAB, "design/plan.md", "PLAN.md", "--apply")
        self.assertEqual(self.read(f"labs/{LAB}/PLAN.md"), "# Design\n\n[report](report.md)\n")
        self.assertIn("[design](PLAN.md)", self.read(f"labs/{LAB}/report.md"))
        self.assertFalse((self.root / "labs" / LAB / "design").exists())

    def test_track_adds_exceptions(self) -> None:
        code, out = self.cli("track", LAB, "results/summary.json")
        self.assertEqual(code, 0)
        text = self.read(f"labs/{LAB}/.gitignore")
        self.assertIn("!/results/\n/results/*\n!/results/summary.json\n", text)
        ignored = subprocess.run(["git", "-C", str(self.root), "check-ignore", "--no-index",
                                  f"labs/{LAB}/results/summary.json"], capture_output=True, text=True).stdout
        self.assertEqual(ignored, "")

    @_SKIP_CASE
    def test_check_reports_layout_and_references(self) -> None:
        code, out = self.cli("check", "--links")
        self.assertEqual(code, 1)
        self.assertIn(f"LAYOUT  {LAB}: report.md should be named REPORT.md", out)
        self.assertIn(f"BROKEN  wiki/page.md:1: labs/{LAB}/run.py.bak", out)
        self.tidy()
        code, out = self.cli("check", LAB)
        self.assertEqual(code, 1)
        self.assertEqual([line for line in out.splitlines() if line.startswith("LAYOUT")],
                         [f"LAYOUT  {LAB}: PLAN.md is missing"])
        (self.root / "labs" / LAB / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
        self.assertEqual(self.cli("check", LAB)[0], 0)
        broken = [line for line in self.cli("check", "--links")[1].splitlines() if line.startswith("BROKEN")]
        self.assertEqual(broken, [f"BROKEN  labs/{OTHER}/REPORT.md:1: labs/{LAB}/run.py",
                                  f"BROKEN  notes/paper.md:1: labs/{LAB}/report.md",
                                  f"BROKEN  wiki/page.md:1: labs/{LAB}/run.py.bak"])


class PythonPathTests(unittest.TestCase):
    HEAD = ('import os, sys\nfrom pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\n'
            'G = ROOT / "labs" / "2026-07-03-gamma"\n')

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for rel in ("labs/2026-07-03-gamma/scripts/common.py", "labs/2026-07-03-gamma/decoders/__init__.py"):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def rewrite(self, body: str) -> str:
        new, _, _ = MODULE.rewrite_python_paths(self.root, "extras/u.py", self.HEAD + body, MODULE.MoveMap())
        return new[len(self.HEAD):]

    def test_entries_follow_the_modules_the_file_imports(self) -> None:
        self.assertEqual(self.rewrite("if str(G) not in sys.path:\n    sys.path.insert(0, str(G))\nimport common\n"),
                         'if str(G / "scripts") not in sys.path:\n    sys.path.insert(0, str(G / "scripts"))\nimport common\n')
        self.assertEqual(self.rewrite('sys.path.append(os.path.join(str(ROOT), "labs", "2026-07-03-gamma"))\nimport common\n'),
                         'sys.path.append(os.path.join(os.path.join(str(ROOT), "labs", "2026-07-03-gamma"), "scripts"))\n'
                         'import common\n')

    def test_entries_stay_while_the_lab_root_still_serves_an_import(self) -> None:
        for body in ("sys.path.insert(0, str(G))\nimport common\nimport decoders\n",
                     "sys.path.insert(0, str(G))\nimport json\n"):
            self.assertEqual(self.rewrite(body), body)

    def test_entries_stay_when_the_module_is_reached_another_way(self) -> None:
        text = ("import sys\nfrom pathlib import Path\nHERE = Path(__file__).resolve().parent\n"
                "for _p in (HERE.parent, HERE):\n    sys.path.insert(0, str(_p))\nimport common\n")
        new, _, _ = MODULE.rewrite_python_paths(self.root, "labs/2026-07-03-gamma/scripts/t.py", text, MODULE.MoveMap())
        self.assertEqual(new, text)


class RewriteUnitTests(unittest.TestCase):
    def mmap(self) -> object:
        mmap = MODULE.MoveMap()
        mmap.add(LAB, MODULE.Move("report.md", "REPORT.md", "r"))
        mmap.add(LAB, MODULE.Move("buffers", "data/buffers", "d", True))
        return mmap

    def test_ids_respect_path_boundaries_and_sentence_ends(self) -> None:
        text = (f"labs/{LAB}/report.md. labs/{LAB}/report.md#r16 labs/{LAB}/report.md:73 "
                f"lab_{LAB}/report.md labs/{LAB}/report.mdx labs/{LAB}/buffers/a.npz labs/{LAB}/buffers_old/a")
        new, count = MODULE.rewrite_ids(text, self.mmap())
        self.assertEqual(count, 4)
        self.assertEqual(new, (f"labs/{LAB}/REPORT.md. labs/{LAB}/REPORT.md#r16 labs/{LAB}/REPORT.md:73 "
                               f"lab_{LAB}/report.md labs/{LAB}/report.mdx labs/{LAB}/data/buffers/a.npz "
                               f"labs/{LAB}/buffers_old/a"))

    def test_md_links_in_fences_are_left_alone(self) -> None:
        text = "```\n[x](report.md)\n```\n[y](report.md)\n"
        new, count = MODULE.rewrite_md_links(text, f"labs/{LAB}/notes.md", f"labs/{LAB}/notes.md", self.mmap())
        self.assertEqual((new, count), ("```\n[x](report.md)\n```\n[y](REPORT.md)\n", 1))

    def test_python_anchor_forms(self) -> None:
        text = ("A = pathlib.Path(__file__).parent / 'x'\n"
                "B = Path(__file__).parent.parent\n"
                "C = os.path.dirname(os.path.abspath(__file__))\n"
                "sys.path.insert(0, os.path.dirname(__file__))\n"
                "print(emb.__file__)\n")
        new, changes, review = MODULE.patch_python(text, 1, "scripts/a.py", "a.py", lambda p: p)
        self.assertEqual(new, ("A = pathlib.Path(__file__).parent.parent / 'x'\n"
                               "B = Path(__file__).parent.parent.parent\n"
                               "C = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
                               "sys.path.insert(0, os.path.dirname(__file__))\n"
                               "print(emb.__file__)\n"))
        self.assertEqual((changes, review), (3, []))

    def test_directory_move_keeps_paths_inside_it(self) -> None:
        text = ("SANDBOX = Path(__file__).resolve().parent\n"
                "LAB_DIR = SANDBOX.parents[1]\n"
                "UNIT = SANDBOX.parent\n"
                "ROOT = Path(__file__).resolve().parents[3]\n"
                "RES = Path(__file__).resolve().parent.parent / 'results'\n"
                "TOP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n")
        new, changes, _ = MODULE.patch_python(text, 1, "scripts/sandbox/grpo/a.py", "sandbox/grpo/a.py", lambda p: p, 2)
        self.assertEqual(new, ("SANDBOX = Path(__file__).resolve().parent\n"
                               "LAB_DIR = SANDBOX.parents[2]\n"
                               "UNIT = SANDBOX.parent\n"
                               "ROOT = Path(__file__).resolve().parents[4]\n"
                               "RES = Path(__file__).resolve().parent.parent / 'results'\n"
                               "TOP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname("
                               "os.path.abspath(__file__)))))\n"))
        self.assertEqual(changes, 3)

    def test_navigation_from_a_file_variable_follows_a_file_move(self) -> None:
        text = "HERE = Path(__file__).resolve()\nLAB = HERE.parent\nUP = os.path.dirname(HERE)\n"
        new, _, _ = MODULE.patch_python(text, 1, "scripts/a.py", "a.py", lambda p: p)
        self.assertEqual(new, "HERE = Path(__file__).resolve()\nLAB = HERE.parent.parent\n"
                              "UP = os.path.dirname(os.path.dirname(HERE))\n")

    def test_shell_directory_move(self) -> None:
        text = ('HERE="$(cd "$(dirname "$0")" && pwd)"\n'
                'LAB="$(cd "$HERE/../.." && pwd)"\n'
                'cd "$(dirname "$0")/.."\n'
                'TOP="$(cd "$(dirname "$0")/../.." && pwd)"\n')
        new, changes, review = MODULE.patch_shell(text, 1, "scripts/sandbox/grpo/a.sh", 2)
        self.assertEqual(new, ('HERE="$(cd "$(dirname "$0")" && pwd)"\n'
                               'LAB="$(cd "$HERE/../../.." && pwd)"\n'
                               'cd "$(dirname "$0")/.."\n'
                               'TOP="$(cd "$(dirname "$0")/../../.." && pwd)"\n'))
        self.assertEqual((changes, review), (2, []))

    def test_shell_names_after_cd_to_the_lab_root(self) -> None:
        mmap = self.mmap()
        mmap.add(LAB, MODULE.Move("run.py", "scripts/run.py", "c"))
        text = ('cd "$(dirname "$0")/.."\n"$PY" -u run.py --out=report.md buffers design > report.md.log\n'
                'pgrep -f "run.py" || true\ncd /tmp && python run.py\n')
        new, count = MODULE.rewrite_shell_literals(text, "scripts/a.sh", LAB, lambda p: mmap.map_lab(LAB, p))
        self.assertEqual(new, ('cd "$(dirname "$0")/.."\n"$PY" -u scripts/run.py --out=REPORT.md buffers design '
                               '> report.md.log\npgrep -f "run.py" || true\ncd /tmp && python run.py\n'))
        self.assertEqual(count, 2)

    def test_shell_literals_keep_sentence_ends(self) -> None:
        text = 'LAB="$(cd "$(dirname "$0")/.." && pwd)"\necho "Read ${LAB}/report.md. Then $LAB/report.md"\n'
        new, count = MODULE.rewrite_shell_literals(text, "scripts/a.sh", LAB,
                                                   lambda p: self.mmap().map_lab(LAB, p))
        self.assertEqual(count, 2)
        self.assertIn('echo "Read ${LAB}/REPORT.md. Then $LAB/REPORT.md"', new)


if __name__ == "__main__":
    unittest.main()
