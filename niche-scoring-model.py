# -*- coding: utf-8 -*-
# Weighted niche scoring. Higher = better FOR THIS PERSON on every row.
# Note: "capital_req", "competition", "barriers" are scored as benefit-to-him:
#   capital_req 100 = needs almost no capital to start
#   competition 100 = uncrowded relative to demand
#   barriers    100 = barrier is high once inside AND crossable by him at 19

W = {
 "wealth":9, "salary":4, "startup":6, "mkt_growth":9, "ai_resilience":3, "ai_leverage":9,
 "tech_moat":5, "fin_moat":2, "reg_moat":4, "network_fx":3, "barriers":3, "capital_req":3,
 "global_demand":4, "competition":3, "fit_background":5, "fit_interests":3, "speed":4,
 "prop_data":6, "founder":6, "p1m":4, "p5m":3, "p10m":2,
}
assert sum(W.values()) == 100, sum(W.values())

K = list(W.keys())

N = {
"1. Digital-asset risk & intelligence (incumbent thesis)":
  [55,60,50,62,55,65,55,35,80,55,60,45,55,45,70,90,70,65,50,60,40,28],
"2. AI systems risk & control in regulated finance":
  [72,72,78,88,80,95,62,40,78,55,65,80,85,60,88,78,72,78,80,72,52,35],
"3. Quantitative trading / systematic research":
  [78,98,35,55,60,85,80,85,55,25,90,25,60,20,65,60,35,60,35,65,42,22],
"4. AI infrastructure engineering (inference/systems)":
  [72,88,62,92,70,88,85,30,15,35,80,55,92,35,75,45,45,45,60,72,45,26],
"5. Applied / vertical AI product engineering (generic)":
  [75,70,88,90,55,92,40,25,25,45,30,88,85,25,80,60,85,60,85,62,45,32],
"6. AI & agent security for financial institutions":
  [68,78,72,88,85,82,65,35,70,45,65,82,88,45,78,62,62,60,72,70,48,30],
"7. Private credit + technology":
  [78,82,62,82,65,78,45,80,55,40,70,30,70,50,60,78,55,72,65,72,55,35],
"8. Energy + AI / power infrastructure":
  [70,72,65,92,88,60,60,25,75,25,78,20,85,60,40,40,40,50,55,62,40,25],
"9. Defence technology (AI / autonomy)":
  [70,68,72,90,82,82,70,40,88,30,82,45,60,55,65,30,45,55,62,62,45,30],
"10. Financial data infrastructure":
  [62,70,62,68,60,78,50,40,35,60,45,80,72,40,85,82,78,82,65,65,42,25],
}

rows=[]
for name, vals in N.items():
    assert len(vals)==len(K), (name, len(vals))
    tot = sum(W[k]*v for k,v in zip(K,vals))/100
    rows.append((tot,name,dict(zip(K,vals))))
rows.sort(reverse=True)

print(f"{'NICHE':<52} {'SCORE':>6}")
print("-"*60)
for tot,name,_ in rows:
    print(f"{name:<52} {tot:6.1f}")

print()
# sensitivity: what if wealth/founder/growth weights are halved and salary/resilience doubled?
W2 = dict(W); 
for k in ("wealth","founder","startup","mkt_growth"): W2[k]=W[k]//2
for k in ("salary","ai_resilience","fit_interests","speed"): W2[k]=W[k]*2
s=sum(W2.values())
print("SENSITIVITY (de-emphasise wealth/founder/growth, emphasise salary/resilience/interest/speed):")
alt=sorted((sum(W2[k]*v for k,v in zip(K,vals))/s*1.0, name) for name,vals in N.items())[::-1]
for tot,name in alt: print(f"{name:<52} {tot:6.1f}")

print()
print("ADVERSARIAL TEST: weights chosen to FAVOUR the digital-asset thesis")
W3 = dict.fromkeys(K, 2)
W3.update({"reg_moat":15,"fit_interests":15,"network_fx":10,"prop_data":10,
           "mkt_growth":10,"barriers":8,"wealth":8,"founder":6})
s3=sum(W3.values())
alt=sorted((sum(W3[k]*v for k,v in zip(K,vals))/s3, name) for name,vals in N.items())[::-1]
for tot,name in alt: print(f"{name:<52} {tot:6.1f}")
