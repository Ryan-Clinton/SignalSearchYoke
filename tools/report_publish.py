"""The report laid out for ryanclinton.uk (its docs/posting-signalsearch.md)
and printed to PDF: publish/findings/SLUG/ with report.md (a +++ TOML
header, then the report from its first ## heading), the figures it names
and report-vVERSION.pdf. Run after tools/report.py; publish/ is not in git.

    python tools/report_publish.py           lay out and print
    python tools/report_publish.py --post    also send it to the site's inbox (only on Ryan's go)

The PDF is printed by headless Chrome from an HTML page made here from the
Markdown (headings, paragraphs, lists, tables, emphasis, figures; links
written as plain text, so the PDF carries no link actions). Its text and
metadata are checked for home paths before anything is posted.
"""
import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import report  # noqa: E402

SLUG = "comparing-searches"
TITLE = "Comparing radio-signal searches on Breakthrough Listen data"
SUMMARY = ("Planted signals in Breakthrough Listen's Green Bank data, counted at matched false-candidate rates: "
           "a new search against turboSETI and BLISS on two sessions, the second fixed in advance, where both "
           "pipelines failed the false-candidate limit.")
# The public versions only: 0.1 was a draft never published, and the site dates the
# report (citation_publication_date) from the first version listed.
REVISIONS = (
    ("1.0", "2026-11-19", "First release: the signals BLISS finds and this search misses traced stage by stage, "
                          "and the detector's misses measured.", True),
    ("1.1", "2026-11-19", "The code's repository, now public, linked.", True),
    ("1.2", "2026-11-19", "The third session, chosen and fixed in advance (NGC 6946 at C band): every criterion "
                          "held.", True),
    ("1.3", "2026-11-19", "Recovery at every tested cut for all three sessions; step 12 described as meeting its "
                          "criteria at the point estimate; what the injections and the false-candidate control "
                          "measure.", True),
    ("1.4", "2026-11-19", "Recovery weighted to each session's crowded and clean blocks beside the sample's; "
                          "the neighbouring-block check over consecutive blocks; one rule for the matched cut.", True),
    ("1.5", None, "Checks of the planted signals (a tone in the voltages, finer sampling, the DC bin, a fixed "
                  "flux): none moves recovery.", True),
)
CHROME = (Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
          Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"))
PUBLISH = ROOT / "publish"
HOME = re.compile(rb"[A-Za-z]:[\\/]+Users|/home/|/Users/|facepipe", re.I)


def _inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    t = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1 (\2)", t)
    return t


def to_html(md, title):
    out, para, lst, table = [], [], [], []

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()
        if lst:
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in lst) + "</ul>")
            lst.clear()
        if table:
            rows = [r for r in table if not re.fullmatch(r"\|(\s*:?-+:?\s*\|)+", r.replace(" ", ""))]
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
            head = "".join(f"<th>{_inline(c)}</th>" for c in cells[0])
            body = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in cells[1:])
            out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            table.clear()

    for line in md.splitlines():
        m = re.match(r"(#{1,4}) (.*)", line)
        img = re.fullmatch(r"!\[(.+?)\]\((.+?)\)", line.strip())
        if m:
            flush()
            k = len(m.group(1))
            out.append(f"<h{k}>{_inline(m.group(2))}</h{k}>")
        elif img:
            flush()
            out.append(f'<figure><img src="{html.escape(img.group(2))}" alt="{html.escape(img.group(1))}"></figure>')
        elif line.startswith("|"):
            if para or lst:
                flush()
            table.append(line)
        elif line.startswith("- "):
            if para or table:
                flush()
            lst.append(line[2:])
        elif line.startswith("  ") and lst:
            lst[-1] += " " + line.strip()
        elif not line.strip():
            flush()
        else:
            if table:
                flush()
            para.append(line.strip())
    flush()
    css = """
    @page { size: A4; margin: 20mm 18mm; }
    body { font-family: Georgia, 'Times New Roman', serif; font-size: 10.5pt; line-height: 1.45; color: #111;
           font-variant-numeric: lining-nums tabular-nums; }
    h1 { font-size: 18pt; margin: 0 0 4pt; } h2 { font-size: 13pt; margin: 16pt 0 4pt; }
    h3 { font-size: 11pt; } p, li { text-align: left; } code { font-size: 9.5pt; }
    table { border-collapse: collapse; margin: 8pt 0; font-size: 9pt; }
    th, td { border-bottom: 1px solid #999; padding: 3pt 6pt; text-align: left; vertical-align: top; }
    figure { margin: 10pt 0; } img { width: 100%; }
    """
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>{html.escape(title)}</title>"
            f"<style>{css}</style></head><body>{''.join(out)}</body></html>")


