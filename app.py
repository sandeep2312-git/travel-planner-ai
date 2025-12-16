import os
import json
from datetime import datetime, timedelta

import streamlit as st


# ----------------------------
# Page setup
# ----------------------------
st.set_page_config(page_title="Travel Planner AI", page_icon="🧭", layout="wide")
st.title("🧭 Travel Planner AI")
st.caption("Build a trip plan from your preferences. Works with or without an AI API key.")


# ----------------------------
# Helpers (No-API planner)
# ----------------------------
ACTIVITY_POOLS = {
    "Food": [
        "street-food crawl", "local market visit", "signature dish tasting",
        "coffee & dessert hop", "cooking class"
    ],
    "Nature": [
        "sunrise viewpoint", "lake/river walk", "easy hike", "botanical garden",
        "scenic drive"
    ],
    "History": [
        "old town walking tour", "museum visit", "heritage site exploration",
        "local cultural performance", "architecture walk"
    ],
    "Shopping": [
        "local artisan bazaar", "souvenir street", "mall + local brands",
        "thrift/vintage browsing", "handicraft district"
    ],
    "Nightlife": [
        "rooftop lounge", "live music venue", "night market", "bar-hopping area",
        "late-night dessert spot"
    ],
    "Adventure": [
        "kayaking/boating", "zipline/rope course", "ATV/quad experience",
        "paragliding viewpoint", "bike tour"
    ],
    "Relax": [
        "spa / massage", "slow café morning", "park picnic", "sunset promenade",
        "bookstore + chill"
    ],
}

MEAL_SUGGESTIONS = [
    "Breakfast: local café + signature pastry",
    "Lunch: regional specialty restaurant",
    "Dinner: highly rated spot near your area (reserve if possible)",
]

def chunk_day(day_idx: int, pace: str):
    if pace == "Relaxed":
        return ["Late Morning", "Afternoon", "Evening"]
    if pace == "Packed":
        return ["Early Morning", "Late Morning", "Afternoon", "Evening", "Late Night"]
    return ["Morning", "Afternoon", "Evening"]

def pick_activities(interests, slots_needed, used=set()):
    picks = []
    pools = []
    for it in interests:
        pools.extend(ACTIVITY_POOLS.get(it, []))
    if not pools:
        pools = sum(ACTIVITY_POOLS.values(), [])

    for a in pools:
        if len(picks) >= slots_needed:
            break
        if a in used:
            continue
        picks.append(a)
        used.add(a)
    # If still short, fill from any pool
    if len(picks) < slots_needed:
        for a in sum(ACTIVITY_POOLS.values(), []):
            if len(picks) >= slots_needed:
                break
            if a in used:
                continue
            picks.append(a)
            used.add(a)
    return picks, used

def build_rule_based_itinerary(city, start_date, days, budget, pace, interests, transport, notes):
    used = set()
    plan = []
    dt = datetime.strptime(start_date, "%Y-%m-%d")

    budget_tip = {
        "Low": "Focus on public transit, free attractions, markets, and street food.",
        "Medium": "Mix paid attractions + 1 special experience. Use transit + occasional rideshare.",
        "High": "Prioritize top experiences, private tours, and premium dining (book ahead).",
    }[budget]

    transport_tip = {
        "Public Transit": "Buy a transit day-pass if available; plan attractions by neighborhoods.",
        "Rideshare/Taxi": "Batch stops to reduce rides; avoid peak hours if possible.",
        "Walking": "Stay central; plan one neighborhood per day.",
        "Rental Car": "Great for day-trips; confirm parking rules and tolls.",
    }[transport]

    for i in range(days):
        day_date = (dt + timedelta(days=i)).strftime("%a, %b %d")
        slots = chunk_day(i, pace)
        # meals included as anchor points
        slots_needed = max(2, len(slots) - 1)

        acts, used = pick_activities(interests, slots_needed, used)

        day_blocks = []
        act_idx = 0
        for s in slots:
            if "Morning" in s or "Early" in s or "Late Morning" in s:
                day_blocks.append((s, MEAL_SUGGESTIONS[0]))
            elif "Afternoon" in s:
                if act_idx < len(acts):
                    day_blocks.append((s, f"Activity: {acts[act_idx].title()}"))
                    act_idx += 1
                else:
                    day_blocks.append((s, "Activity: Explore a nearby neighborhood + photos"))
            elif "Evening" in s:
                day_blocks.append((s, MEAL_SUGGESTIONS[2]))
            else:
                if act_idx < len(acts):
                    day_blocks.append((s, f"Optional: {acts[act_idx].title()}"))
                    act_idx += 1
                else:
                    day_blocks.append((s, "Optional: Night walk / dessert / views"))

        plan.append({
            "day": i + 1,
            "date": day_date,
            "blocks": day_blocks
        })

    summary = {
        "City": city,
        "Start Date": start_date,
        "Days": days,
        "Budget style": budget,
        "Pace": pace,
        "Interests": ", ".join(interests) if interests else "Any",
        "Transport tip": transport_tip,
        "Budget tip": budget_tip,
        "Notes": notes or "—"
    }

    return summary, plan


