"""
Tests of run_all.py and of the hardware path of parse_log.py that need no board.

    python -m unittest discover -s tests -v

Needs: the hardware images (python scripts/run_all.py hw-build), the QEMU cell armv8m-c-clang-O3 and its
log in a run folder (python scripts/run_all.py qemu), and build/host/fuzz_digest.json.

SYNTHETIC LOGS. A Pico 2 log is needed to test the hardware log path before the board exists. The tests
make one in a temporary folder from a QEMU log of the twin cell (same backend code): BUILD lines taken from
the hardware cell's manifest, RUN/TIMER lines in the hardware format. Its numbers are QEMU ticks, NOT
cycles. It is never written under results/ and must never be used as data.
"""

import contextlib
import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import run_all  # noqa: E402

PY = sys.executable
HW_CELL = "rp2350_arm-c-clang-O3"
QEMU_CELL = "armv8m-c-clang-O3"
HOST_DIGEST = REPO / "build" / "host" / "fuzz_digest.json"


def qemu_log():
    logs = sorted((REPO / "results" / "runs").glob(f"*/raw/{QEMU_CELL}.r1.log"))
    if not logs:
        raise unittest.SkipTest("no QEMU log of armv8m-c-clang-O3 under results/runs/*/raw")
    return logs[-1].read_text()


def synthetic_image_output():
    """What the hardware image would print (format only; the numbers are QEMU ticks)."""
    man = json.loads((REPO / "build" / "cells" / HW_CELL / "manifest.json").read_text())
    out = ["", "RUN,clock_hz,12000000", "RUN,clock_source,xosc (clk_sys = clk_ref = XOSC, no PLL)",
           "HWINFO,dwt_ctrl_at_start,0x40000000,nocyccnt_bit,0,cyccnt_counts,1"]
    for line in qemu_log().splitlines():
        tag = line.split(",", 1)[0]
        if tag == "RUN":
            continue
        if line.startswith("BUILD,") and line.split(",")[1] in man["build_info"]:
            k = line.split(",")[1]
            line = f"BUILD,{k},{man['build_info'][k]}"
        elif line.startswith("BUILD,platform,"):
            line = "BUILD,platform,rp2350.armv8m.main"
        elif tag == "TIMER":
            line = "TIMER,DWT_CYCCNT,cpu_cycles,ffffffff"
        out.append(line)
    return "\n".join(out + ["EXIT,0"]) + "\n"


def hardware_log(run_id_lines=()):
    man = json.loads((REPO / "build" / "cells" / HW_CELL / "manifest.json").read_text())
    head = ["RUN,env,hardware", f"RUN,cell,{HW_CELL}", "RUN,repeat,1", "RUN,board,Raspberry Pi Pico 2 (RP2350)",
            "RUN,arch,arm", f"RUN,elf_sha256,{man['elf_sha256']}", *run_id_lines]
    return "\n".join(head) + "\n" + synthetic_image_output()


def parse(dirpath, matrix="build/matrix_hw.json"):
    out = Path(dirpath) / "out"
    r = subprocess.run([PY, "scripts/parse_log.py", "--input", str(dirpath), "--out-dir", str(out),
                        "--matrix", matrix, "--host-digest", str(HOST_DIGEST)],
                       cwd=REPO, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr, out


@unittest.skipUnless((REPO / "build" / "matrix_hw.json").exists() and HOST_DIGEST.exists(),
                     "run `run_all.py hw-build` (and the host step) first")
class HardwareLogValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, text):
        (self.tmp / name).write_text(text, newline="\n")

    def test_well_formed_hardware_log_is_accepted_as_cpu_cycles(self):
        self.write(f"{HW_CELL}.r1.log", hardware_log())
        code, out, csvdir = parse(self.tmp)
        self.assertEqual(code, 0, out)
        rows = list(csv.DictReader(open(csvdir / "benchmark.csv")))
        self.assertEqual({r["metric_kind"] for r in rows}, {"cpu_cycles"})
        self.assertEqual({r["env"] for r in rows}, {"hardware"})
        self.assertEqual({r["clock_hz"] for r in rows}, {"12000000"})

    def test_rejections(self):
        base = hardware_log()
        cases = {
            "no clock": (base.replace("RUN,clock_hz,12000000\n", ""), "RUN,clock_hz missing"),
            "no board": (base.replace("RUN,board,Raspberry Pi Pico 2 (RP2350)\n", ""), "RUN,board missing"),
            "bad arch": (base.replace("RUN,arch,arm", "RUN,arch,x86"), "RUN,arch"),
            "systick ticks": (base.replace("TIMER,DWT_CYCCNT,cpu_cycles", "TIMER,SYSTICK,systick_ticks"),
                              "expected one of"),
            "stale elf": (base.replace("RUN,elf_sha256,", "RUN,elf_sha256,00"), "SHA-256 differs"),
            "qemu label on hw target": (base.replace("RUN,env,hardware", "RUN,env,qemu\nRUN,exit_status,0"),
                                        "env=qemu log for hardware target"),
            "no LWC_END": (base.replace("LWC_END,ok", "LWC_END,fail"), "LWC_END"),
        }
        for name, (text, reason) in cases.items():
            with self.subTest(name):
                d = self.tmp / name.replace(" ", "_")
                d.mkdir()
                (d / f"{HW_CELL}.r1.log").write_text(text, newline="\n")
                code, out, _ = parse(d)
                self.assertNotEqual(code, 0, out)
                self.assertIn(reason, out)

    def test_qemu_log_claiming_cpu_cycles_is_rejected(self):
        text = qemu_log().replace("TIMER,SYSTICK,systick_ticks", "TIMER,SYSTICK,cpu_cycles")
        self.write(f"{QEMU_CELL}.r1.log", text)
        code, out, _ = parse(self.tmp, "build/matrix.json")
        self.assertNotEqual(code, 0)
        self.assertIn("QEMU counts instructions", out)

    def test_mixed_envs_are_refused(self):
        self.write(f"{HW_CELL}.r1.log", hardware_log())
        self.write(f"{QEMU_CELL}.r1.log", qemu_log())
        code, out, _ = parse(self.tmp)
        self.assertEqual(code, 2)
        self.assertIn("more than one env", out)


