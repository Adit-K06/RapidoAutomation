import os
import requests
from models import ChatResponse, LocationResult
from dotenv import load_dotenv

load_dotenv()

GOOGLE_PLACES_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

# In-memory session store
sessions = {}

# Keep Render alive
import threading
import time

def keep_alive():
    while True:
        time.sleep(840)
        try:
            requests.get("https://rapidoautomation.onrender.com/health", timeout=5)
        except:
            pass

threading.Thread(target=keep_alive, daemon=True).start()

# ── Intent parsing (no LLM, pure keyword matching) ──────────────────────────

RIDE_KEYWORDS = {
    "Bike Direct": ["bike", "bike direct", "byke", "byk", "motorbike", "motorcycle"],
    "Scooty Direct": ["scooty", "scooter", "scooti", "scoty"],
    "Auto": ["auto", "autorickshaw", "auto rickshaw", "rick", "tuk"],
}

CONFIRM_KEYWORDS = ["yes", "yeah", "yep", "yup", "correct", "right", "confirm", "ok", "okay", "sure", "book", "proceed", "go ahead", "haan", "ha"]
REJECT_KEYWORDS = ["no", "nope", "wrong", "nahi", "cancel", "stop", "not", "different", "change"]

def extract_ride_type(text: str) -> str | None:
    text = text.lower().strip()
    for ride_type, keywords in RIDE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return ride_type
    return None

def is_confirmation(text: str) -> bool:
    text = text.lower().strip()
    for kw in CONFIRM_KEYWORDS:
        if kw in text:
            return True
    return False

def is_rejection(text: str) -> bool:
    text = text.lower().strip()
    for kw in REJECT_KEYWORDS:
        if kw in text:
            return True
    return False

# ── Google Places search ─────────────────────────────────────────────────────

def search_location(query: str) -> list:
    try:
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        params = {
            "query": f"{query} Bengaluru",
            "key": GOOGLE_PLACES_KEY,
            "region": "in",
            "language": "en",
        }
        response = requests.get(url, params=params, timeout=5)
        data = response.json()

        results = []
        for item in data.get("results", [])[:3]:
            name = item.get("name", "")
            address = item.get("formatted_address", "")
            lat = item["geometry"]["location"]["lat"]
            lng = item["geometry"]["location"]["lng"]
            results.append({
                "name": name,
                "full_address": f"{name}, {address}",
                "lat": lat,
                "lng": lng,
            })
        return results
    except Exception as e:
        return []

# ── Rapido ride coordinates ──────────────────────────────────────────────────

RAPIDO_RIDE_COORDS = {
    "Bike Direct": {"x": 540, "y": 1247},
    "Scooty Direct": {"x": 540, "y": 1450},
    "Auto": {"x": 540, "y": 1822},
}

# ── Session management ───────────────────────────────────────────────────────

def get_session(session_id: str) -> dict:
    if session_id not in sessions:
        sessions[session_id] = {
            "step": "asking_destination",
            "locations": [],
            "selected_location": None,
            "ride_type": None,
        }
    return sessions[session_id]

def clear_session(session_id: str):
    sessions.pop(session_id, None)

# ── Main conversation handler ────────────────────────────────────────────────

def process_message(session_id: str, user_message: str) -> ChatResponse:
    session = get_session(session_id)
    step = session["step"]
    text = user_message.lower().strip()

    # ── Step 1: User says where they want to go ──
    if step == "asking_destination":
        locations = search_location(user_message)

        if not locations:
            return ChatResponse(
                message=f"Sorry, I couldn't find that location in Bengaluru. Please try again.",
                next_step="asking_destination",
            )

        session["locations"] = locations
        session["step"] = "confirming_destination"

        top = locations[0]
        from models import LocationResult
        location_results = [LocationResult(**loc) for loc in locations]

        return ChatResponse(
            message=f"I found {top['name']}. Address: {top['full_address']}. Is this correct?",
            next_step="confirming_destination",
            locations=location_results,
            selected_location=LocationResult(**top),
        )

    # ── Step 2: User confirms or rejects location ──
    elif step == "confirming_destination":
        if is_confirmation(text):
            session["selected_location"] = session["locations"][0]
            session["step"] = "asking_ride_type"
            from models import LocationResult
            return ChatResponse(
                message="Great! Which ride do you want? Say Bike, Scooty, or Auto.",
                next_step="asking_ride_type",
                selected_location=LocationResult(**session["selected_location"]),
            )
        elif is_rejection(text):
            if len(session["locations"]) > 1:
                session["locations"].pop(0)
                top = session["locations"][0]
                from models import LocationResult
                location_results = [LocationResult(**loc) for loc in session["locations"]]
                return ChatResponse(
                    message=f"How about {top['name']}? Address: {top['full_address']}. Is this correct?",
                    next_step="confirming_destination",
                    locations=location_results,
                    selected_location=LocationResult(**top),
                )
            else:
                session["step"] = "asking_destination"
                return ChatResponse(
                    message="No more results. Please say your destination again.",
                    next_step="asking_destination",
                )
        else:
            return ChatResponse(
                message="Please say Yes to confirm or No to try another result.",
                next_step="confirming_destination",
            )

    # ── Step 3: User picks ride type ──
    elif step == "asking_ride_type":
        ride_type = extract_ride_type(text)
        if not ride_type:
            return ChatResponse(
                message="I didn't catch that. Please say Bike, Scooty, or Auto.",
                next_step="asking_ride_type",
            )

        session["ride_type"] = ride_type
        session["step"] = "confirming_booking"
        loc = session["selected_location"]
        from models import LocationResult
        return ChatResponse(
            message=f"Booking {ride_type} to {loc['name']}. Say Yes to confirm or No to cancel.",
            next_step="confirming_booking",
            ride_type=ride_type,
            selected_location=LocationResult(**loc),
        )

    # ── Step 4: Final confirmation ──
    elif step == "confirming_booking":
        if is_confirmation(text):
            coords = RAPIDO_RIDE_COORDS[session["ride_type"]]
            ride = session["ride_type"]
            loc = session["selected_location"]
            clear_session(session_id)
            from models import LocationResult
            return ChatResponse(
                message=f"Booking your {ride} now!",
                next_step="booking",
                ride_type=ride,
                ride_coords=coords,
                ready_to_book=True,
                selected_location=LocationResult(**loc),
            )
        elif is_rejection(text):
            clear_session(session_id)
            return ChatResponse(
                message="Booking cancelled. Tap the mic to start again.",
                next_step="idle",
            )
        else:
            return ChatResponse(
                message="Please say Yes to book or No to cancel.",
                next_step="confirming_booking",
            )

    return ChatResponse(
        message="Something went wrong. Please start again.",
        next_step="idle",
    )