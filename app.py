import os
import json
import re
from datetime import datetime, timedelta, time

import streamlit as st


# ---------------------------------
# Page setup
# ---------------------------------
st.set_page_config(page_title="Travel Planner AI", page_icon="🧭", layout="wide")
st.title("🧭 Travel Planner AI")
st.caption("Create a day-wise itinerary with timeline + plan-based explanations + user customization.")


# ---------------------------------
# Utilities
# ---------------------------------
def parse_csv_list(text: str) -> list[str]:
    items = [x.strip() for x in (text or "").split(",")]
    return [x for x in items if x]


def parse_duration_to_minutes(duration_text: str) -> int:
    """
    Accepts strings like:
      "45 min", "1 hour", "2 hours", "2–3 hours", "2-3 hours", "1.5 hours"
    Returns a reasonable average in minutes.
    """
    s = (duration_text or "").strip().lower()
    s = s.replace("–", "-").replace("—", "-")

    m = re.search(r"(\d+(\.\d+)?)\s*-\s*(\d+(\.\d+)?)\s*(hour|hours|hr|hrs)", s)
    if m:
        a = float(m.group(1))
        b = float(m.group(3))
        avg = (a + b) / 2.0
        return int(round(avg * 60))

    m = re.search(r"(\d+(\.\d+)?)\s*(hour|hours|hr|hrs)", s)
    if m:
        hrs = float(m.group(1))
        return int(round(hrs * 60))

    m = re.search(r"(\d+)\s*(min|mins|minute|minutes)", s)
    if m:
        return int(m.group(1))

    return 90


def fmt_hhmm(dt_obj: datetime) -> str:
    return dt_obj.strftime("%I:%M %p").lstrip("0")


def travel_time_minutes(transport: str) -> int:
    if transport == "Walking":
        return 15
    if transport == "Public Transit":
        return 25
    if transport == "Rideshare/Taxi":
        return 18
    if transport == "Rental Car":
        return 20
    return 20


def safe_list_join(items):
    items = [str(x).strip() for x in (items or []) if str(x).strip()]
    return ", ".join(items) if items else "—"