class FakeSerial:
    """Replays the synthetic image output, then times out (b'')."""

    def __init__(self, text):
        self.data, self.closed = text.encode("ascii"), False

    def read(self, n):
        chunk, self.data = self.data[:n], self.data[n:]
        return chunk

    def reset_input_buffer(self):
        pass

    def close(self):
        self.closed = True


def run_main(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            run_all.main(argv)
            code = 0
        except SystemExit as e:   # sys.exit("msg") prints msg only when the process ends: keep it here
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            if isinstance(e.code, str):
                out.write(e.code + "\n")
    return code, out.getvalue()


class RunAllArguments(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._runs = run_all.RUNS
        run_all.RUNS = self.tmp

    def tearDown(self):
        run_all.RUNS = self._runs
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_hw_run_refuses_without_confirm_flag(self):
        code, out = run_main(["hw-run", "--port", "COM99", "--run-id", "t-refuse"])
        self.assertEqual(code, 2)
        self.assertIn("REFUSED", out)
        self.assertFalse((self.tmp / "t-refuse").exists())

    def test_hw_run_requires_port(self):
        code, _ = run_main(["hw-run", "--confirm-hardware"])
        self.assertEqual(code, 2)          # argparse error

    @unittest.skipUnless((REPO / "build" / "matrix_hw.json").exists(), "needs hw-build")
    def test_hw_run_stops_if_port_cannot_be_opened(self):
        code, out = run_main(["hw-run", "--port", "NO_SUCH_PORT_42", "--confirm-hardware", "--run-id", "t-port"])
        self.assertNotEqual(code, 0)
        self.assertTrue("cannot open serial port" in out or "pyserial is not installed" in out, out)
        self.assertFalse((self.tmp / "t-port").exists())

    def test_existing_run_folder_is_never_reused(self):
        (self.tmp / "t-exists").mkdir()
        (self.tmp / "t-exists" / "keep.txt").write_text("x")
        for mode in (["qemu"], ["hw-build"]):
            code, out = run_main([*mode, "--run-id", "t-exists"])
            self.assertNotEqual(code, 0)
            self.assertIn("never reuses", out)
        self.assertEqual([p.name for p in (self.tmp / "t-exists").iterdir()], ["keep.txt"])

    def test_default_mode_is_qemu(self):
        (self.tmp / "t-default").mkdir()
        code, out = run_main(["--run-id", "t-default"])   # no mode given -> qemu, refused before running anything
        self.assertNotEqual(code, 0)
        self.assertIn("never reuses", out)

    @unittest.skipUnless((REPO / "build" / "matrix_hw.json").exists() and HOST_DIGEST.exists(), "needs hw-build")
    def test_hw_run_end_to_end_with_fake_board(self):
        text = synthetic_image_output()
        port = FakeSerial("")
        loads = []

        def fake_load(args, cell_dir):
            loads.append(cell_dir.name)
            port.data = text.encode("ascii")   # the "board" prints the image output after each load
            return "fake loader (test)"
        orig = run_all.open_port, run_all.load_image
        try:
            run_all.open_port = lambda p, b, t: port
            run_all.load_image = fake_load
            code, out = run_main(["hw-run", "--port", "FAKE", "--confirm-hardware", "--no-prompt", "--cells", HW_CELL,
                                  "--repeats", "2", "--timeout", "5", "--run-id", "t-e2e"])
        finally:
            run_all.open_port, run_all.load_image = orig
        self.assertEqual(code, 0, out)
        self.assertEqual(loads, [HW_CELL, HW_CELL])
        run = self.tmp / "t-e2e"
        log1 = (run / "raw" / f"{HW_CELL}.r1.log").read_text()
        for line in ("RUN,env,hardware", "RUN,board,Raspberry Pi Pico 2 (RP2350)", "RUN,arch,arm",
                     "RUN,capture_status,exit", "RUN,clock_hz,12000000"):
            self.assertIn(line, log1)
        rows = list(csv.DictReader(open(run / "metrics_summary.csv")))
        self.assertEqual(len(rows), 14)
        self.assertEqual(list(rows[0]), run_all.SUMMARY_COLS)
        self.assertEqual({r["metric_kind"] for r in rows}, {"cpu_cycles"})
        self.assertTrue(all(r["flash_bytes"] != "" and r["stack_bytes"] != "" for r in rows))
        self.assertIn("env=hardware", (run / "REPORT.md").read_text())


if __name__ == "__main__":
    unittest.main()
