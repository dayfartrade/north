"""Position sizing across gold vehicles (GC, MGC, GLD).

Vehicles:
  - GC  : full gold futures, 100 oz/contract, ~$0.10 tick = $10 P&L/tick
  - MGC : micro gold futures, 10 oz/contract, ~$0.10 tick = $1 P&L/tick
  - GLD : ETF, ~1/10 of spot gold price; 100 shares ≈ 1 oz exposure (~$0.50 per share moves)

Sizing modes:
  - fixed_frac : risk a fixed % of equity per trade
  - fixed_$    : risk a fixed dollar amount per trade
  - kelly_half : half-Kelly using v5 backtest expectancy (use cautiously)

Output recommends the cheapest viable vehicle for the user's account.
"""
from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass
class Vehicle:
    name: str
    units_per_contract: float    # ounces or shares
    multiplier: float            # $ P&L per 1.00 price move per 1 contract/share unit
    typical_margin: float        # estimated initial margin in $

GC  = Vehicle("GC",  units_per_contract=100, multiplier=100.0, typical_margin=11_000)
MGC = Vehicle("MGC", units_per_contract=10,  multiplier=10.0,  typical_margin=1_100)
GLD = Vehicle("GLD", units_per_contract=1,   multiplier=1.0,   typical_margin=0)  # ETF, no margin (cash) — uses share price as cost


@dataclass
class SizingConfig:
    mode: str = "fixed_frac"
    account_equity: float = 25000
    risk_pct: float = 0.01           # 1% per trade (sane default)
    fixed_risk_dollars: float = 250
    win_rate: float = 0.553
    payoff_ratio: float = 2.0


def kelly_fraction(p: float, b: float) -> float:
    if b <= 0:
        return 0.0
    return max(0.0, (p * (b + 1) - 1) / b)


def _target_risk(cfg: SizingConfig) -> tuple[float, str]:
    if cfg.mode == "fixed_frac":
        return cfg.account_equity * cfg.risk_pct, \
               f"fixed-frac {cfg.risk_pct*100:.2f}% × ${cfg.account_equity:,.0f}"
    if cfg.mode == "fixed_$":
        return cfg.fixed_risk_dollars, f"fixed-$ ${cfg.fixed_risk_dollars:,.0f}"
    if cfg.mode == "kelly_half":
        f = kelly_fraction(cfg.win_rate, cfg.payoff_ratio) * 0.5
        return cfg.account_equity * f, \
               f"half-Kelly f*={f*100:.2f}% (full {kelly_fraction(cfg.win_rate, cfg.payoff_ratio)*100:.2f}%)"
    raise ValueError(cfg.mode)


def size_for_vehicle(stop_dist_per_oz: float, vehicle: Vehicle,
                      gld_price: float | None, cfg: SizingConfig) -> dict:
    """Stop distance is given in $/oz of underlying gold price."""
    target, notes = _target_risk(cfg)

    if vehicle.name == "GLD":
        # GLD ≈ spot/10 in $/share. Stop distance in $/share ≈ stop_dist/10.
        if gld_price is None or gld_price <= 0:
            return {"vehicle": "GLD", "viable": False, "reason": "no GLD price"}
        share_stop = stop_dist_per_oz / 10.0
        # Cost: ~$0.02 per share spread+slippage RT
        rt_cost_per_share = 0.02
        net_stop = share_stop + rt_cost_per_share
        risk_per_unit = net_stop  # per share
        if risk_per_unit <= 0:
            return {"vehicle": "GLD", "viable": False, "reason": "zero stop"}
        n_units = math.floor(target / risk_per_unit)
        cost = n_units * gld_price
        # Cap position to what cash + 50% Reg-T margin can hold
        max_position_value = cfg.account_equity * 1.5
        if cost > max_position_value:
            n_units = max(0, math.floor(max_position_value / gld_price))
            cost = n_units * gld_price
            cap_note = " (capped by buying-power)"
        else:
            cap_note = ""
        viable = n_units >= 1
        reason = "" if viable else \
                 ("share cost > 1.5× equity" if target / risk_per_unit > max_position_value / gld_price
                  else "risk too small for any GLD share")
        return {
            "vehicle": "GLD",
            "viable": viable,
            "n_units": n_units,
            "unit_label": "shares",
            "cost": cost,
            "dollar_risk_at_stop": n_units * risk_per_unit,
            "target_risk": target,
            "risk_per_unit": risk_per_unit,
            "notes": notes + cap_note,
            "reason": reason,
        }

    # Futures: risk per contract = stop_dist_per_oz * units_per_contract + RT cost
    risk_per_contract = stop_dist_per_oz * vehicle.units_per_contract
    # RT cost from backtest.RT_COST_PER_OZ ($0.19/oz w/ $0.05 spread); MGC ~half-ish
    rt_cost = 19 if vehicle.name == "GC" else 4  # $/contract RT (MGC scales lower)
    risk_per_contract += rt_cost
    n_contracts = max(0, math.floor(target / risk_per_contract))
    if n_contracts == 0 and target / risk_per_contract >= 0.5:
        n_contracts = 1
    margin_needed = n_contracts * vehicle.typical_margin
    return {
        "vehicle": vehicle.name,
        "viable": n_contracts >= 1 and margin_needed <= cfg.account_equity * 0.5,
        "n_units": n_contracts,
        "unit_label": "contracts",
        "cost": margin_needed,
        "dollar_risk_at_stop": n_contracts * risk_per_contract,
        "target_risk": target,
        "risk_per_unit": risk_per_contract,
        "notes": notes,
    }


