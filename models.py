from pydantic import BaseModel
from typing import Optional, List

class ChatRequest(BaseModel):
    session_id: str
    user_message: str
    step: str

class LocationResult(BaseModel):
    name: str
    full_address: str
    lat: float
    lng: float

class ChatResponse(BaseModel):
    message: str
    next_step: str
    locations: Optional[List[LocationResult]] = None
    selected_location: Optional[LocationResult] = None
    ride_type: Optional[str] = None
    ride_coords: Optional[dict] = None
    ready_to_book: bool = False