# ---------------------------------
# Place library (generic building blocks)
# Must-visits (user typed) will override these.
# ---------------------------------
PLACE_LIBRARY = {
    "Food": [
        {
            "name": "Local Breakfast Café",
            "duration": "45–60 min",
            "description": "Start with local flavors and a quick energy boost.",
            "activities": ["Try a local pastry", "Signature coffee/tea", "Light breakfast"],
            "nearby": ["Photo-friendly streets", "Small boutique shops"],
            "food": ["Breakfast set", "Coffee + pastry"],
            "transport": "Walking / short ride",
            "tips": "Arrive early to avoid the morning rush."
        },
        {
            "name": "Local Market / Food Street",
            "duration": "1.5–2 hours",
            "description": "Taste multiple local items in one walkable area.",
            "activities": ["Street-food tasting", "Browse snacks", "Buy souvenirs"],
            "nearby": ["Dessert shops", "Local craft lane"],
            "food": ["Street snacks", "Regional specialty dish"],
            "transport": "Walking / public transit",
            "tips": "Carry cash for small vendors."
        },
        {
            "name": "Signature Dinner Spot",
            "duration": "1.5–2 hours",
            "description": "End the day with a well-known local dinner option.",
            "activities": ["Order the house special", "Try a local drink", "Dessert tasting"],
            "nearby": ["Night walk area", "Rooftop views (if available)"],
            "food": ["Main course", "Dessert"],
            "transport": "Rideshare/Taxi or transit",
            "tips": "Reserve in advance if it’s popular."
        },
    ],
    "Nature": [
        {
            "name": "Main City Park / Scenic Viewpoint",
            "duration": "1.5–2.5 hours",
            "description": "Fresh air, views, and easy walking.",
            "activities": ["Short walk", "Photography", "Relaxing break"],
            "nearby": ["Visitor center", "Lake/river promenade"],
            "food": ["Park-side café", "Quick bites nearby"],
            "transport": "Walking / public transit",
            "tips": "Morning light is best; carry water."
        },
        {
            "name": "Botanical Garden / Nature Trail",
            "duration": "2–3 hours",
            "description": "A calm block that pairs well with a relaxed pace.",
            "activities": ["Garden trail", "Photo stops", "Rest breaks"],
            "nearby": ["Museum area", "Coffee shops"],
            "food": ["Garden café", "Nearby brunch spot"],
            "transport": "Public Transit or rideshare",
            "tips": "Check entry timings; avoid midday heat if applicable."
        },
    ],
    "History": [
        {
            "name": "Historic Old Town Walk",
            "duration": "2–3 hours",
            "description": "Heritage streets, architecture, and local culture.",
            "activities": ["Walking tour", "Architecture photos", "Small museum visit"],
            "nearby": ["Local market", "Historic monument"],
            "food": ["Traditional lunch spot", "Bakery"],
            "transport": "Walking",
            "tips": "Wear comfortable shoes."
        },
        {
            "name": "Main Museum / Cultural Center",
            "duration": "2–3 hours",
            "description": "Understand local history and context.",
            "activities": ["Top exhibits", "Audio guide", "Gift shop quick stop"],
            "nearby": ["City square", "Historic site"],
            "food": ["Museum café", "Nearby restaurant strip"],
            "transport": "Public Transit / rideshare",
            "tips": "Go early for fewer crowds."
        },
    ],
    "Shopping": [
        {
            "name": "Local Bazaar / Artisan Street",
            "duration": "1.5–2.5 hours",
            "description": "Shop unique crafts and local items.",
            "activities": ["Browse crafts", "Compare prices", "Pick souvenirs"],
            "nearby": ["Street-food lane", "Photo alleys"],
            "food": ["Snacks nearby", "Dessert stall"],
            "transport": "Walking / transit",
            "tips": "Carry a tote bag; bargain politely."
        }
    ],
    "Nightlife": [
        {
            "name": "Evening Walk + Night Market",
            "duration": "1.5–2.5 hours",
            "description": "Lights, snacks, and local vibe for the evening.",
            "activities": ["Night photos", "Snack tasting", "People watching"],
            "nearby": ["Dessert spots", "Live music area"],
            "food": ["Night snacks", "Dessert"],
            "transport": "Walking / rideshare",
            "tips": "Check closing times and keep valuables secure."
        }
    ],
    "Adventure": [
        {
            "name": "Active Experience Block",
            "duration": "2–3 hours",
            "description": "A higher-energy activity for memorable moments.",
            "activities": ["Guided activity", "Safety briefing", "Photos/videos"],
            "nearby": ["Scenic stop", "Quick café"],
            "food": ["Energy snack", "Post-activity meal"],
            "transport": "Rideshare/Taxi / rental car",
            "tips": "Confirm reservations; wear comfortable gear."
        }
    ],
    "Relax": [
        {
            "name": "Spa / Slow Café + Park Time",
            "duration": "2–3 hours",
            "description": "A slower block for recovery and calm vibes.",
            "activities": ["Massage/spa (optional)", "Slow café time", "Park sit-down"],
            "nearby": ["Bookstore", "Tea shop"],
            "food": ["Light meal", "Tea/coffee"],
            "transport": "Walking / short ride",
            "tips": "Book spa slots ahead on weekends."
        }
    ],
}


def pick_places(interests, num_stops, used_names: set[str], avoid_lower: set[str]):
    picks = []
    pools = []
    for it in interests:
        pools.extend(PLACE_LIBRARY.get(it, []))

    if not pools:
        for v in PLACE_LIBRARY.values():
            pools.extend(v)

    for p in pools:
        if len(picks) >= num_stops:
            break
        if p["name"] in used_names:
            continue
        if p["name"].lower() in avoid_lower:
            continue
        picks.append(p)
        used_names.add(p["name"])

    if len(picks) < num_stops:
        all_places = []
        for v in PLACE_LIBRARY.values():
            all_places.extend(v)
        for p in all_places:
            if len(picks) >= num_stops:
                break
            if p["name"] in used_names:
                continue
            if p["name"].lower() in avoid_lower:
                continue
            picks.append(p)
            used_names.add(p["name"])

    return picks, used_names


