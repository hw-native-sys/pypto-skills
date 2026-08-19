---
name: setup-and-run
description: Use when a first-time user needs to go from a fresh checkout to a validated PyPTO run, when someone asks how to get started or how to run a model, or when a newly prepared environment runs nothing successfully yet.
---

# Set Up and Run

Drive this as a guided runbook, not as a document to hand over. Run one stage
at a time, show the user the exact command, and check that stage's gate before
moving on. A later stage started on a broken earlier stage produces misleading
errors: most "the model does not run" reports are an unverified environment or
an unverified smoke test.

This skill owns the sequence, the gates, and the escalation discipline. The
consumer repository owns the command text. Read that repository's guides
before running anything, and never restate its install commands from memory,
from an old log, or from a pinned version you remember.

## Bound system-test execution

Never run the full system-test suite locally. Run only system-test cases
directly relevant to the changed or requested scope; use CI for the full
system-test suite. If CI cannot run it, report that limitation instead of
substituting a local full-suite run. This applies to the ladder below: a rung
is chosen because it is the next step for this user, never because it is one
more case that could be run.

## Stage 0: Establish the target

Ask before running anything, because the answers change every later stage.

1. **Simulator or real device?** A simulator run needs no vendor toolkit and
   no accelerator. A device run needs the vendor toolkit, its device query
   tool, and a device the user is actually allocated. Execution target is
   selected by the entry point's platform argument, never by the host CPU
   architecture.
2. **Which model, and how many cards?** Single-card and multi-rank entry
   points take different device arguments — one integer versus a
   comma-separated set plus an explicit world size.
3. **Is there an existing environment?** Reuse a working checkout and Python
   environment when one exists. Never overwrite or delete one.

On a shared host, ask how devices are allocated there. Do not pick an
apparently idle device by probing and racing another user.

## Stage 1: Source and environment

Locate the repository's setup guide before installing anything. Look in this
order and stop at the first hit:

```bash
ls docs/get-started/installation.md 2>/dev/null
ls docs/**/install*.md docs/**/setup*.md 2>/dev/null
grep -rn -i 'install' README.md CONTRIBUTING.md 2>/dev/null | head
```

Then follow that guide, and prefer the repository's own environment skill when
it publishes one. Two rules survive every version of these guides:

- One selected framework checkout is the version source of truth. Its pins
  determine the runtime, assembler, and tile-ISA revisions. Do not mix a pin
  from one checkout with a binary from another.
- On a device target, source the vendor environment **before** installing the
  runtime. A runtime installed without it does not build the onboard binaries,
  and sourcing afterwards does not add them.

Gate — every one of these must succeed in the shell that will run the case:

```bash
python -c "import <framework>, torch"          # framework and torch import
python -c "from golden import run, run_jit"    # harness imports from the repo root
<assembler> --version                          # the assembler actually runs
```

Then compare what is installed against what the selected checkout pins. This
comparison is the gate, not the liveness checks above:

```bash
<assembler> --version                                   # installed assembler
sed -n 's/^PTOAS_VERSION=//p' "$FRAMEWORK/toolchain/versions.env"   # pinned
cat "$FRAMEWORK/runtime/pto_isa.pin"                    # pinned tile-ISA commit
git -C "$TILE_ISA" rev-parse HEAD                       # installed tile-ISA
```

A binary that answers `--version` is necessary and not sufficient: an
assembler one release away from the pin runs, reports a version, compiles some
kernels, and fails others with tile-op contract errors that read like kernel
bugs. Resolve a version difference here, before Stage 3 attributes it to a
model.

Locating the tile-ISA checkout the build actually uses takes a search when no
root is exported — a build tree usually vendors its own copy, and a machine
often has more than one. Reconcile every copy you find against the pin rather
than the first one.

For a device target, additionally: the vendor environment is sourced in this
shell, and the device query tool lists the allocated device.

Report a mismatch with both values named and stop. If the user decides to
proceed on a skewed toolchain anyway, say which Stage 3 failures that choice
is expected to produce rather than silently continuing.

## Stage 2: Smoke the whole chain

