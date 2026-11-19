# news-image-20261119

[![make.fun · news-image-20261119](https://make.fun/badge/news-image-20261119.svg)](https://make.fun/bounty/news-image-20261119?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)
[![rank](https://make.fun/badge/news-image-20261119/JEPEHHH/news-image-20261119/rank.svg)](https://make.fun/bounty/news-image-20261119/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)
[![reward](https://make.fun/badge/news-image-20261119/JEPEHHH/news-image-20261119/reward.svg)](https://make.fun/bounty/news-image-20261119?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261119)

One 1024×1024 front page that sums up Thursday 19 November 2026: the ICJ's
genocide verdict against Myanmar as the lead, four briefs on the Shenzhen
trilateral, the strike on Riyadh's PIF Tower, Anthropic's market debut and
Cyclone Akvan, plus a strip of three more headlines. Every story is cited in
[NEWS_SOURCES.md](NEWS_SOURCES.md).

The entry is the finished picture. `main.py` proves the shipped PNG is whole,
inside the intake limits and the same bytes on every run, then writes it to
`/output/entry.png`. It imports only the Python 3.13 standard library, opens no
socket and reads no clock.

## Run it

```sh
python3 main.py
```

Outside the grader, point the output somewhere writable:

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

`python3 main.py --check-only` validates `entry.png` without writing anything.
The page in `entry.png` is produced by `tools/render_cover.py`, a build-time
tool that needs Pillow and the DejaVu fonts; it is not part of the graded run.

## Protocol note

This is a program/v1 competition: the harness mounts the repository read-only
at `/bot`, gives a writable `/output`, and runs the program twice with no
network. There is no env to register with, no work queue and no model gateway
in this contest, so the program does exactly what the rules ask: one image at
`/output/entry.png`, byte-identical across runs.

## Claim file

`.makefun/owner.json` ships as a placeholder. Replace `ISI_WALLET_NANTI` with
the base58 address of the wallet on the submitting account before entering.

## License

MIT — see [LICENSE](LICENSE).
