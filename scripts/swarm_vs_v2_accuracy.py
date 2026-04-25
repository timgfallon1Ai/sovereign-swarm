#!/usr/bin/env python3
"""
BTC Swarm vs V2 Prediction Accuracy Analysis
=============================================
Compares swarm consensus predictions against V2Engine predictions
using the last 50 settled KXBTC15M markets.
"""

from dataclasses import dataclass


# --- RAW DATA: Last 50 settled KXBTC15M markets (chronological, earliest first) ---
# Format: (time, outcome)  where "yes" = Up, "no" = Down
SETTLED_MARKETS = [
    ("08:15", "no"),
    ("08:30", "yes"),
    ("08:45", "yes"),
    ("09:00", "no"),
    ("09:15", "no"),
    ("09:30", "yes"),
    ("09:45", "no"),
    ("10:00", "yes"),
    ("10:15", "no"),
    ("10:30", "no"),
    ("10:45", "yes"),
    ("11:00", "yes"),
    ("11:15", "yes"),
    ("11:30", "no"),
    ("11:45", "no"),
    ("12:00", "yes"),
    ("12:15", "no"),
    ("12:30", "no"),
    ("12:45", "no"),
    ("13:00", "yes"),
    ("13:15", "yes"),
    ("13:30", "yes"),
    ("13:45", "no"),
    ("14:00", "yes"),
    ("14:15", "yes"),
    ("14:30", "yes"),
    ("14:45", "no"),
    ("15:00", "yes"),
    ("15:15", "no"),
    ("15:30", "yes"),
    ("15:45", "yes"),
    ("16:00", "yes"),
    ("16:15", "no"),
    ("16:30", "yes"),
    ("16:45", "yes"),
    ("17:00", "no"),
    ("17:15", "no"),
    ("17:30", "no"),
    ("17:45", "no"),
    ("18:00", "no"),
    ("18:15", "no"),
    ("18:30", "no"),
    ("18:45", "yes"),
    ("19:00", "no"),
    ("19:15", "yes"),
    ("19:30", "yes"),
    ("19:45", "no"),
    ("20:00", "no"),
    ("20:15", "no"),
    ("20:30", "no"),
]

# --- SWARM CONSENSUS MAPPING (from observed logs) ---
# The swarm updates slowly — it holds a direction for extended periods.
# Mapping observed consensus direction to time ranges:
SWARM_CONSENSUS = [
    # (start_time, end_time, predicted_direction)
    # Early/morning session: swarm was predicting Up
    ("08:15", "12:59", "Up"),
    # 13:00-15:00: Swarm was Up with 87.5% agreement
    ("13:00", "14:59", "Up"),
    # 15:00-17:30: Swarm stayed Up with 87.5-88% agreement
    ("15:00", "17:29", "Up"),
    # 17:30-18:30: Swarm flipped to Down with 87.5-88% agreement
    ("17:30", "18:29", "Down"),
    # 18:30-20:30: Swarm stayed Down with 87-88% agreement
    ("18:30", "20:30", "Down"),
]


def time_to_minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def get_swarm_prediction(time_str: str) -> str:
    """Get swarm's predicted direction for a given market window."""
    t = time_to_minutes(time_str)
    for start, end, direction in SWARM_CONSENSUS:
        if time_to_minutes(start) <= t <= time_to_minutes(end):
            return direction
    return "Unknown"


