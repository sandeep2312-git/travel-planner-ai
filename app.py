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
st.caption("Generates a day-wise plan + timeline + plan-based explanations (not generic).")


# ---------------------------------
# Utilities
# ---------------------------------
def parse_duration_to_minutes(duration_text: str) -> int:
    """
    Accepts strings like: "45 min", "1 hour", "2 hours", "2–3 hours", "1.5 hours"
    Returns a reasonable average in minutes.
    """
    s = duration_text.strip().lower()
    s = s.replace("–", "-").replace("—", "-")
    # Extract ranges like "2-3 hours"
    m = re.search(r"(\d+(\.\d+)?)\s*-\s*(\d+(\.\d+)?)\s*(hour|hours|hr|hrs)", s)
    if m:
        a = float(m.group(1))
        b = float(m.group(3))
        avg = (a + b) / 2
        return int(round(avg * 60))

    # Single "x hours"
    m = re.search(r"(\d+(\.\d+)?)\s*(hour|hours|hr|hrs)", s)
    if m:
        hrs = float(m.group(1))
        return int(round(hrs * 60))

    # Minutes
    m = re.search(r"(\d+)\s*(min|mins|minute|minutes)", s)
    if m:
        return int(m.group(1))

    # fallback
    return 90


def fmt_hhmm(dt_obj: datetime) -> str:
    return dt_obj.strftime("%I:%M %p").lstrip("0")


def build_time_blocks(pace: str):
    """
    Defines the skeleton of the day schedule.
    We'll create 3-5 stops depending on pace.
    """
    if pace == "Relaxed":
        return ["Late Morning", "Afternoon", "Evening"]
    if pace == "Packed":
        return ["Early Morning", "Late Morning", "Afternoon", "Evening", "Late Night"]
    return ["Morning", "Afternoon", "Evening"]


def start_time_for_pace(pace: str) -> time:
    if pace == "Packed":
        return time(8, 30)
    if pace == "Relaxed":
        return time(10, 0)
    return time(9, 0)


def travel_time_minutes(transport: str) -> int:
    """
    Simple heuristic travel time between stops.
    """
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
    items = [x for x in items if str(x).strip()]
    return ", ".join(items) if items else "—"


