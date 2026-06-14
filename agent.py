from google import genai
from tools import search_location, get_ride_coords
from models import ChatResponse, LocationResult
from dotenv import load_dotenv
import os

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

sessions = {}

def get_session(session_id: str) -> dict:
    if session_id not in sessions:
        sessions[session_id] = {
            "step": "asking_destination",
            "destination": None,
            "locations": [],
            "selected_location": None,
            "ride_type": None,
        }
    return sessions[session_id]

def clear_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]

def ask_gemini(system: str, user: str) -> str:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"{system}\n\nUser: {user}",
    )
    return response.text.strip()

def extract_destination(user_message: str) -> str:
    return ask_gemini(
        """You extract destination names from natural speech for a ride booking app in Bengaluru.
Extract only the destination name/place. Return ONLY the place name, nothing else.
Examples:
- "take me to NMIT" → "NMIT"
- "I want to go to Koramangala 5th block" → "Koramangala 5th block"
- "drop me at Hebbal flyover" → "Hebbal flyover"
- "college" → "Dayananda Sagar College of Engineering"
- "home" → "Nobel Residency Phase 2 Tejaswini Nagar Bengaluru" """,
        user_message,
    )

def extract_ride_type(user_message: str) -> str:
    return ask_gemini(
        """You extract ride type from natural speech for Rapido booking.
Return ONLY one of these exact values: "Bike Direct", "Scooty Direct", "Auto"
Examples:
- "bike" → "Bike Direct"
- "scooty" → "Scooty Direct"
- "auto" → "Auto"
- "I'll take the bike" → "Bike Direct"
- "get me an auto" → "Auto" """,
        user_message,
    )

def is_confirmation(user_message: str) -> bool:
    result = ask_gemini(
        "Return only 'yes' or 'no' based on whether the user is confirming. Any positive response = yes.",
        user_message,
    )
    return result.lower().startswith("yes")

def process_message(session_id: str, user_message: str) -> ChatResponse:
    session = get_session(session_id)
    step = session["step"]

    if step == "asking_destination":
        destination = extract_destination(user_message)
        locations = search_location(destination)

        if not locations:
            return ChatResponse(
                message=f"Sorry, I couldn't find '{destination}' in Bengaluru. Please try again.",
                next_step="asking_destination",
            )

        session["destination"] = destination
        session["locations"] = locations
        session["step"] = "confirming_destination"

        top = locations[0]
        location_results = [LocationResult(**loc) for loc in locations]

        return ChatResponse(
            message=f"I found: {top['full_address']}. Is this correct?",
            next_step="confirming_destination",
            locations=location_results,
            selected_location=LocationResult(**top),
        )

    elif step == "confirming_destination":
        confirmed = is_confirmation(user_message)

        if confirmed:
            session["selected_location"] = session["locations"][0]
            session["step"] = "asking_ride_type"
            return ChatResponse(
                message="Great! Which ride type do you want? Say Bike, Scooty, or Auto.",
                next_step="asking_ride_type",
                selected_location=LocationResult(**session["selected_location"]),
            )
        else:
            if len(session["locations"]) > 1:
                session["locations"].pop(0)
                top = session["locations"][0]
                location_results = [LocationResult(**loc) for loc in session["locations"]]
                return ChatResponse(
                    message=f"How about: {top['full_address']}. Is this correct?",
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
        ride_type = extract_ride_type(user_message)
        session["ride_type"] = ride_type
        session["step"] = "confirming_booking"

        loc = session["selected_location"]
        return ChatResponse(
            message=f"Booking {ride_type} to {loc['full_address']}. Say Yes to confirm or No to cancel.",
            next_step="confirming_booking",
            ride_type=ride_type,
            selected_location=LocationResult(**loc),
        )

    elif step == "confirming_booking":
        confirmed = is_confirmation(user_message)

        if confirmed:
            coords = get_ride_coords(session["ride_type"])
            ride = session["ride_type"]
            clear_session(session_id)
            return ChatResponse(
                message="Booking your ride now!",
                next_step="booking",
                ride_type=ride,
                ride_coords=coords,
                ready_to_book=True,
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