def _chrome():
    for c in CHROME:
        if c.exists():
            return c
    raise SystemExit("report_publish.py: no Chrome or Edge to print the PDF with")


def pdf(md_full, figures, out_pdf):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for f in figures:
            shutil.copy2(f, tmp / f.name)
        page = tmp / "report.html"
        page.write_text(to_html(md_full, TITLE), encoding="utf-8")
        done = subprocess.run([str(_chrome()), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                               "--no-first-run", f"--user-data-dir={tmp / 'profile'}",
                               f"--print-to-pdf={out_pdf}", page.as_uri()],
                              capture_output=True, text=True, timeout=180)
        if not out_pdf.exists():
            raise SystemExit(f"report_publish.py: the PDF was not printed: {done.stderr[-500:]}")
    data = out_pdf.read_bytes()
    for bad in (b"/JavaScript", b"/Launch", b"/URI", b"/AcroForm", b"/EmbeddedFile", b"/Encrypt"):
        if bad in data:
            raise SystemExit(f"report_publish.py: the PDF holds {bad.decode()}; the site would refuse it")
    if HOME.search(data):
        raise SystemExit("report_publish.py: the PDF names a home path")


def header(version, date, commit, pdf_name):
    lines = ["+++", f'title = "{TITLE}"', f'summary = "{SUMMARY}"', f'version = "{version}"', f"date = {date}",
             f'commit = "{commit}"', f'pdf = "{pdf_name}"', ""]
    for v, d, note, has_pdf in REVISIONS:
        lines += ["[[revisions]]", f'version = "{v}"', f"date = {d or date}", f'note = "{note}"']
        if has_pdf:
            lines.append(f'pdf = "report-v{v}.pdf"')
        lines.append("")
    lines.append("+++")
    return "\n".join(lines)


def main():
    if report.VERSION != REVISIONS[-1][0]:
        raise SystemExit(f"report_publish.py: report.py is at {report.VERSION}, the revisions end at "
                         f"{REVISIONS[-1][0]}")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "tools", "docs/report", "*.py"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        raise SystemExit(f"report_publish.py: commit first, the report must be built from a commit:\n{dirty}")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()[:12]
    md = report.OUT.read_text(encoding="utf-8")
    body = md[md.index("\n## ") + 1:]
    body = body[:body.index("## Records this version was written from")].rstrip() + "\n"
    figures = [report.OUT.parent / f for f in re.findall(r"!\[.+?\]\((.+?)\)", body)]
    if HOME.search(md.encode("utf-8")):
        raise SystemExit("report_publish.py: the report names a home path")
    for f in figures:
        svg = f.read_text(encoding="utf-8")
        if re.search(r"<script|<foreignObject|<a[\s>]|<use|<image|<animate|<set[\s>]|\son\w+=|href|url\(", svg, re.I):
            raise SystemExit(f"report_publish.py: {f.name} holds something the site refuses in an SVG")
    folder = PUBLISH / "findings" / SLUG
    folder.mkdir(parents=True, exist_ok=True)
    pdf_name = f"report-v{report.VERSION}.pdf"
    full = md[:md.index("## Records this version was written from")].rstrip() + "\n"
    pdf(full, figures, folder / pdf_name)
    for f in figures:
        shutil.copy2(f, folder / f.name)
    (folder / "report.md").write_text(header(report.VERSION, report.DATE, commit, pdf_name) + "\n" + body,
                                      encoding="utf-8", newline="\n")
    print(f"{folder}: report.md, {', '.join(f.name for f in figures)}, {pdf_name} (commit {commit})")
    if "--post" in sys.argv[1:]:
        cmd = ("cd /mnt/c/Projects/SignalSearchYoke/publish && rsync -rt findings ryanclinton-signalsearch: "
               "&& touch READY && rsync READY ryanclinton-signalsearch:READY && rm READY")
        done = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True)
        print("posted" if done.returncode == 0 else f"post failed: {done.stderr.decode(errors='replace')[-500:]}")
        return done.returncode


if __name__ == "__main__":
    sys.exit(main())