# ---------------------------------
# Place library (semi-structured building blocks)
# The *explanation* is NOT generic; it is generated from the chosen plan data.
# ---------------------------------
PLACE_LIBRARY = {
    "Food": [
        {
            "name": "Local Breakfast Café",
            "duration": "45–60 min",
            "description": "A strong start to the day with local flavors and quick energy.",
            "activities": ["Try a local pastry", "Order a signature coffee/tea", "Light breakfast"],
            "nearby": ["Walkable streets for photos", "Small boutique shops"],
            "food": ["Breakfast set", "Coffee + pastry"],
            "transport": "Walking / short ride",
            "tips": "Arrive early to avoid the morning rush."
        },
        {
            "name": "Local Market / Food Street",
            "duration": "1.5–2 hours",
            "description": "Best place to taste multiple local items in one area.",
            "activities": ["Street-food tasting", "Browse local snacks", "Buy small souvenirs"],
            "nearby": ["Dessert shops", "Local craft lane"],
            "food": ["Street snacks", "Regional specialty dish"],
            "transport": "Walking / public transit",
            "tips": "Carry cash for smaller vendors; go hungry!"
        },
        {
            "name": "Signature Dinner Spot",
            "duration": "1.5–2 hours",
            "description": "A memorable end to your day with the city’s popular cuisine.",
            "activities": ["Order house special", "Try a local drink", "Dessert tasting"],
            "nearby": ["Night walk area", "Rooftop views (if available)"],
            "food": ["Main course", "Dessert"],
            "transport": "Rideshare/Taxi or transit",
            "tips": "Reserve in advance if it’s a famous place."
        },
    ],
    "Nature": [
        {
            "name": "Main City Park / Scenic Viewpoint",
            "duration": "1.5–2.5 hours",
            "description": "Good for fresh air, views, and easy walking without heavy planning.",
            "activities": ["Short hike/walk", "Photography", "Relaxing break"],
            "nearby": ["Visitor center", "Lake/river promenade"],
            "food": ["Park-side café", "Quick bites nearby"],
            "transport": "Walking / public transit",
            "tips": "Morning light is best; carry water."
        },
        {
            "name": "Botanical Garden / Nature Trail",
            "duration": "2–3 hours",
            "description": "A slower, calming block that pairs well with a relaxed pace.",
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
            "description": "Heritage streets, architecture, and local culture in one walkable zone.",
            "activities": ["Walking tour", "Architecture photos", "Small museum visit"],
            "nearby": ["Local market", "Cathedral/temple/church (if applicable)"],
            "food": ["Traditional lunch spot", "Bakery"],
            "transport": "Walking",
            "tips": "Comfortable shoes; keep an eye out for local guided tours."
        },
        {
            "name": "Main Museum / Cultural Center",
            "duration": "2–3 hours",
            "description": "A focused block to understand local history and context.",
            "activities": ["Top exhibits", "Audio guide", "Gift shop quick stop"],
            "nearby": ["City square", "Historic monument"],
            "food": ["Museum café", "Nearby restaurant strip"],
            "transport": "Public Transit / rideshare",
            "tips": "Go right when it opens for a quieter experience."
        },
    ],
    "Shopping": [
        {
            "name": "Local Bazaar / Artisan Street",
            "duration": "1.5–2.5 hours",
            "description": "Best place to find unique local crafts and gifts.",
            "activities": ["Browse crafts", "Bargain politely", "Pick souvenirs"],
            "nearby": ["Street-food lane", "Photo-friendly alleys"],
            "food": ["Snacks nearby", "Dessert stall"],
            "transport": "Walking / transit",
            "tips": "Carry a tote bag; compare prices before buying."
        }
    ],
    "Nightlife": [
        {
            "name": "Evening Walk + Viewpoint / Night Market",
            "duration": "1.5–2.5 hours",
            "description": "A lively end to the day with lights, snacks, and local vibe.",
            "activities": ["Night photos", "Snack tasting", "People watching"],
            "nearby": ["Dessert spots", "Live music area"],
            "food": ["Night snacks", "Dessert"],
            "transport": "Walking / rideshare",
            "tips": "Keep valuables secure; check closing times."
        }
    ],
    "Adventure": [
        {
            "name": "Active Experience Block",
            "duration": "2–3 hours",
            "description": "A higher-energy activity to make the trip memorable.",
            "activities": ["Guided activity", "Safety briefing", "Photo/video moments"],
            "nearby": ["Scenic stop", "Quick café"],
            "food": ["Energy snack", "Post-activity meal"],
            "transport": "Rideshare/Taxi / rental car",
            "tips": "Wear comfortable gear; confirm reservations."
        }
    ],
    "Relax": [
        {
            "name": "Spa / Slow Café + Park Time",
            "duration": "2–3 hours",
            "description": "A slower block for recovery and a calm vibe.",
            "activities": ["Massage/spa (optional)", "Slow café time", "Park sit-down"],
            "nearby": ["Bookstore", "Tea shop"],
            "food": ["Light meal", "Tea/coffee"],
            "transport": "Walking / short ride",
            "tips": "Book spa slots ahead on weekends."
        }
    ],
}


def pick_places(interests, num_stops, used_names):
    """
    Select places from the library based on interests, avoiding duplicates by name.
    """
    picks = []
    pools = []
    for it in interests:
        pools.extend(PLACE_LIBRARY.get(it, []))

    # If user selected nothing, pull from all
    if not pools:
        for v in PLACE_LIBRARY.values():
            pools.extend(v)

    for p in pools:
        if len(picks) >= num_stops:
            break
        if p["name"] in used_names:
            continue
        picks.append(p)
        used_names.add(p["name"])

    # Fill if short
    if len(picks) < num_stops:
        all_places = []
        for v in PLACE_LIBRARY.values():
            all_places.extend(v)
        for p in all_places:
            if len(picks) >= num_stops:
                break
            if p["name"] in used_names:
                continue
            picks.append(p)
            used_names.add(p["name"])

    return picks, used_names