# ----------------------------
# Optional: OpenAI mode
# ----------------------------
def try_openai_itinerary(payload: dict) -> dict | None:
    """
    Uses OpenAI if OPENAI_API_KEY exists.
    Returns structured JSON with keys: summary, days (list).
    If anything fails, return None and fall back to rule-based.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        system = (
            "You are a travel planning assistant. Generate a realistic itinerary. "
            "Return ONLY valid JSON with keys: summary (object) and days (array). "
            "Each day item: day_number, date_label, schedule (array of {time_block, plan}). "
            "No markdown, no extra text."
        )

        user = {
            "task": "Create a travel itinerary",
            "inputs": payload
        }

        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)}
            ],
            temperature=0.7,
        )

        content = resp.choices[0].message.content
        data = json.loads(content)
        if not isinstance(data, dict) or "summary" not in data or "days" not in data:
            return None
        return data
    except Exception:
        return None


# ----------------------------
# UI
# ----------------------------
with st.sidebar:
    st.header("Trip inputs")

    city = st.text_input("Destination city", placeholder="e.g., Denver, Tokyo, Paris")
    start_date = st.date_input("Start date")
    days = st.slider("Number of days", 1, 14, 4)

    budget = st.selectbox("Budget", ["Low", "Medium", "High"], index=1)
    pace = st.selectbox("Pace", ["Relaxed", "Balanced", "Packed"], index=1)

    interests = st.multiselect(
        "Interests",
        ["Food", "Nature", "History", "Shopping", "Nightlife", "Adventure", "Relax"],
        default=["Food", "Nature", "History"]
    )

    transport = st.selectbox(
        "Preferred transport",
        ["Public Transit", "Walking", "Rideshare/Taxi", "Rental Car"],
        index=0
    )

    notes = st.text_area("Extra notes (optional)", placeholder="Kids? Accessibility? Must-see places?")

    use_ai = st.toggle("Use AI (requires OPENAI_API_KEY in Streamlit Secrets)", value=False)

    generate = st.button("✨ Generate itinerary", type="primary", use_container_width=True)


if "chat" not in st.session_state:
    st.session_state.chat = [{"role": "assistant", "content": "Tell me your destination + dates, and I’ll plan your trip!"}]

if "latest_plan" not in st.session_state:
    st.session_state.latest_plan = None

# Chat display
st.subheader("💬 Planner Chat")
for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        st.write(m["content"])

# Generate itinerary action
if generate:
    if not city.strip():
        st.error("Please enter a destination city.")
    else:
        payload = {
            "city": city.strip(),
            "start_date": str(start_date),
            "days": int(days),
            "budget": budget,
            "pace": pace,
            "interests": interests,
            "transport": transport,
            "notes": notes.strip(),
        }

        st.session_state.chat.append({"role": "user", "content": f"Plan my trip to {city} for {days} day(s) starting {start_date}."})

        # Try AI first (if toggle on), else rule-based
        ai_data = try_openai_itinerary(payload) if use_ai else None

        if ai_data:
            st.session_state.latest_plan = ("ai", ai_data)
            st.session_state.chat.append({"role": "assistant", "content": "Done! I generated an AI itinerary below."})
        else:
            summary, plan = build_rule_based_itinerary(**payload)
            st.session_state.latest_plan = ("rule", {"summary": summary, "days": plan})
            msg = "Done! I generated an itinerary (no-API mode). Turn on AI + add OPENAI_API_KEY for smarter plans."
            st.session_state.chat.append({"role": "assistant", "content": msg})

        st.rerun()

# Render itinerary
st.divider()
st.subheader("🗓️ Your Itinerary")

if st.session_state.latest_plan is None:
    st.info("Fill the trip inputs on the left and click **Generate itinerary**.")
else:
    mode, data = st.session_state.latest_plan
    summary = data.get("summary", {})

    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("### Trip Summary")
        st.json(summary)
    with col2:
        st.markdown("### Export")
        export_json = json.dumps(data, indent=2)
        st.download_button(
            "⬇️ Download itinerary JSON",
            export_json,
            file_name="itinerary.json",
            mime="application/json",
            use_container_width=True
        )

    st.markdown("### Daily Plan")
    days_data = data.get("days", [])

    # AI format vs rule-based format normalization
    for d in days_data:
        if mode == "rule":
            title = f"Day {d['day']} — {d['date']}"
            with st.expander(title, expanded=(d["day"] == 1)):
                for t, p in d["blocks"]:
                    st.write(f"**{t}:** {p}")
        else:
            title = f"Day {d.get('day_number')} — {d.get('date_label')}"
            with st.expander(title, expanded=(d.get("day_number") == 1)):
                for item in d.get("schedule", []):
                    st.write(f"**{item.get('time_block')}:** {item.get('plan')}")
