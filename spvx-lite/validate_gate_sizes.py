#!/usr/bin/env python3
"""
Validate gate sizes against real-world strait dimensions.
Ensures gates are wide enough to catch all transits.
"""

import json
from pathlib import Path

# Real-world strait widths (approximate)
STRAIT_WIDTHS = {
    "Sicily": {
        "real_width_km": 145,  # Sicily to Tunisia
        "recommended_gate_nm": 80,
        "notes": "Wide strait, main shipping lane ~50-60nm"
    },
    "Canary": {
        "real_width_km": 100,  # Shipping lanes around Canary Islands
        "recommended_gate_nm": 60,
        "notes": "Multiple lanes, need wide coverage"
    },
    "Dardanelles": {
        "real_width_km": 1.2,  # Narrowest point
        "recommended_gate_nm": 10,  # But add buffer for approaches
        "notes": "Very narrow strait, but include approach zones"
    },
    "Otranto": {
        "real_width_km": 72,  # Italy to Albania
        "recommended_gate_nm": 45,
        "notes": "Moderate width, main shipping lane"
    },
    "Bonny": {
        "real_width_km": 30,  # Offshore terminal area
        "recommended_gate_nm": 20,
        "notes": "Terminal approach area"
    },
    # Reference: Existing major straits
    "Hormuz": {
        "real_width_km": 39,
        "recommended_gate_nm": 25,
        "notes": "Narrow, high traffic chokepoint"
    },
    "Malacca": {
        "real_width_km": 2.8,  # Narrowest
        "recommended_gate_nm": 15,  # But wider for traffic lanes
        "notes": "Narrow but with defined traffic separation"
    },
    "Gibraltar": {
        "real_width_km": 14,
        "recommended_gate_nm": 10,
        "notes": "Narrow strait between continents"
    },
}

def check_gate_sizes():
    """Check existing gate configurations."""

    print("🔍 Gate Size Validation")
    print("=" * 80)
    print()

    gates_file = Path("data/geo/gates.geojson")

    if not gates_file.exists():
        print(f"❌ {gates_file} not found")
        return

    with open(gates_file) as f:
        gates_data = json.load(f)

    print("📏 Existing Gates:")
    print("-" * 80)

    for feature in gates_data.get('features', []):
        props = feature.get('properties', {})
        gate_id = props.get('id', 'UNKNOWN')
        name = props.get('name', 'Unknown')
        half_width = props.get('half_width_nm', 0)
        total_width = half_width * 2

        # Estimate coverage in km
        total_width_km = total_width * 1.852

        # Check if this is a known strait
        strait_key = None
        for key in STRAIT_WIDTHS.keys():
            if key.upper() in gate_id.upper():
                strait_key = key
                break

        if strait_key:
            reference = STRAIT_WIDTHS[strait_key]
            real_width = reference['real_width_km']
            recommended = reference['recommended_gate_nm']

            # Calculate coverage percentage
            coverage = (total_width_km / real_width) * 100 if real_width > 0 else 0

            # Status
            if total_width >= recommended:
                status = "✅"
                verdict = "Good"
            elif total_width >= recommended * 0.7:
                status = "⚠️"
                verdict = "Marginal"
            else:
                status = "❌"
                verdict = "Too small!"

            print(f"{status} {gate_id:40s}")
            print(f"   Name: {name}")
            print(f"   Current width: {total_width:.1f} NM ({total_width_km:.1f} km)")
            print(f"   Strait width: {real_width:.1f} km")
            print(f"   Coverage: {coverage:.0f}% of strait")
            print(f"   Recommended: {recommended:.1f} NM")
            print(f"   Verdict: {verdict}")
            if coverage < 70:
                print(f"   ⚠️  Gate may miss ships on the edges!")
                print(f"   💡 Increase to {recommended} NM for better coverage")
            print()
        else:
            # Unknown strait, just show dimensions
            print(f"ℹ️  {gate_id:40s}")
            print(f"   Name: {name}")
            print(f"   Width: {total_width:.1f} NM ({total_width_km:.1f} km)")
            print()

    print("=" * 80)
    print()

    # Recommendations
    print("💡 Gate Sizing Guidelines:")
    print("-" * 80)
    print()
    print("1. **Major Chokepoints** (Hormuz, Malacca, Gibraltar):")
    print("   - Use 15-25 NM to cover main traffic lanes")
    print("   - Don't need to cover entire strait width")
    print()
    print("2. **Wide Straits** (Sicily, Otranto):")
    print("   - Use 40-80 NM to cover primary shipping lanes")
    print("   - Ships don't use full strait width uniformly")
    print()
    print("3. **Offshore Terminals** (Bonny):")
    print("   - Use 15-30 NM to cover approach/departure zones")
    print("   - Include anchorage areas")
    print()
    print("4. **Open Ocean Lanes** (Canary):")
    print("   - Use 50-100 NM for wider coverage")
    print("   - Multiple routes may exist")
    print()
    print("5. **Rule of Thumb**:")
    print("   - half_width_nm = (main_shipping_lane_width / 2) + 5nm buffer")
    print("   - Better slightly too wide than too narrow")
    print("   - Monitor gate_crossings to verify ships are caught")
    print()

    print("🎯 Recommended Gate Widths:")
    print("-" * 80)
    for strait, info in sorted(STRAIT_WIDTHS.items()):
        print(f"   {strait:20s}: {info['recommended_gate_nm']:5.1f} NM  ({info['notes']})")
    print()

if __name__ == "__main__":
    check_gate_sizes()
