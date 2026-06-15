import os
import requests
import threading
import time
from models import ChatResponse, LocationResult
from dotenv import load_dotenv

load_dotenv()

GOOGLE_PLACES_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

sessions = {}

def keep_alive():
    while True:
        time.sleep(840)
        try:
            requests.get("https://rapidoautomation.onrender.com/health", timeout=5)
        except:
            pass

threading.Thread(target=keep_alive, daemon=True).start()

RIDE_KEYWORDS = {
    "Bike Direct": ["bike", "bike direct", "byke", "byk", "motorbike", "motorcycle"],
    "Scooty Direct": ["scooty", "scooter", "scooti", "scoty"],
    "Auto": ["auto", "autorickshaw", "auto rickshaw", "rick", "tuk"],
}

CONFIRM_KEYWORDS = [
    "yes", "yeah", "yep", "yup", "correct", "right", "confirm",
    "ok", "okay", "sure", "book", "proceed", "go ahead", "haan", "ha",
]

REJECT_KEYWORDS = [
    "no", "nope", "wrong", "nahi", "cancel", "stop", "not", "different",
    "change", "none", "cancel the ride", "stop the ride", "don't book",
    "do not book", "abort", "quit", "exit", "nevermind", "never mind",
    "forget it", "leave it", "band kar", "mat karo",
]

def extract_ride_type(text: str):
    text = text.lower().strip()
    for ride_type, keywords in RIDE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return ride_type
    return None

def is_confirmation(text: str) -> bool:
    text = text.lower().strip()
    if is_rejection(text):
        return False
    return any(kw in text for kw in CONFIRM_KEYWORDS)

def is_rejection(text: str) -> bool:
    text = text.lower().strip()
    return any(kw in text for kw in REJECT_KEYWORDS)

def shorten_address(full_address: str) -> str:
    parts = [p.strip() for p in full_address.split(",")]
    if len(parts) > 3:
        return ", ".join(parts[1:3])
    elif len(parts) > 1:
        return ", ".join(parts[:2])
    return full_address

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
            short = shorten_address(address)
            lat = item["geometry"]["location"]["lat"]
            lng = item["geometry"]["location"]["lng"]
            results.append({
                "name": name,
                "full_address": address,
                "short_address": short,
                "lat": lat,
                "lng": lng,
            })
        return results
    except:
        return []

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

def process_message(session_id: str, user_message: str) -> ChatResponse:
    session = get_session(session_id)
    step = session["step"]
    text = user_message.lower().strip()

    # Global cancel — works at any step
    if is_rejection(text) and step != "asking_destination":
        clear_session(session_id)
        return ChatResponse(
            message="Booking cancelled. Tap the mic to start again.",
            next_step="idle",
        )

    if step == "asking_destination":
        locations = search_location(user_message)
        if not locations:
            return ChatResponse(
                message="Sorry, I couldn't find that in Bengaluru. Please try again.",
                next_step="asking_destination",
            )

        session["locations"] = locations
        session["step"] = "confirming_destination"
        top = locations[0]
        location_results = [LocationResult(**loc) for loc in locations]

        return ChatResponse(
            message=f"I found {top['name']} in {top['short_address']}. Is this correct?",
            next_step="confirming_destination",
            locations=location_results,
            selected_location=LocationResult(**top),
        )

    elif step == "confirming_destination":
        if is_confirmation(text):
            session["selected_location"] = session["locations"][0]
            session["step"] = "asking_ride_type"
            loc = session["selected_location"]
            return ChatResponse(
                message="Great! Opening Rapido to check live fares.",
                next_step="asking_ride_type",
                selected_location=LocationResult(**loc),
            )
        else:
            if len(session["locations"]) > 1:
                session["locations"].pop(0)
                top = session["locations"][0]
                location_results = [LocationResult(**loc) for loc in session["locations"]]
                return ChatResponse(
                    message=f"How about {top['name']} in {top['short_address']}? Is this correct?",
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

    elif step == "asking_ride_type":
        ride_type = extract_ride_type(text)
        if not ride_type:
            return ChatResponse(
                message="I didn't catch that. Please say Bike, Scooty, or Auto. Or say Cancel to stop.",
                next_step="asking_ride_type",
            )
        session["ride_type"] = ride_type
        session["step"] = "confirming_booking"
        loc = session["selected_location"]
        return ChatResponse(
            message=f"Booking {ride_type} to {loc['name']}. Say Yes to confirm or No to cancel.",
            next_step="confirming_booking",
            ride_type=ride_type,
            selected_location=LocationResult(**loc),
        )

    elif step == "confirming_booking":
        if is_confirmation(text):
            ride = session["ride_type"]
            loc = session["selected_location"]
            clear_session(session_id)
            return ChatResponse(
                message=f"Booking your {ride} now!",
                next_step="booking",
                ride_type=ride,
                ready_to_book=True,
                selected_location=LocationResult(**loc),
            )
        else:
            clear_session(session_id)
            return ChatResponse(
                message="Booking cancelled. Tap the mic to start again.",
                next_step="idle",
            )

    return ChatResponse(
        message="Something went wrong. Please start again.",
        next_step="idle",
    )