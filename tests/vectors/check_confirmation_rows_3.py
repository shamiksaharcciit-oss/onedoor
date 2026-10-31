"""A reference implementation of draft 3's verifier rows (section 7), run over
confirmation_vectors_3.json. It imports nothing from onedoor or onetrace: only the
standard library and `cryptography` for Ed25519. Exit 0 when every vector's five rows
equal its stated `expect`, verdict and detail both.

Usage: python check_confirmation_rows_3.py confirmation_vectors_3.json
"""

import base64
import json
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

TYP = "aadp-confirmation+jwt"
OUTCOMES = {"effected", "refused", "effect-unknown"}
DEPENDENCIES = {"consume-store", "presenter-key-directory", "status"}
KNOWN = {
    "iss",
    "permit",
    "request",
    "action_digest",
    "mandate_verdict",
    "outcome",
    "step",
    "reason",
    "dependency",
    "recipient_action_id",
    "iat",
}
KNOWN_NESTED = {
    "permit": {"iss", "jti", "digest"},
    "request": {"content_digest", "signature_base_digest"},
}


class Malformed(Exception):
    pass


def b64u_dec(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def no_dups(pairs):
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise Malformed(f"duplicate member '{k}'")
        seen[k] = v
    return seen


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def read(token):
    """Section 2.4: unreadable unless a compact JWS whose header and payload are JSON objects without duplicates."""
    parts = token.split(".")
    if len(parts) != 3:
        raise Malformed("not a compact JWS")
    try:
        header = json.loads(b64u_dec(parts[0]), object_pairs_hook=no_dups)
        payload = json.loads(b64u_dec(parts[1]), object_pairs_hook=no_dups)
        sig = b64u_dec(parts[2])
    except Malformed:
        raise
    except Exception:
        raise Malformed("not a compact JWS")
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise Malformed("header or payload is not a JSON object")
    return header, payload, f"{parts[0]}.{parts[1]}".encode("ascii"), sig


def shape_problem(p):
    """Section 2's presence rules. Returns a problem string, or None."""
    if not isinstance(p.get("iss"), str):
        return "iss missing or not a string"
    if not is_int(p.get("iat")):
        return "iat missing or not an integer"
    o = p.get("outcome")
    if o not in OUTCOMES:
        return "outcome missing or unknown"
    if o == "effected" and "recipient_action_id" not in p:
        return "effected without recipient_action_id"
    if o != "effected" and "recipient_action_id" in p:
        return f"recipient_action_id on a '{o}' confirmation"
    if o != "refused" and any(k in p for k in ("step", "reason", "dependency")):
        return f"step, reason or dependency on a '{o}' confirmation"
    if o == "refused":
        by_check = "step" in p or "reason" in p
        if by_check and "dependency" in p:
            return "both a check refusal and a dependency"
        if by_check:
            if not (is_int(p.get("step")) and 1 <= p["step"] <= 13):
                return "step missing or outside 1 to 13"
            if not isinstance(p.get("reason"), str):
                return "reason missing"
        elif p.get("dependency") not in DEPENDENCIES:
            return "a refusal with neither step and reason nor a known dependency"
    for k in ("permit", "request"):
        if k in p:
            if not isinstance(p[k], dict):
                return f"{k} is not an object"
            for m in KNOWN_NESTED[k]:
                if m in p[k] and not isinstance(p[k][m], str):
                    return f"{k}.{m} missing"
    if o == "refused" and "step" in p:
        s = p["step"]
        need = {
            "permit": s > 1,
            "request.content_digest": s > 7,
            "request.signature_base_digest": s > 8,
            "action_digest": s > 9,
        }
    elif o in ("effected", "effect-unknown"):
        need = dict.fromkeys(
            ("permit", "request.content_digest", "request.signature_base_digest", "action_digest"),
            True,
        )
    else:
        need = None  # a dependency refusal: nothing required
    if need is not None:
        have = {
            "permit": "permit" in p,
            "request.content_digest": "content_digest" in p.get("request", {}),
            "request.signature_base_digest": "signature_base_digest" in p.get("request", {}),
            "action_digest": "action_digest" in p,
        }
        for k, required in need.items():
            if required and not have[k]:
                return f"{k} missing"
            if not required and have[k]:
                return f"{k} present before its step passed"
    return None


def unknown_members(p):
    names = sorted(k for k in p if k not in KNOWN)
    for k, allowed in KNOWN_NESTED.items():
        if isinstance(p.get(k), dict):
            names += sorted(f"{k}.{m}" for m in p[k] if m not in allowed)
    return names


def combine(results, pass_detail):
    """FAIL over NOT-RUN over PASS; details joined by '; '."""
    fails = [d for v, d in results if v == "FAIL"]
    if fails:
        return ["FAIL", "; ".join(fails)]
    nrs = [d for v, d in results if v == "NOT-RUN"]
    if nrs:
        return ["NOT-RUN", "; ".join(nrs)]
    return ["PASS", pass_detail]


def its(n):
    return "its" if n == 1 else "their"


def rows(doc, vec):
    st, win = doc["step"], doc["window_seconds"]
    trust = vec["trust"] if "trust" in vec else doc["trust"]
    keys = {k["kid"]: bytes.fromhex(k["public_hex"]) for k in doc["keys"].values()}
    steps = vec["steps"]
    readable, unreadable = [], {}
    for s in steps:
        if s["confirmation"] is None:
            continue
        try:
            readable.append((s,) + read(s["confirmation"]))
        except Malformed as e:
            unreadable[s["name"]] = str(e)
    any_conf = any(s["confirmation"] is not None for s in steps)
    empty = "no confirmation recorded" if not any_conf else "no readable confirmation"
    n = len(readable)

    # 3. Recipient key, first: rows 1 and 2 read its per-step result.
    key_of = {}
    if not any_conf:
        key = ["NOT-RUN", "no confirmation recorded"]
    else:
        res, unknown, no_list_said = [], [], False
        for name, problem in unreadable.items():
            res.append(("FAIL", f"{name}: malformed confirmation ({problem})"))
            key_of[name] = "FAIL"
        for s, h, p, si, sig in readable:
            nm = s["name"]

            def put(v, d):
                res.append((v, d))
                key_of[nm] = v

            if h.get("typ") != TYP:
                put("FAIL", f"{nm}: not a recipient confirmation (typ {h.get('typ')!r})")
                continue
            if "crit" in h:
                put("FAIL", f"{nm}: unknown critical header parameter(s): {', '.join(h['crit'])}")
                continue
            if h.get("alg") != "EdDSA":
                put("FAIL", f"{nm}: malformed confirmation (alg {h.get('alg')!r})")
                continue
            problem = shape_problem(p)
            if problem:
                put("FAIL", f"{nm}: malformed confirmation ({problem})")
                continue
            unknown += unknown_members(p)
            if trust is None:
                key_of[nm] = "NOT-RUN"
                if not no_list_said:
                    res.append(("NOT-RUN", "no recipient list given (pass --recipients)"))
                    no_list_said = True
                continue
            if p["iss"] not in trust:
                put("NOT-RUN", f"{nm}: recipient {p['iss']} is not on the list")
                continue
            if h.get("kid") not in trust[p["iss"]]:
                put("NOT-RUN", f"{nm}: key {str(h.get('kid'))[:8]}... is not listed for {p['iss']}")
                continue
            try:
                Ed25519PublicKey.from_public_bytes(keys[h["kid"]]).verify(sig, si)
                put("PASS", None)
            except (InvalidSignature, KeyError):
                put(
                    "FAIL",
                    f"{nm}: the confirmation does not verify under the recipient's listed key",
                )
        detail = f"{n} confirmation(s), each verifying under the recipient's listed key"
        if unknown:
            detail += "; unknown member(s) ignored: " + ", ".join(sorted(set(unknown)))
        key = combine(res, detail)

    def caution():
        bad = [s["name"] for s, *_ in readable if key_of.get(s["name"]) != "PASS"]
        return ("; signature not verified for: " + ", ".join(bad)) if bad else ""

    # 1. Request
    if n == 0:
        request = ["NOT-RUN", empty]
    else:
        res = []
        for s, h, p, si, sig in readable:
            r = p.get("request", {}) if isinstance(p.get("request"), dict) else {}
            if "content_digest" in r and r["content_digest"] != st["content_digest"]:
                res.append(
                    ("FAIL", f"{s['name']}: the recipient confirmed a different request body")
                )
            elif (
                "signature_base_digest" in r
                and r["signature_base_digest"] != st["signature_base_digest"]
            ):
                res.append(
                    ("FAIL", f"{s['name']}: the recipient confirmed a different signature base")
                )
            elif "action_digest" in p and p["action_digest"] != st["action_digest"]:
                res.append(("FAIL", f"{s['name']}: the recipient confirmed a different action"))
            elif is_int(p.get("iat")) and p["iat"] > st["ended"] + win:
                res.append(
                    (
                        "FAIL",
                        f"{s['name']}: the confirmation is dated outside the step (iat {p['iat'] - st['ended']} s after it ended)",
                    )
                )
            elif is_int(p.get("iat")) and p["iat"] < st["started"] - win:
                res.append(
                    (
                        "FAIL",
                        f"{s['name']}: the confirmation is dated outside the step (iat {st['started'] - p['iat']} s before it started)",
                    )
                )
            else:
                res.append(("PASS", None))
        dated_only = sum(
            1 for s, h, p, *_ in readable if not p.get("request") and "action_digest" not in p
        )
        d = f"{n} confirmation(s) checked against the request {its(n)} step sent"
        if dated_only:
            d += f" ({dated_only} by date only)"
        request = combine(res, d + caution())

    # 2. Permit
    if n == 0:
        permit = ["NOT-RUN", empty]
    else:
        res = []
        for s, h, p, si, sig in readable:
            pm = p.get("permit") if isinstance(p.get("permit"), dict) else None
            if p.get("iss") != st["permit_aud"]:
                res.append(
                    (
                        "FAIL",
                        f"{s['name']}: confirmed by {p.get('iss')}, but the permit is for {st['permit_aud']}",
                    )
                )
            elif pm is not None and (pm.get("digest"), pm.get("iss"), pm.get("jti")) != (
                st["permit_digest"],
                st["permit_iss"],
                st["permit_jti"],
            ):
                res.append(("FAIL", f"{s['name']}: the confirmation cites another permit"))
            else:
                res.append(("PASS", None))
        by_recipient = sum(1 for s, h, p, *_ in readable if "permit" not in p)
        d = f"{n} confirmation(s) checked against the permit {its(n)} step presented"
        if by_recipient:
            d += f" ({by_recipient} by recipient only)"
        permit = combine(res, d + caution())

    # 4. Single use
    if n == 0:
        single = ["NOT-RUN", empty]
    else:
        cited, effected = set(), {}
        for s, h, p, si, sig in readable:
            if isinstance(p.get("permit"), dict):
                pid = (p["permit"].get("iss"), p["permit"].get("jti"))
                cited.add(pid)
                if p.get("outcome") == "effected":
                    effected.setdefault(pid, []).append((s["name"], s["confirmation"]))
        if not cited:
            single = ["NOT-RUN", "no confirmation cites a permit"]
        else:
            fails, repeats = [], 0
            for pid, lst in effected.items():
                distinct = []
                for nm, tok in lst:
                    if tok in [t for _, t in distinct]:
                        repeats += 1
                    else:
                        distinct.append((nm, tok))
                if len(distinct) > 1:
                    fails.append(
                        (
                            "FAIL",
                            f"permit {pid[0]} {pid[1]} confirmed as effected twice: "
                            + ", ".join(nm for nm, _ in distinct),
                        )
                    )
            d = f"{len(cited)} permit(s) cited, none confirmed as effected twice"
            if repeats:
                d += f" ({repeats} byte-identical repeat{'s' if repeats > 1 else ''})"
            single = combine(fails, d)

    # 5. Outcome
    res, parsed = [], {s["name"]: p for s, h, p, si, sig in readable}
    for s in steps:
        nm, ok = s["name"], s["outcome"] == "ok"
        if s["confirmation"] is None:
            res.append(("NOT-RUN", f"{nm}: presented a permit; no confirmation recorded"))
            continue
        if nm not in parsed:
            res.append(("NOT-RUN", f"{nm}: the confirmation could not be read"))
            continue
        p = parsed[nm]
        o = p.get("outcome")
        if ok and o == "refused" and "dependency" in p:
            res.append(
                (
                    "FAIL",
                    f"{nm}: reported ok, but the recipient could not check ({p['dependency']})",
                )
            )
        elif ok and o == "refused":
            res.append(
                (
                    "FAIL",
                    f"{nm}: reported ok, but the recipient says 'refused' ({p.get('reason')}, step {p.get('step')})",
                )
            )
        elif ok and o == "effect-unknown":
            res.append(("FAIL", f"{nm}: reported ok, but the recipient says 'effect-unknown'"))
        elif not ok and o == "effected":
            res.append(
                (
                    "FAIL",
                    f"{nm}: reported {s['outcome']}, but the recipient says it acted ({p.get('recipient_action_id')})",
                )
            )
        else:
            res.append(("PASS", None))
    outcome = combine(res, f"{len(steps)} step(s), each outcome consistent with its confirmation")
    return {
        "request": request,
        "permit": permit,
        "key": key,
        "single_use": single,
        "outcome": outcome,
    }


def main(path):
    doc = json.load(open(path, encoding="utf-8"))
    bad = 0
    for vid, vec in sorted(doc["vectors"].items()):
        got = rows(doc, vec)
        ok = got == vec["expect"]
        bad += not ok
        print(
            f"{vid} {'agree' if ok else 'DIFFER'}  " + " / ".join(f"{k}={got[k][0]}" for k in got)
        )
        if not ok:
            for k in got:
                if got[k] != vec["expect"][k]:
                    print(f"   {k}: got  {got[k]}\n   {' ' * len(k)}  want {vec['expect'][k]}")
    print(f"{len(doc['vectors']) - bad} of {len(doc['vectors'])} vectors agree")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
