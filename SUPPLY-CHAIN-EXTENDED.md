# WHAT YOUR CHAIN IS MISSING

Your layer-2 chain is accurate and better than most sell-side notes. Three
things sit outside it. Two of them are the actual binding constraints on the
whole boom — which means they are also the answer to a question we left open
earlier: *what breaks the chain?*

Short version: **it is not credit. It is power and packaging.**

---

## 1 · THE GAP INSIDE YOUR OWN CHAIN — ADVANCED PACKAGING

Your chain goes: dicing (Disco) → HBM mounted beside the GPU → ABF substrate →
inspection → test.

There is a step between dicing and mounting, and it is currently the tightest
link in the entire industry. **CoWoS** — Chip on Wafer on Substrate. TSMC's
advanced packaging process. It is what physically bonds the logic die and the
HBM stacks onto a silicon interposer so they can talk to each other fast enough
to matter.

Why it is the bottleneck and not the fab:

- TSMC scaled CoWoS from roughly **35,000 wafers a month in late 2024** toward
  a target of roughly **130,000 a month by end of 2026.** Nearly 4x in two
  years — and it is still not enough.
- 2026 demand runs around **1 million wafers** against supply covering about
  **80%** of it.
- **Nvidia has booked over half of TSMC's 2026–27 CoWoS capacity** — roughly
  60% of the global total.
- TSMC CEO C.C. Wei has described capacity as **"extremely tight and sold out
  through 2026."**
- **Lead times are 52 to 78 weeks.** A year to eighteen months.
- TSMC's 2026 capex is **$52–56bn**, with 10–20% of it going to advanced
  packaging alone.

**The reframe:** everyone says "chip shortage" and pictures a fab. The fab is
not the problem. TSMC can print the logic. What it cannot do fast enough is
*glue the logic to the memory.* Nvidia's revenue ceiling next year is not set
by demand or by wafer starts — it is set by how many packages TSMC can bond.

That is a script. **"The AI shortage isn't chips. It's glue."**

---

## 2 · THE LAYER YOU SKIPPED — LAYER 1, ENERGY

You listed energy as layer 1 and moved straight past it. It has quietly become
the hard limit.

**Grid capacity has replaced GPU availability as the primary constraint on
building data centres.** The numbers:

- A new data centre campus takes **2–3 years** to build.
  Grid interconnection takes **4–10 years.**
- US interconnection queues held roughly **2,600 GW** in early 2026.
- Texas: interconnection requests hit around **474 GW**, roughly **90% of it
  data centres** — more than **five times the state's all-time record peak
  demand.** Governor Abbott ordered an audit of every data centre in the ERCOT
  queue on **3 August 2026.**
- Gas turbines: GE Vernova booked **over $30bn** in orders in 2025, with
  heavy-duty slots allocated **through 2029.** Mitsubishi Power moved to
  selective order acceptance — turning customers away.
- H1 2026 power equipment priced **20%+ above Q4 2025.**
- The tightest link is not generation. It is **transformers and switchgear.**

**The reframe, and it is the important one:** money can fix a credit problem.
It cannot fix a queue. If a hyperscaler wants power in Texas in 2027, no amount
of capital moves them up a line that is four to ten years long. The physical
world has a lead time, and it is longer than the financing cycle.

This is why the "AI bubble" question is badly framed. The question is not
whether the money runs out. It is whether **the electricity arrives before the
debt comes due.**

---

## 3 · THE COMPANY YOU MENTIONED BUT UNDERSOLD — BROADCOM

You listed Broadcom alongside AMD as an also-ran to Nvidia. It is not an
also-ran. It is a structural competitor doing two different jobs.

**Job one — networking.** Roughly **40% of Broadcom's AI revenue.** Once a
cluster passes a certain size, the constraint stops being how fast each chip
computes and becomes how fast the chips talk. Broadcom's Jericho 4 switch runs
**51.2 Tbps** and is built to interconnect **over a million** accelerators.
Nvidia's competing Spectrum-X1600 is not in volume until H2 2026. Broadcom is
shipping now.

**Job two — custom chips (XPUs).** Broadcom does not sell its own GPU. It
co-designs a customer's own accelerator and hands it to TSMC. Six major
customers, including:

- **Google** — seven generations of TPU since 2014
- **Meta** — MTIA
- **ByteDance**

Broadcom's AI semiconductor revenue grew **143% year on year to $10.8bn.**
Custom XPUs offer **30–50% lower total cost of ownership** than a general
GPU for a workload the customer already knows the shape of.

**The reframe:** Nvidia's real competitive threat is not AMD building a better
GPU. It is Google, Meta and Amazon deciding they do not need to buy one — and
Broadcom is the company that makes that possible. Every hyperscaler that goes
custom is a customer Nvidia loses permanently, not a sale it loses this quarter.

---

## WHAT THIS CHANGES IN THE WORK WE ALREADY HAVE

### It revises the order of transmission in AI-CREDIT-WATCHLIST.md

I had it as: financing tightens → CoreWeave and the neoclouds struggle →
orders get cancelled → Nvidia's revenue falls.

That is one path and it is still live. But there is a shorter one that does
not need anybody's credit to fail:

> Power does not arrive → the data centre sits half-energised → the operator
> cannot bill for compute it cannot run → *now* the debt is a problem.

Same ending. But the trigger is a substation, not a bond market. And a
substation is much easier to see coming, because the queue is public.

### It changes what "sold out" means

Nvidia guiding to $108bn next quarter is not purely a demand signal. With CoWoS
sold out through 2026 and booked over a year ahead, that guidance is closer to
a **supply** statement. They are telling you what TSMC can bond for them, not
what customers would buy at any price. That is a much less bullish sentence
than it sounds, and nobody reads it that way.

### It gives the China script a harder edge

The US is not just outspending China on models. It is outspending China on an
input — electricity — where China added more generating capacity last year than
the US has in a decade. If compute becomes power-limited rather than chip-
limited, export controls stop being the deciding variable.

---

## SCRIPTS THIS OPENS UP

1. **"The AI shortage isn't chips. It's glue."** — CoWoS. Nobody has heard of
   it, it is 52–78 week lead times, and Nvidia has booked 60% of the world's.
2. **"Texas just audited every data centre in the queue."** — 474 GW, 90% data
   centres, five times the state's record demand. A real, dated, verifiable
   event from three weeks ago.
3. **"Nvidia's biggest competitor doesn't sell a chip."** — Broadcom, custom
   XPUs, Google's seven TPU generations.
4. **"They can build the data centre in two years. The power takes ten."** —
   the single cleanest statement of the whole constraint.
5. **"Nvidia isn't sold out because everyone wants one."** — the guidance-as-
   supply-statement reframe.

---

## WHAT I STILL DO NOT HAVE, AND YOU MIGHT

- Where **hyperscalers** sit in your five layers. They buy layer 2, own layer
  3, build layer 4, and sell layer 5. They are not a layer — they are a column
  cutting through four of them. Worth deciding how you frame that on camera.
- Whether **fabrication** deserves to be its own layer rather than living
  inside "chips". On lead times and chokepoints it behaves like a separate one.
- Layer 3 in the detail you gave layer 2 — cooling, interconnect, the actual
  economics of a colocation contract.

---

*Figures from public reporting and company disclosure as of August 2026.
Direct company IR pages are blocked from this environment, so these came via
search results rather than primary filings — treat the round numbers as
directionally right rather than to the decimal.*