def build_detailed_itinerary(city, start_date_str, days, budget, pace, interests, transport, notes):
    used_names = set()
    dt = datetime.strptime(start_date_str, "%Y-%m-%d")

    day_blocks = build_time_blocks(pace)
    # number of "places" per day equals blocks count minus 1 meal anchor sometimes
    # We'll do 3 stops for balanced, 4 for packed, 2-3 for relaxed
    if pace == "Relaxed":
        stops_per_day = 2
    elif pace == "Packed":
        stops_per_day = 4
    else:
        stops_per_day = 3

    itinerary_days = []
    for i in range(days):
        day_date_label = (dt + timedelta(days=i)).strftime("%a, %b %d")

        places, used_names = pick_places(interests, stops_per_day, used_names)

        # Build timeline
        start_dt = datetime.combine(dt.date() + timedelta(days=i), start_time_for_pace(pace))
        travel_gap = travel_time_minutes(transport)

        timeline = []
        cursor = start_dt

        for idx, place in enumerate(places):
            dur_min = parse_duration_to_minutes(place["duration"])
            end = cursor + timedelta(minutes=dur_min)

            timeline.append({
                "start": fmt_hhmm(cursor),
                "end": fmt_hhmm(end),
                "place": place,
                "estimated_travel_to_next_min": (travel_gap if idx < len(places) - 1 else 0)
            })

            cursor = end
            if idx < len(places) - 1:
                cursor = cursor + timedelta(minutes=travel_gap)

        itinerary_days.append({
            "day": i + 1,
            "date": day_date_label,
            "timeline": timeline
        })

    summary = {
        "City": city,
        "Start Date": start_date_str,
        "Days": days,
        "Budget": budget,
        "Pace": pace,
        "Interests": interests if interests else ["Any"],
        "Transport": transport,
        "Notes": notes or "—"
    }

    return {"summary": summary, "days": itinerary_days}


def generate_plan_explanation(day_num: int, city: str, slot: dict, transport: str, pace: str) -> str:
    """
    NON-GENERIC narrative built from the actual plan data.
    (Still "general" in tone, but it never describes things that aren't in the plan.)
    """
    p = slot["place"]
    start = slot["start"]
    end = slot["end"]
    name = p["name"]
    duration = p["duration"]

    acts = p.get("activities", [])
    nearby = p.get("nearby", [])
    food = p.get("food", [])
    tips = p.get("tips", "")
    travel_next = slot.get("estimated_travel_to_next_min", 0)

    # Build a message strictly from plan fields
    lines = []
    lines.append(
        f"**{start}–{end} | {name}** — planned for about **{duration}** in **{city}**."
    )

    if acts:
        lines.append(f"You’ll focus on: {safe_list_join(acts)}.")

    if nearby and nearby != ["—"]:
        lines.append(f"If you still have time, nearby options you can pair with this stop: {safe_list_join(nearby)}.")

    if food and food != ["—"]:
        lines.append(f"Food idea around here: {safe_list_join(food)}.")

    # Explain order/pace/transport using only user selections + computed travel
    if pace == "Packed":
        lines.append("Since your pace is **Packed**, this stop is kept tight so you can fit more into the day.")
    elif pace == "Relaxed":
        lines.append("Since your pace is **Relaxed**, you have buffer time here for breaks and a slower walkthrough.")
    else:
        lines.append("With a **Balanced** pace, this block keeps the day structured but flexible.")

    lines.append(f"Transport note: you chose **{transport}** for getting around.")

    if travel_next and travel_next > 0:
        lines.append(f"Next move: plan ~**{travel_next} min** to reach the next stop.")

    if tips:
        lines.append(f"Local tip from your plan: {tips}")

    return " ".join(lines)


