# Dogfooding walkthrough — the Policy Studio, all eight screens

**For a person, on a machine that has never run this.** Twenty minutes, ending with a
receipt you verify yourself using a command that does not trust the Studio.

> **Every command below is either run or checked by
> `tests/studio/test_dogfooding.py` before anyone types it**, and each one says which.
> The test reads *this file* and extracts the commands, so a command that stops working
> fails the build rather than wasting your afternoon.
>
> **`[run]`** — executed to completion exactly as written, exit code asserted.
> **`[checked]`** — not executed, with the reason, and with whatever the command *claims*
> checked instead. Four of the seven are `[checked]`; none is unexamined.
>
> The distinction is the point. Saying "every command is tested" when three of them are
> validated rather than run would spend trust this walkthrough has not earned.

---

## 0. What you will end up with

A Studio running on loopback, a policy set you ratified yourself, a decision the engine
made under it, and a receipt you check with a command that reads two files and opens no
database. If the last step prints `verified`, you have done the whole loop the product
exists for.

---

## 1. Install

```shell
python -m venv .venv
```

```shell
.venv/bin/pip install -e ".[studio]"
```

**`[checked]`** — both. A test that created a virtualenv and installed from the network
would be testing pip, and would need the network CI does not give it. Checked instead:
`studio` is a declared extra in `pyproject.toml`, and every distribution it names
imports.

On Windows the second path is `.venv\Scripts\pip`. The rest of this walkthrough uses
`python` to mean *that* interpreter.

## 2. Check the Studio is there

```shell
python -m onedoor.studio --help
```

**`[run]`.** You should see `--db`, `--studio-db`, `--host` and `--port`. **`--host` accepts loopback
and nothing else** — there is no flag to turn that off, because a flag that turns it off
is the drift it exists to catch.

## 3. Start it

```shell
python -m onedoor.studio --db onedoor.db --studio-db studio.db --port 8787
```

**`[checked]`** — it serves until you stop it, so a test cannot run it to completion.
Checked instead: this exact argument list goes through the real parser, and an unknown
flag is refused rather than ignored. That the server serves is covered separately, over a
real socket.

Then open **http://127.0.0.1:8787**.

**Name `--db` explicitly, exactly as above.** The decision service defaults to
`onedoor-service.db` and the Studio's `--db` defaults to `onedoor.db`; accept both
defaults and they point at *different stores*, so the Studio comes up, works, and shows
you an empty world. If the store it opened has never held a policy, the Studio says so on
its face — that is F-H, and this is the trap it was fixed for.

## 4. Walk the screens

In this order. Each is a tab.

| # | Screen | What to look for |
|---|---|---|
| 1 | **Drafts** (`/`, which redirects to `/drafts`) | The empty state offers a form *and* a `curl` line — an affordance discoverable only by the lost is no affordance. On a fresh store you should also see the F-H warning naming both database defaults. |
| 2 | **Policies** | Empty at first, and it says *nothing is permitted* rather than showing a blank. Read the sentence about absence being denial; it is the most load-bearing fact about the engine. |
| 3 | **History** | No decisions yet. Note that filtering by API key is **not offered**, and the page says why: the ledger does not record one. |
| 4 | **Live state** | The kill switch is shown and **cannot be thrown from here**, with the reason. Read what it says the switch does *not* stop. |
| 5 | **Verify** | No receipts yet. You will come back. |

## 5. Make a draft and put a rule in it

From the Drafts screen, type a title and press the button. Or, from a terminal:

```shell
curl -X POST 'http://127.0.0.1:8787/drafts' --data-urlencode 'title=first policy set'
```

**`[checked]`** — CI need not have `curl`. Checked instead: the path this line posts to
is one the app actually routes for POST, and the field name is the one the form uses. That
is the class of error that stranded this very line when Drafts moved to `/drafts`.

Open the draft, then open a rule in the **editor**. Change a cap. Save from the guided
pane, then look at the raw pane — **it shows the same value**, because both are rendered
from one parsed object. Try saving nonsense in the raw pane: it refuses, says the draft is
unchanged, and writes nothing.

Note the ND-054 note at the decimal fields. It describes what the engine does **today**.

## 6. Ratify it

From the draft, choose **Review and ratify**. The ceremony page is a page before it is an
action: it shows what will be in force, what changes, and what ratifying does not undo.
Read that last sentence — it does not say the change cannot be undone, because that would
be false. Give a session note and confirm.

You now have a receipt.

## 7. Make a decision happen

Run something through the engine so History has a row. The smallest honest way is a
decision through the library:

```shell
python -m onedoor.studio.walkthrough --db onedoor.db
```

**`[run]`.** Then reload **History**. Your decision is there, numbered by the chain. Open it and use
**re-evaluate under version** — pick another version and see whether the answer would have
been different. Note both versions named in the same breath, and the sentence saying this
is what *would have* happened, not what will.

## 8. Verify the receipt yourself

Go to **Verify**, open your receipt, and follow the page. Save the two files it shows as
`receipt.json` and `snapshot.json`, then:

```shell
python -m onedoor.studio.verify receipt.json snapshot.json
```

**`[run]`** — all three of its outcomes are, against files this test produced itself.

`verified` and exit `0` means the receipt matches its own digest and the snapshot hashes
to the version that receipt ratified. `failed` and exit `1` means one of those did not
hold. `unreadable` and exit `2` means a file could not be read — **that is not a failed
check; it is a check that never ran.**

That command reads two files and opens no database. Copy them to another machine and it
gives the same answer, which is the entire point: **the Studio showed you a verification
and told you how to repeat it without trusting the Studio.**

---

## What to write down

Anything that surprised you, in your words, including things that merely felt wrong. The
three findings that shaped this Studio most — F-A, F-G, F-H — all came from someone using
it and saying what happened, not from a test.
