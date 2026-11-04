# -*- coding: utf-8 -*-
"""Extract dsh-skill-office assets from app.asar (used when runtime/ is already wiped)."""
import argparse, io, json, os, sys

def walk(node, prefix, out):
    for name, meta in node.get("files", {}).items():
        p = prefix + "/" + name if prefix else name
        if "files" in meta:
            walk(meta, p, out)
        else:
            out.append((p, meta))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asar", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--prefix", default="dsh/node_modules/@deepseek-ai/dsh-skill-office/assets")
    a = ap.parse_args()
    f = io.open(a.asar, "rb")
    head = f.read(16)
    if len(head) < 16 or head[4:8] != b"\x04\x00\x00\x00":
        print("not an asar archive", file=sys.stderr); return 2
    jlen = int.from_bytes(head[8:12], "little")
    hdr, end = json.JSONDecoder().raw_decode(f.read(jlen).decode("utf-8"))
    base = 12 + end + 4
    node = hdr
    for part in a.prefix.split("/"):
        node = node.get("files", {}).get(part)
        if node is None:
            print("prefix not found in asar: " + a.prefix, file=sys.stderr); return 3
    files = []
    walk(node, "", files)
    unpacked = a.asar + ".unpacked"
    n = 0
    for rel, m in files:
        dst = os.path.join(a.out, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if "offset" in m:
            f.seek(base + int(m["offset"]))
            data = f.read(int(m["size"]))
        else:
            p = os.path.join(unpacked, *a.prefix.split("/"), *rel.split("/"))
            data = io.open(p, "rb").read()
        io.open(dst, "wb").write(data)
        n += 1
    print("extracted %d file(s) -> %s" % (n, a.out))
    return 0

if __name__ == "__main__":
    sys.exit(main())