def recommend(stop_dist_per_oz: float, gld_price: float | None,
              cfg: SizingConfig) -> list[dict]:
    """Return sizing for GC, MGC, GLD in order. Mark which is recommended."""
    out = [
        size_for_vehicle(stop_dist_per_oz, GC,  None,      cfg),
        size_for_vehicle(stop_dist_per_oz, MGC, None,      cfg),
        size_for_vehicle(stop_dist_per_oz, GLD, gld_price, cfg),
    ]
    # Recommendation: prefer the SMALLEST viable vehicle (granularity & affordability).
    # Order checked: GLD > MGC > GC (GLD has finest granularity per dollar at risk)
    rec_name = None
    for name in ("GLD", "MGC", "GC"):
        r = next((x for x in out if x["vehicle"] == name), None)
        if r and r.get("viable"):
            rec_name = name
            break
    for r in out:
        r["recommended"] = (r["vehicle"] == rec_name)
    return out


def format_for_alert(rows: list[dict]) -> str:
    parts = ["*Position sizing*"]
    for r in rows:
        marker = "👉 " if r.get("recommended") else "   "
        if not r.get("viable"):
            reason = r.get("reason", "risk too large for this account")
            parts.append(f"{marker}{r['vehicle']}: not viable ({reason})")
            continue
        if r["vehicle"] == "GLD":
            parts.append(f"{marker}{r['vehicle']}: *{r['n_units']} shares*  "
                         f"cost ≈ ${r['cost']:,.0f}  risk@stop ${r['dollar_risk_at_stop']:,.0f}")
        else:
            parts.append(f"{marker}{r['vehicle']}: *{r['n_units']} contract(s)*  "
                         f"margin ≈ ${r['cost']:,.0f}  risk@stop ${r['dollar_risk_at_stop']:,.0f}")
    return "\n".join(parts)


DEFAULT_CONFIG = SizingConfig(
    mode="fixed_frac",
    account_equity=25000,
    risk_pct=0.01,
)


if __name__ == "__main__":
    # Example: stop distance $30/oz, GLD price ~$400
    rows = recommend(stop_dist_per_oz=30.0, gld_price=400.0, cfg=DEFAULT_CONFIG)
    print("--- $25k account, 1% risk, stop=$30/oz ---")
    print(format_for_alert(rows))
    print()
    print("--- $5k account, 1% risk ---")
    rows = recommend(30.0, 400.0, SizingConfig(account_equity=5000, risk_pct=0.01))
    print(format_for_alert(rows))
    print()
    print("--- $100k account, 1% risk ---")
    rows = recommend(30.0, 400.0, SizingConfig(account_equity=100000, risk_pct=0.01))
    print(format_for_alert(rows))
