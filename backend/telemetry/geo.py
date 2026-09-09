"""Geospatial helpers: great-circle distance without GIS infrastructure."""

import math


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two (lat, lon) points.

    The haversine formula assumes a spherical earth; over the short distances a
    vehicle geofence cares about (hundreds of meters to a few kilometers) the
    error versus a proper ellipsoid (WGS-84, ~0.3% flattening) is well inside
    the radius slack the demo uses, which is why the added GIS machinery of
    PostGIS is not justified here.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * math.asin(min(1.0, math.sqrt(a))) * 6_371_000.0


def is_within_radius_m(lat1, lon1, lat2, lon2, radius_m) -> bool:
    return haversine_distance_m(lat1, lon1, lat2, lon2) <= float(radius_m)
