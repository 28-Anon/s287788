# LAYER 2 — WHAT ACTUALLY HAPPENS

Supplied by the channel owner. My additions are marked.

---

## THE CHAIN, IN ORDER

An infrastructure player building a data centre places a chip order with
**AMD, Nvidia or Broadcom.**

**1 · Design software — EDA**
The chipmaker designs the chip in EDA software. Think CAD, for silicon.
Two majors: **Cadence** and **Synopsys**.
> *Note: it is **EDA** — Electronic Design Automation. Worth getting right on
> camera. And **Synopsys** spelt that way.*

**2 · Fabrication — the fab**
Design goes to **TSMC** (Taiwan Semiconductor Manufacturing Company), which
produces about **90% of cutting-edge logic chips.** This is why Taiwan matters
so much politically to the US.

**3 · Inside the fab**

| Step | What it does | Who |
|---|---|---|
| Polished silicon wafers | the base material | **Shin-Etsu**, **SUMCO** — about half the world's supply, both Tokyo-listed |
| Deposition | lays a thin film on the wafer — the material the circuit is built from | **Applied Materials**, **Lam Research** |
| Photoresist coating machine | | **Tokyo Electron** |
| Photoresist itself | | **Shin-Etsu**, **JSR** (private) |
| Lithography | prints the pattern | **ASML** (Netherlands) — the *only* company making leading-edge machines. China has just built its first, one tier down |

**The wafer goes back through these same machines around 80 times.**

| Step | What it does | Who |
|---|---|---|
| Dicing | cuts the wafer into individual chips | **Disco** (Japan) |
| Memory (HBM) | mounted beside the GPU | **Micron**, **SK hynix** |
| ABF substrate | the film the whole thing sits on | **Ajinomoto** (Japan — the company that invented MSG) |
| Inspection | checks every layer as it is built | **KLA** |
| Final electrical test | | **Advantest**, **Teradyne** |

**4 · Nvidia does not sell chips. It sells racks.**
TSMC ships the finished chip to a Taiwanese manufacturer — **Foxconn** or
**Wistron** — who mount it on Nvidia's board, build that into a compute tray,
add switch trays, networking and liquid cooling. The finished rack runs about
**$6 million**. That is what ships to the customer.

---

## WHAT THIS CHANGES

### The chokepoints are mostly not American, and mostly not in SMH

SMH holds 25 **US-listed** companies. But look at the single points of failure:

- **ASML** — Netherlands. One company on earth for leading-edge lithography.
- **TSMC** — Taiwan. ~90% of cutting-edge logic.
- **Shin-Etsu, SUMCO, Tokyo Electron, Disco, Ajinomoto, Advantest** — Tokyo.
- **JSR** — private.

**You cannot buy the AI supply chain from the US market.** The ETF everybody
uses to "own semis" misses most of the places it would actually break. That is
a video on its own.

### It revises my read on Nvidia's receivables

I had the $24.6bn build in receivables down as a warning sign — customers
booked but not paying. **Selling $6m racks rather than chips changes that.**
Multi-million-dollar systems assembled by third parties and shipped physically
have a long, lumpy working-capital cycle by nature. Some of that build is the
business model, not distress.

It does not erase the concern — cash still fell 56% while sales rose — but I
overweighted it, and any script should say systems, not chips.

### Single points of failure worth a script each

- **One Dutch company decides who gets to build advanced AI.** ASML.
- **The company that invented MSG is a chokepoint in AI.** Ajinomoto's ABF
  substrate. That is a hook that writes itself.
- **The same machines, eighty times.** Nobody outside the industry knows this.
- **China building one tier down** — the export control story in a single fact.

---

## THE MODEL LADDER — why world models

Five stages to get here:

1. Traditional AI
2. **LLMs** — ChatGPT, Claude, Gemini
3. Multimodal models
4. Agentic models
5. **World models** — underpin industries involving the real world

The point: everything that generated the hype so far was **stage two**. Text.

### The two papers

**Ha & Schmidhuber, "World Models" (2018)** — arXiv 1803.10122. The founding
idea: an agent learns a compressed model of its environment, then trains
*inside its own imagination* rather than in the real world.

**"World-Gymnast" (Feb 2026)** — arXiv 2602.02454. Trains a vision-language-
action policy by rolling it out inside an action-conditioned video world model,
scored by a vision-language model. On real robot hardware it beat supervised
finetuning **by up to 18x**, and beat software simulators **by up to 2x**.

**That gap is the argument.** The bottleneck in robotics has always been real
world data — it is slow, expensive and dangerous to collect. Training inside a
learned world model now beats both alternatives on real hardware. 2018 was the
idea; 2026 is it working.

Which is why layer 4 is not finished when the chatbots stop impressing people.
The models that touch factories, vehicles and machines have not arrived yet.