Run the repository's smallest end-to-end example — one that compiles, generates
inputs, computes a torch reference, executes, and validates. In pypto-lib that
is `examples/beginner/hello_world.py`.

Run the simulator form first even when the goal is a device run: it separates
compiler and assembler problems from device and driver problems.

```bash
PYTHONPATH="$PWD" python <smallest example> -p <sim platform>
PYTHONPATH="$PWD" python <smallest example> -p <device platform> -d <allocated id>
```

Gate: the harness prints its compile, input, golden, runtime, and validation
stages, ends in a passing result, and the process exits 0.

Exit 0 alone is not the gate. Some entry points take a compile-only path on a
simulator and print lowering output with no run or validation stages at all;
that is a successful compile, not a validated run, and it must be reported as
such. Read the stages, not the exit code.

Everything that fails here is an environment fault, not a model fault. Fix it
in Stage 1 rather than moving on.

## Stage 3: Climb the model ladder

Never start a new user on a full forward. Climb in order — operator, then one
layer, then the multi-layer forward. Each rung is cheaper to run and far
easier to diagnose than the next, and a failure means much more when the rung
below it passed.

The ladder buys diagnosis, so spend it where diagnosis is worth buying. On an
environment that has just been built, or one whose pins needed reconciling,
climb from the bottom. On an environment that has already been proven, start
at the rung the user actually asked for and fall back down the ladder only if
it fails. Do not make someone run operators they did not ask about to earn a
case that would have run.

Inspect every entry point before running it, because the argument shape is
per-script and entry-point names drift:

```bash
PYTHONPATH="$PWD" python <entry>.py --help
grep -n '^#\s*ci:' <entry>.py
```

Where the repository marks entry points with `# ci:` comments, read them as
hard constraints: a `no-sim` marker means the case is device-only, and a
`devices=N` marker means it needs N allocated cards.

Prefer a rung that runs on the simulator whenever one exists at that level.
It removes device allocation from the failure surface. Confirm what the rung
actually did: a simulator platform can select a compile-only path, so a rung
that lowers without running has not validated anything and does not license
the next rung.

One class of failure here is never a model fault. A compile error about a tile
op needing an explicit temporary, or about a memory-planning pass being
skipped, is the Stage 1 version comparison coming due: the assembler and the
framework disagree. Kernels that avoid those ops keep passing, which makes the
skew look like a per-kernel bug. Go back to Stage 1 and reconcile the pins —
do not work around it by trying a different rung.

### Worked example: pypto-lib

Verify each command with `--help` before running it; treat this table as the
shape of the ladder, not as a fixed inventory.

| Rung | Command | Notes |
|---|---|---|
| Operator | `python models/qwen3_14b/topk_select.py -p a2a3sim` | Single card, simulator-capable |
| Single layer | `python models/qwen3_14b/decode_layer_a8w8.py -p a2a3sim` | One quantized decode layer. On a simulator this lowers only and reports no run stages; `-p a2a3 -d 0` is the rung that validates |
| Single layer, BF16 | `python models/qwen3_14b/decode_fwd.py -p a2a3 -d 0` | The default CLI is the single-layer golden; device-only |
| Multi-layer decode | `python models/qwen3_14b/decode_fwd.py -p a2a3 -d 0 --validate-fwd --fwd-layers 4` | Stacked layers plus the on-device LM head, against a host reference |
| Multi-layer prefill | `python models/qwen3_14b/prefill_fwd.py -p a2a3 -d 0 --num-layers 2` | Device-only; start at 2 layers |

One decode entry point often serves both the single-layer and the multi-layer
case, switched by a flag. In this tree `decode_fwd.py` without `--validate-fwd`
is the single-layer case and `--fwd-layers` is ignored — read the flag help
before concluding that a layer count had no effect.

Multi-rank trees follow the same ladder with a device set instead of a device:

