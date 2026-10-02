"""Update impact's "Revenue per user/day" row: the engine stores it per 1,000 users (unit 'usd1k'); the page must show it
PER USER (÷1,000) under its per-user label — a per-1,000 number under a per-user label reads 1,000× too high."""
import json, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "..", "frontend", "index.html")


def _fn(src, name):
    i = src.index("function %s(" % name)
    j = src.index("\n//", i)   # the function ends where the next comment block starts
    return src[i:j]


def test_usd1k_rows_are_formatted_per_user():
    src = open(PAGE, encoding="utf-8").read()
    assert "(u==='usd1k'?uniMoneyPU(+v,x.currency):" in src
    js = """
    const DATA={usd_inr:96}; let VIEW='USD';
    const baseCur=()=>'USD', cfx=()=>VIEW==='INR'?96:1, csym=()=>VIEW==='INR'?'₹':'$';
    %s
    const out=[uniMoneyPU(22.13,'USD'), uniMoneyPU(1850,'USD'), uniMoneyPU(0,'USD')];
    VIEW='INR'; out.push(uniMoneyPU(22.13,'USD'));
    console.log(JSON.stringify(out));
    """ % _fn(src, "uniMoneyPU")
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
    assert json.loads(r.stdout) == ["$0.0221", "$1.85", "$0", "₹2.12"]