def generate_plan_explanation(day_num: int, city: str, slot: dict, transport: str, pace: str) -> str:
    """
    Explanation derived from plan data (place + duration + activities + nearby + timing).
    """
    p = slot["place"]
    start = slot["start"]
    end = slot["end"]
    name = p.get("name", "Place")
    duration = p.get("duration", "—")

    acts = p.get("activities", [])
    nearby = p.get("nearby", [])
    food = p.get("food", [])
    tips = p.get("tips", "")
    travel_next = slot.get("estimated_travel_to_next_min", 0)

    parts = []
    parts.append(f"**{start}–{end} | {name}** — planned for about **{duration}** in **{city}** (Day {day_num}).")

    if acts:
        parts.append(f"Main focus: {safe_list_join(acts)}.")

    if nearby:
        parts.append(f"Nearby options to pair: {safe_list_join(nearby)}.")

    if food:
        parts.append(f"Food around this stop: {safe_list_join(food)}.")

    if pace == "Packed":
        parts.append("Because your pace is **Packed**, this stop is kept efficient to fit more in the day.")
    elif pace == "Relaxed":
        parts.append("Because your pace is **Relaxed**, you have buffer time here for breaks and a slower walkthrough.")
    else:
        parts.append("With a **Balanced** pace, this block keeps the day structured but flexible.")

    parts.append(f"Transport: **{transport}**.")

    if travel_next and travel_next > 0:
        parts.append(f"Next travel estimate: ~**{travel_next} min**.")

    if tips:
        parts.append(f"Tip: {tips}")

    return " ".join(parts)


def build_detailed_itinerary(
    city: str,
    start_date: datetime.date,
    end_date: datetime.date,
    start_time: time,
    day_end_time: time,
    budget: str,
    pace: str,
    interests: list[str],
    transport: str,
    notes: str,
    stay_area: str,
    stay_type: str,
    must_visit: list[str],
    avoid: list[str],
    food_pref: list[str]
) -> dict:
    days = max(1, (end_date - start_date).days + 1)
    avoid_lower = {a.strip().lower() for a in avoid if a.strip()}

    used_names = set()
    itinerary_days = []

    travel_gap = travel_time_minutes(transport)

    # Stops per day based on pace
    if pace == "Relaxed":
        stops_per_day = 2
    elif pace == "Packed":
        stops_per_day = 4
    else:
        stops_per_day = 3

    must_idx = 0

    for i in range(days):
        day_date = start_date + timedelta(days=i)
        day_date_label = day_date.strftime("%a, %b %d")

        day_start_dt = datetime.combine(day_date, start_time if i == 0 else start_time)
        day_end_dt = datetime.combine(day_date, day_end_time)

        # Build places list: must-visit first
        places = []
        while must_idx < len(must_visit) and len(places) < stops_per_day:
            mv = must_visit[must_idx]
            must_idx += 1

            if mv.lower() in avoid_lower:
                continue

            places.append({
                "name": mv,
                "duration": "2 hours",
                "description": "User-selected must-visit place.",
                "activities": ["Explore key highlights", "Photos", "Spend time based on your interest"],
                "nearby": ["Look for nearby cafés", "Walkable spots around"],
                "food": ["Nearby local option"],
                "transport": transport,
                "tips": "Check opening hours and tickets; adjust time based on crowd."
            })
            used_names.add(mv)

        # Fill remaining with library picks
        if len(places) < stops_per_day:
            picks, used_names = pick_places(interests, stops_per_day - len(places), used_names, avoid_lower)
            places.extend(picks)

        # Build timeline within daily bounds
        timeline = []
        cursor = day_start_dt

        # Start from stay location (if provided)
        if stay_area.strip():
            stay_block_end = cursor + timedelta(minutes=10)
            timeline.append({
                "start": fmt_hhmm(cursor),
                "end": fmt_hhmm(stay_block_end),
                "place": {
                    "name": f"Start from your stay: {stay_area} ({stay_type})",
                    "duration": "10 min",
                    "description": "Starting point based on your accommodation.",
                    "activities": ["Quick prep", "Grab essentials", "Head out"],
                    "nearby": [],
                    "food": [],
                    "transport": transport,
                    "tips": "Carry water, power bank, and ID."
                },
                "estimated_travel_to_next_min": travel_gap
            })
            cursor = stay_block_end + timedelta(minutes=travel_gap)

        for idx, place in enumerate(places):
            dur_min = parse_duration_to_minutes(place.get("duration", "90 min"))
            end_dt = cursor + timedelta(minutes=dur_min)

            # Respect daily end time
            if end_dt > day_end_dt:
                break

            timeline.append({
                "start": fmt_hhmm(cursor),
                "end": fmt_hhmm(end_dt),
                "place": place,
                "estimated_travel_to_next_min": travel_gap if idx < len(places) - 1 else 0
            })

            cursor = end_dt + timedelta(minutes=travel_gap)

        itinerary_days.append({
            "day": i + 1,
            "date": day_date_label,
            "timeline": timeline
        })

    summary = {
        "City": city,
        "Start Date": str(start_date),
        "End Date": str(end_date),
        "Days": days,
        "Budget": budget,
        "Pace": pace,
        "Interests": interests if interests else ["Any"],
        "Transport": transport,
        "Stay Area": stay_area or "—",
        "Stay Type": stay_type,
        "Must-visit": must_visit or ["—"],
        "Avoid": avoid or ["—"],
        "Food Preference": food_pref or ["—"],
        "Notes": notes or "—"
    }

    return {"summary": summary, "days": itinerary_days}


