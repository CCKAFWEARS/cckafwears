"""
Delivery distance + fee calculation.

Uses free OpenStreetMap (Nominatim) geocoding to turn a typed address into
coordinates, then Haversine distance from the shop, then a simple
per-km fee formula (base fee + fee per km) - the same shape Jumia and
similar sites show customers at checkout.

No paid API key needed. If geocoding fails (bad address, no internet,
Nominatim rate limit), we fall back to an average-distance estimate so
checkout never breaks - the admin can always correct the final fee
manually on the order.
"""

import math

FALLBACK_DISTANCE_KM = 12.0  # used only if geocoding fails


def geocode_address(address: str):
    """Return (lat, lng) or None if it can't be resolved."""
    try:
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent="cckafwears-app", timeout=6)
        # Bias the search toward Ghana for better accuracy
        location = geolocator.geocode(f"{address}, Ghana")
        if location:
            return (location.latitude, location.longitude)
    except Exception:
        pass
    return None


def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def calculate_delivery(address: str, shop_lat: float, shop_lng: float,
                        base_fee: float, fee_per_km: float):
    """
    Returns a dict: { lat, lng, distance_km, fee, estimated }
    'estimated' is True when we couldn't geocode and used the fallback distance.
    """
    coords = geocode_address(address)
    if coords:
        lat, lng = coords
        distance_km = haversine_km(shop_lat, shop_lng, lat, lng)
        estimated = False
    else:
        lat, lng = None, None
        distance_km = FALLBACK_DISTANCE_KM
        estimated = True

    fee = round(base_fee + fee_per_km * distance_km, 2)
    return {
        "lat": lat,
        "lng": lng,
        "distance_km": round(distance_km, 2),
        "fee": fee,
        "estimated": estimated,
    }