| Rung | Command | Notes |
|---|---|---|
| Operator | `python models/deepseek_v4_flash_mtp/rmsnorm.py -p a2a3sim` | Single card, simulator-capable |
| Attention path | `python models/deepseek_v4_flash_mtp/decode_csa.py -p a2a3sim` | Single card, simulator-capable |
| Single layer | `python models/deepseek_v4_flash_mtp/decode_layer.py -p a2a3 --ep 2 -d 0,1` | Two allocated cards; `-d` is a comma-separated set |
| Multi-layer forward | `python models/deepseek_v4_flash_mtp/decode_fwd.py -p a2a3 --ep 2 -d 0,1` | Device-only and substantially heavier |

### Cost discipline

Full-forward cases allocate large fixtures and can exhaust host memory or the
device cache pool. Keep batch, sequence length, layer count, and world size at
their defaults on a first run, then raise one of them at a time. Read the
script's `--help` before raising any of them.

## Stage 4: Read the result and hand off

A passing run exits 0. A validation mismatch is a real numerical failure, not
a harness error, and belongs in the repository's precision guidance rather
than in this runbook.

Find the pass signal each rung actually emits before declaring one. Rungs
driven by the harness end in its own passing line, but a rung that checks
itself against a host reference reports through a case-specific summary —
match counts, an error percentage, a maximum absolute error — and never prints
the harness line at all. Quote the line the rung printed rather than asserting
a result its output does not contain.

Do not stop at the first green run. Point the user at the repository's harness
and validation guide, its saved-golden replay workflow so later iterations
skip the torch reference, and its kernel coding style before they edit
anything.

## First-run failure table

| Symptom | Cause and fix |
|---|---|
| The harness package cannot be imported | Not running from the repository root, or the root is not on `PYTHONPATH` |
| The framework cannot be imported | Wrong Python environment active, or it was not installed from the selected checkout |
| Compile fails with little or no stderr | The assembler binary is not usable. It must be a regular executable that answers `--version`; a partial extract or copy satisfies an existence check and then fails real compiles |
| Compile fails on tile-op contracts — an op "requires explicit tmp", a memory-planning pass is skipped — while other kernels still compile | The assembler and the framework are at different revisions. Compare the installed version against the checkout's pin; the per-kernel pattern is which ops each kernel happens to use, not a kernel bug |
| A simulator run exits 0 but prints no run or validation stages | That entry point takes a compile-only path on a simulator. It proves the kernel lowers; it validates nothing. Use a device platform, or a rung that runs on the simulator, before reporting a validated result |
| Simulator compile cannot find its compiler | Simulator builds need the exact compiler generation the setup guide names, not merely "a C++ compiler" |
| Tile-ISA headers missing, or a version mismatch at runtime init | The compile-side and runtime-side tile-ISA checkouts have drifted. Point the environment at one checkout and confirm its `HEAD` equals the pin |
| Import or signature errors from the runtime package on an otherwise working install | The framework and its runtime are at different revisions, or a stale prebuilt extension shadows the fresh one. Reinstall the runtime from the selected checkout. Common on shared machines where the framework is rebuilt in place |
| A device run cannot find or initialize the onboard runtime | The vendor environment was not sourced before the runtime was installed. Source it and reinstall |
| A run compiles, reaches the runtime stage, and then hangs or reports a runtime or driver error code | Re-check the Stage 1 pin comparison first. A skewed assembler also produces generic on-device exceptions, not only compile errors, and the same case passes once the pin is honored. Only after the pins agree is this past this runbook's scope; then move to the repository's debugging guide. It happens on simulators too, not only on devices |

## Safety and scope

- Use only devices the user is allocated. On a shared host use the site's
  allocator; do not probe for an idle device.
- Do not use `sudo`, modify the vendor toolkit, or install into system
  directories.
- Never overwrite or delete an existing framework, tile-ISA, or assembler
  checkout. Inspect and reuse it, or place a new one in a scoped sibling
  directory.
- The consumer repository's documentation is the technical source of truth.
  Where it disagrees with this runbook, follow the repository and report the
  discrepancy.

## Reporting

Report the stage reached, the exact commands run, the platform and device set
used, and the resolved framework, runtime, assembler, and tile-ISA versions.
When a stage fails, report the failing stage and its gate rather than only the
final traceback — a model-stage traceback usually describes an environment
fault.