# ---------------------------------
# Optional AI: rewrite day narrative (no new info)
# ---------------------------------
def ai_rewrite_day_narrative(plan_day: dict, summary: dict) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        payload = {
            "city": summary.get("City"),
            "pace": summary.get("Pace"),
            "transport": summary.get("Transport"),
            "day": plan_day.get("day"),
            "date": plan_day.get("date"),
            "timeline": [
                {
                    "start": t["start"],
                    "end": t["end"],
                    "name": t["place"].get("name"),
                    "duration": t["place"].get("duration"),
                    "activities": t["place"].get("activities", []),
                    "nearby": t["place"].get("nearby", []),
                    "food": t["place"].get("food", []),
                    "tips": t["place"].get("tips", "")
                }
                for t in plan_day.get("timeline", [])
            ]
        }

        system = (
            "Rewrite the provided structured travel plan into a friendly paragraph. "
            "CRITICAL: Do NOT add new places, activities, or facts not present in the input JSON. "
            "Only connect and rephrase what is already in the plan. Return plain text only."
        )

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload)}
            ],
            temperature=0.4
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None


# ---------------------------------
# Session state migration/cleanup (prevents old tuple formats breaking the new app)
# ---------------------------------
if "latest_plan" not in st.session_state:
    st.session_state.latest_plan = None

lp = st.session_state.latest_plan
if isinstance(lp, tuple) and len(lp) == 2 and isinstance(lp[1], dict):
    # old format like ("rule", {"summary":..., "days":...})
    st.session_state.latest_plan = lp[1]
elif lp is not None and not isinstance(lp, dict):
    st.session_state.latest_plan = None


# ---------------------------------
# Sidebar UI (customized)
# ---------------------------------
with st.sidebar:
    st.header("Trip inputs")

    city = st.text_input("Destination city", placeholder="e.g., Denver, Tokyo, Paris")

    colA, colB = st.columns(2)
    with colA:
        start_date = st.date_input("Start date")
        start_time_val = st.time_input("Start time", value=time(9, 0))
    with colB:
        end_date = st.date_input("End date", value=start_date + timedelta(days=3))
        day_end_time_val = st.time_input("Daily end time", value=time(20, 0))

    trip_days = max(1, (end_date - start_date).days + 1)
    st.caption(f"Trip length: **{trip_days} day(s)**")

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

    st.subheader("Stay details")
    stay_area = st.text_input("Where will you stay? (area/neighborhood/hotel)", placeholder="e.g., Downtown / Shinjuku / near Union Station")
    stay_type = st.selectbox("Stay type", ["Hotel", "Airbnb", "Hostel", "With friends/family", "Not decided"], index=0)

    st.subheader("Customization")
    must_visit_text = st.text_area("Must-visit places (comma-separated)", placeholder="e.g., Red Rocks, Meow Wolf, Union Station")
    avoid_text = st.text_area("Avoid places (comma-separated)", placeholder="e.g., bars, steep hikes, museums")

    food_pref = st.multiselect(
        "Food preference (optional)",
        ["Vegetarian", "Vegan", "Halal", "Kosher", "No preference", "Spicy lover", "Seafood"],
        default=["No preference"]
    )

    notes = st.text_area("Extra notes (optional)", placeholder="Kids? Accessibility? Must-see places?")

    use_ai_rewrite = st.toggle("AI rewrite day narrative (requires OPENAI_API_KEY)", value=False)

    generate = st.button("✨ Generate itinerary", type="primary", use_container_width=True)