# ---------------------------------
# Optional AI: rewrite plan-based narratives (no new places)
# ---------------------------------
def ai_rewrite_day_narrative(plan_day: dict, city: str, transport: str, pace: str) -> str | None:
    """
    If OPENAI_API_KEY exists, returns a single narrative paragraph for the day.
    Must not add new places/activities beyond what's in plan_day.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        # Provide ONLY the plan data; instruct not to invent.
        payload = {
            "city": city,
            "pace": pace,
            "transport": transport,
            "day": plan_day["day"],
            "date": plan_day["date"],
            "timeline": [
                {
                    "start": t["start"],
                    "end": t["end"],
                    "name": t["place"]["name"],
                    "duration": t["place"]["duration"],
                    "activities": t["place"].get("activities", []),
                    "nearby": t["place"].get("nearby", []),
                    "food": t["place"].get("food", []),
                    "tips": t["place"].get("tips", "")
                }
                for t in plan_day["timeline"]
            ]
        }

        system = (
            "You rewrite structured travel plans into a friendly paragraph. "
            "CRITICAL: Do NOT add new places, new activities, or facts not present in the input JSON. "
            "Only rephrase and connect what's already there. Return plain text only."
        )

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload)}
            ],
            temperature=0.4
        )
        text = resp.choices[0].message.content.strip()
        return text
    except Exception:
        return None


# ---------------------------------
# UI
# ---------------------------------
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

    use_ai_rewrite = st.toggle("AI rewrite day narrative (requires OPENAI_API_KEY)", value=False)

    generate = st.button("✨ Generate itinerary", type="primary", use_container_width=True)


if "latest_plan" not in st.session_state:
    st.session_state.latest_plan = None


if generate:
    if not city.strip():
        st.error("Please enter a destination city.")
    else:
        plan = build_detailed_itinerary(
            city=city.strip(),
            start_date_str=str(start_date),
            days=int(days),
            budget=budget,
            pace=pace,
            interests=interests,
            transport=transport,
            notes=notes.strip()
        )
        st.session_state.latest_plan = plan
        st.rerun()


st.divider()
st.subheader("🗓️ Your Itinerary (Plan + Timeline + Plan-Based Explanations)")

if st.session_state.latest_plan is None:
    st.info("Fill the trip inputs on the left and click **Generate itinerary**.")
else:
    data = st.session_state.latest_plan
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

            # Optional AI rewrite for the whole day (still plan-based, no new info)
            if use_ai_rewrite:
                rewritten = ai_rewrite_day_narrative(day, summary["City"], summary["Transport"], summary["Pace"])
                if rewritten:
                    st.markdown("#### 🤖 AI Day Narrative (based strictly on your plan)")
                    st.write(rewritten)
                    st.divider()
                else:
                    st.info("AI rewrite is ON, but OPENAI_API_KEY is missing or request failed. Showing plan-based explanations below.")
                    st.divider()

            for slot in day["timeline"]:
                p = slot["place"]

                # Header with timeline
                st.markdown(f"## 📍 {slot['start']} – {slot['end']} | {p['name']}")
                st.write(f"⏱️ **Time Required:** {p['duration']}")
                st.write(f"🚶 **Transport:** {summary['Transport']}")
                st.write(f"🍽️ **Food Nearby:** {safe_list_join(p.get('food', []))}")

                # The key part you asked for:
                st.markdown("### 🧠 Explanation (generated from plan data)")
                expl = generate_plan_explanation(
                    day_num=day["day"],
                    city=summary["City"],
                    slot=slot,
                    transport=summary["Transport"],
                    pace=summary["Pace"]
                )
                st.write(expl)

                # Details that are also plan-derived
                st.markdown("### 🎯 What you can do here (from plan)")
                for a in p.get("activities", []):
                    st.write(f"- {a}")

                st.markdown("### 📌 Nearby places you can pair (from plan)")
                for n in p.get("nearby", []):
                    st.write(f"- {n}")

                st.markdown("### 💡 Tip (from plan)")
                st.write(p.get("tips", "—"))

                # Travel time to next
                if slot.get("estimated_travel_to_next_min", 0) > 0:
                    st.caption(f"Next stop travel estimate: ~{slot['estimated_travel_to_next_min']} minutes")

                st.divider()