def analyze():
    total = len(SETTLED_MARKETS)
    ups = sum(1 for _, o in SETTLED_MARKETS if o == "yes")
    downs = total - ups

    print("=" * 72)
    print("  BTC SWARM vs V2 ENGINE — PREDICTION ACCURACY COMPARISON")
    print("  Last 50 settled KXBTC15M markets")
    print("=" * 72)

    # ---------------------------------------------------------------
    # 1. BASE RATE
    # ---------------------------------------------------------------
    print(f"\n{'=' * 72}")
    print("  1. BASE RATE (coin-flip benchmark)")
    print(f"{'=' * 72}")
    print(f"  Total markets:   {total}")
    print(f"  Up (yes):        {ups}  ({ups/total*100:.1f}%)")
    print(f"  Down (no):       {downs}  ({downs/total*100:.1f}%)")
    base_rate = max(ups, downs) / total
    print(f"  Always-majority: {base_rate*100:.1f}% (always predict '{('Up' if ups > downs else 'Down')}')")

    # ---------------------------------------------------------------
    # 2. SWARM ACCURACY
    # ---------------------------------------------------------------
    print(f"\n{'=' * 72}")
    print("  2. SWARM CONSENSUS ACCURACY")
    print(f"{'=' * 72}")

    swarm_correct = 0
    swarm_total = 0
    swarm_details = {"Up": {"correct": 0, "total": 0}, "Down": {"correct": 0, "total": 0}}

    # Track by time segment
    segments = {
        "08:15-12:45 (morning)": {"correct": 0, "total": 0, "direction": "Up"},
        "13:00-14:45 (early afternoon)": {"correct": 0, "total": 0, "direction": "Up"},
        "15:00-17:15 (mid afternoon)": {"correct": 0, "total": 0, "direction": "Up"},
        "17:30-18:15 (late afternoon)": {"correct": 0, "total": 0, "direction": "Down"},
        "18:30-20:30 (evening)": {"correct": 0, "total": 0, "direction": "Down"},
    }

    for time_str, outcome in SETTLED_MARKETS:
        pred = get_swarm_prediction(time_str)
        if pred == "Unknown":
            continue
        swarm_total += 1
        actual = "Up" if outcome == "yes" else "Down"
        is_correct = pred == actual
        if is_correct:
            swarm_correct += 1
        swarm_details[pred]["total"] += 1
        if is_correct:
            swarm_details[pred]["correct"] += 1

        # Assign to segment
        t = time_to_minutes(time_str)
        for seg_name, seg_data in segments.items():
            seg_range = seg_name.split("(")[0].strip()
            start_str, end_str = seg_range.split("-")
            if time_to_minutes(start_str) <= t <= time_to_minutes(end_str):
                seg_data["total"] += 1
                if is_correct:
                    seg_data["correct"] += 1
                break

    swarm_wr = swarm_correct / swarm_total if swarm_total else 0

    print(f"  Markets with swarm prediction: {swarm_total}")
    print(f"  Correct:  {swarm_correct}")
    print(f"  Wrong:    {swarm_total - swarm_correct}")
    print(f"  Win Rate: {swarm_wr*100:.1f}%")
    print()
    print("  By predicted direction:")
    for direction, stats in swarm_details.items():
        if stats["total"] > 0:
            wr = stats["correct"] / stats["total"] * 100
            print(f"    {direction}: {stats['correct']}/{stats['total']} = {wr:.1f}%")

    print()
    print("  By time segment:")
    for seg_name, seg_data in segments.items():
        if seg_data["total"] > 0:
            wr = seg_data["correct"] / seg_data["total"] * 100
            print(f"    {seg_name}: {seg_data['correct']}/{seg_data['total']} = {wr:.1f}% (predicted {seg_data['direction']})")

    # ---------------------------------------------------------------
    # 3. V2 ENGINE STATS
    # ---------------------------------------------------------------
    print(f"\n{'=' * 72}")
    print("  3. V2 ENGINE ACCURACY")
    print(f"{'=' * 72}")

    v2_shadow_bets = 89
    v2_shadow_wins = 63
    v2_shadow_losses = 26
    v2_shadow_wr = v2_shadow_wins / v2_shadow_bets

    v2_live_bets = 7
    v2_live_wins = 6
    v2_live_losses = 1
    v2_live_wr = v2_live_wins / v2_live_bets

    print(f"  Shadow tracker (corrupted buffer data):")
    print(f"    Bets: {v2_shadow_bets}  W: {v2_shadow_wins}  L: {v2_shadow_losses}  WR: {v2_shadow_wr*100:.1f}%")
    print(f"    NOTE: This ran on corrupted/stale buffer data pre-wipe")
    print()
    print(f"  Live bets today (post-buffer-wipe):")
    print(f"    Bets: {v2_live_bets}  W: {v2_live_wins}  L: {v2_live_losses}  WR: {v2_live_wr*100:.1f}%")
    print(f"    NOTE: Very small sample size")

    # ---------------------------------------------------------------
    # 4. COMPARISON TABLE
    # ---------------------------------------------------------------
    print(f"\n{'=' * 72}")
    print("  4. HEAD-TO-HEAD COMPARISON")
    print(f"{'=' * 72}")

    row_fmt = "  {:<30s} {:>8s} {:>8s} {:>10s} {:>10s}"
    print(row_fmt.format("Model", "Bets", "W/L", "Win Rate", "vs Base"))
    print("  " + "-" * 68)

    models = [
        ("Always-Down (base rate)", total, downs, total - downs, base_rate),
        ("Swarm Consensus", swarm_total, swarm_correct, swarm_total - swarm_correct, swarm_wr),
        ("V2 Shadow (corrupted)", v2_shadow_bets, v2_shadow_wins, v2_shadow_losses, v2_shadow_wr),
        ("V2 Live (today only)", v2_live_bets, v2_live_wins, v2_live_losses, v2_live_wr),
    ]

    for name, bets, wins, losses, wr in models:
        edge = wr - base_rate
        sign = "+" if edge >= 0 else ""
        print(row_fmt.format(
            name,
            str(bets),
            f"{wins}W/{losses}L",
            f"{wr*100:.1f}%",
            f"{sign}{edge*100:.1f}pp",
        ))

    # ---------------------------------------------------------------
    # 5. PROFITABILITY ANALYSIS
    # ---------------------------------------------------------------
    print(f"\n{'=' * 72}")
    print("  5. PROFITABILITY ESTIMATE (simplified)")
    print(f"{'=' * 72}")

    # Kalshi BTC 15m markets: typical payout ~90c on a 50c bet (after fees)
    # Win: +$0.40 profit, Loss: -$0.50
    # Edge = WR * 0.40 - (1-WR) * 0.50
    win_profit = 0.40
    loss_cost = 0.50

    print(f"  Assumptions: Win +${win_profit:.2f}, Loss -${loss_cost:.2f} per contract")
    print(f"  (typical 50c entry, 90c payout, ~10% fee drag)")
    print()

    for name, bets, wins, losses, wr in models:
        ev_per_bet = wr * win_profit - (1 - wr) * loss_cost
        total_pnl = ev_per_bet * bets
        print(f"  {name}:")
        print(f"    EV/bet: ${ev_per_bet:+.3f}  |  Est PnL over {bets} bets: ${total_pnl:+.2f}")

    # ---------------------------------------------------------------
    # 6. KEY FINDINGS
    # ---------------------------------------------------------------
    print(f"\n{'=' * 72}")
    print("  6. KEY FINDINGS")
    print(f"{'=' * 72}")

    print(f"""
  - Base rate is {base_rate*100:.1f}% (market skews {('Up' if ups > downs else 'Down')}: {downs}/50 windows)
  - Swarm consensus at {swarm_wr*100:.1f}% is {'ABOVE' if swarm_wr > base_rate else 'BELOW'} base rate by {abs(swarm_wr - base_rate)*100:.1f}pp
  - V2 shadow tracker at {v2_shadow_wr*100:.1f}% but data was corrupted (unreliable)
  - V2 live at {v2_live_wr*100:.1f}% but only {v2_live_bets} bets (not statistically significant)

  SWARM WEAKNESS: The swarm updates slowly (holds direction for hours).
  It correctly called the Down trend in late session, but missed intra-period
  reversals. It acts more like a trend filter than a per-window predictor.

  RECOMMENDATION:
  - Swarm alone is NOT sufficient for per-window betting
  - Swarm is useful as a REGIME FILTER (trend direction confirmation)
  - V2 with clean data (post-buffer-wipe) needs more samples to evaluate
  - Best approach: V2 for per-window signals, swarm as a directional gate
    (only bet when V2 and swarm agree on direction)
""")


if __name__ == "__main__":
    analyze()