# ---------------------------------
# Generate
# ---------------------------------
if generate:
    if not city.strip():
        st.error("Please enter a destination city.")
    else:
        must_visit = parse_csv_list(must_visit_text)
        avoid = parse_csv_list(avoid_text)

        plan = build_detailed_itinerary(
            city=city.strip(),
            start_date=start_date,
            end_date=end_date,
            start_time=start_time_val,
            day_end_time=day_end_time_val,
            budget=budget,
            pace=pace,
            interests=interests,
            transport=transport,
            notes=notes.strip(),
            stay_area=stay_area.strip(),
            stay_type=stay_type,
            must_visit=must_visit,
            avoid=avoid,
            food_pref=food_pref,
        )

        st.session_state.latest_plan = plan
        st.rerun()


# ---------------------------------
# Render
# ---------------------------------
st.divider()
st.subheader("🗓️ Your Itinerary (Plan + Timeline + Explanations)")

if st.session_state.latest_plan is None:
    st.info("Fill the trip inputs on the left and click **Generate itinerary**.")
else:
    data = st.session_state.latest_plan
    if not isinstance(data, dict) or "summary" not in data or "days" not in data:
        st.error("Stored itinerary data is invalid (likely from an older app version). Please click **Generate itinerary** again.")
        st.session_state.latest_plan = None
        st.stop()

    summary = data["summary"]

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
    for day in data["days"]:
        with st.expander(f"Day {day['day']} — {day['date']}", expanded=(day["day"] == 1)):

            # Optional AI rewrite for the whole day (still plan-based)
            if use_ai_rewrite:
                rewritten = ai_rewrite_day_narrative(day, summary)
                if rewritten:
                    st.markdown("#### 🤖 AI Day Narrative (based strictly on your plan)")
                    st.write(rewritten)
                    st.divider()
                else:
                    st.info("AI rewrite is ON, but OPENAI_API_KEY is missing or request failed. Showing plan-based explanations below.")
                    st.divider()

            for slot in day.get("timeline", []):
                p = slot.get("place", {})

                st.markdown(f"## 📍 {slot.get('start','—')} – {slot.get('end','—')} | {p.get('name','—')}")
                st.write(f"⏱️ **Time Required:** {p.get('duration','—')}")
                st.write(f"🚶 **Transport:** {summary.get('Transport','—')}")
                st.write(f"🍽️ **Food Nearby:** {safe_list_join(p.get('food', []))}")

                st.markdown("### 🧠 Explanation (generated from plan data)")
                expl = generate_plan_explanation(
                    day_num=day.get("day", 1),
                    city=summary.get("City", "—"),
                    slot=slot,
                    transport=summary.get("Transport", "—"),
                    pace=summary.get("Pace", "Balanced")
                )
                st.write(expl)

                st.markdown("### 🎯 What you can do here (from plan)")
                for a in p.get("activities", []):
                    st.write(f"- {a}")

                st.markdown("### 📌 Nearby places you can pair (from plan)")
                for n in p.get("nearby", []):
                    st.write(f"- {n}")

                st.markdown("### 💡 Tip (from plan)")
                st.write(p.get("tips", "—"))

                if slot.get("estimated_travel_to_next_min", 0) > 0:
                    st.caption(f"Next stop travel estimate: ~{slot['estimated_travel_to_next_min']} minutes")

                st.divider()
