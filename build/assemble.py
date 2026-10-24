"""Assemble the standalone page for deployment into site/index.html."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = os.path.join(ROOT, "docs")
SITE_URL = "https://julian-cloud-max.github.io/poker-ranges/"

TAILWIND = ["npx", "--yes", "tailwindcss@3.4.17", "-i", os.path.join(HERE, "input.css"),
            "-o", os.path.join(HERE, "tw.css"),
            "--config", os.path.join(ROOT, "tailwind.config.js"), "--minify"]


def run_tailwind():
    r = subprocess.run(TAILWIND, capture_output=True, text=True, shell=True)
    if r.returncode != 0:
        sys.exit("tailwind failed:\n" + (r.stderr or r.stdout))
    print("tailwind ok")


def git_build_id():
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, cwd=ROOT)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    import datetime
    return datetime.date.today().isoformat()


def main():
    os.makedirs(SITE, exist_ok=True)
    run_tailwind()

    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    css = open(os.path.join(HERE, "tw.css"), encoding="utf-8").read()
    data = open(os.path.join(HERE, "data.json"), encoding="utf-8").read()
    post = open(os.path.join(HERE, "postflop.json"), encoding="utf-8").read()

    # 注入为同一份全局数据的两个分支
    merged = data[:-1] + ',"postflop":' + post + "}"
    assert json.loads(merged)["postflop"]["textures"], "merged data invalid"

    html = (tpl
            .replace("/*__CSS__*/", css)
            .replace("/*__DATA__*/", merged)
            .replace("__SITE_URL__", SITE_URL)
            .replace("__BUILD__", git_build_id()))

    out = os.path.join(SITE, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote", out, len(html), "bytes")


if __name__ == "__main__":
    main()
