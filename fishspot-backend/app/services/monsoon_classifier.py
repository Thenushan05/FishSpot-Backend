"""
Monsoon classification service for oceanographic features.
Classifies geographical locations and months into monsoon categories.
"""
from typing import Dict


def classify_monsoon(lat: float, lon: float, month: int) -> Dict[str, int]:
    """
    Classify monsoon pattern based on location and month.
    
    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        month: Month (1-12)
    
    Returns:
        Dictionary with one-hot encoded monsoon features
    """
    # Initialize all monsoon features to 0
    monsoon_features = {
        'IO_NE_monsoon': 0,
        'IO_SW_monsoon': 0,
        'IO_First_Intermonsoon': 0,
        'IO_Second_Intermonsoon': 0,
        'MC_NW_monsoon': 0,
        'MC_SE_monsoon': 0,
        'MC_Transition_1': 0,
        'MC_Transition_2': 0,
        'No_monsoon_region': 0
    }
    
    # Check if location is outside monsoon regions (far north or far south)
    if abs(lat) > 35:
        monsoon_features['No_monsoon_region'] = 1
        return monsoon_features
    
    # Indian Ocean Region (10°S to 30°S)
    if -30 <= lat <= -10:
        if month in [11, 12, 1, 2, 3]:
            monsoon_features['IO_NE_monsoon'] = 1
        elif month in [5, 6, 7, 8, 9]:
            monsoon_features['IO_SW_monsoon'] = 1
        elif month in [3, 4, 5]:
            monsoon_features['IO_First_Intermonsoon'] = 1
        elif month in [10, 11]:
            monsoon_features['IO_Second_Intermonsoon'] = 1
        return monsoon_features
    
    # Maritime Continent Region (10°S to 10°N, 95°E to 140°E)
    if -10 <= lat <= 10 and 95 <= lon <= 140:
        if month in [12, 1, 2]:
            monsoon_features['MC_NW_monsoon'] = 1
        elif month in [6, 7, 8, 9]:
            monsoon_features['MC_SE_monsoon'] = 1
        elif month in [3, 4, 5]:
            monsoon_features['MC_Transition_1'] = 1
        elif month in [10, 11]:
            monsoon_features['MC_Transition_2'] = 1
        return monsoon_features
    
    # Indian Ocean transitions for areas between 10°S and equator
    if -10 <= lat <= 0:
        if month in [11, 12, 1, 2, 3]:
            monsoon_features['IO_NE_monsoon'] = 1
        elif month in [5, 6, 7, 8, 9]:
            monsoon_features['IO_SW_monsoon'] = 1
        elif month in [3, 4, 5]:
            monsoon_features['IO_First_Intermonsoon'] = 1
        elif month in [10, 11]:
            monsoon_features['IO_Second_Intermonsoon'] = 1
        return monsoon_features
    
    # Northern Indian Ocean / Bay of Bengal region (0°N to 30°N)
    if 0 <= lat <= 30:
        if month in [11, 12, 1, 2, 3]:
            monsoon_features['IO_NE_monsoon'] = 1
        elif month in [5, 6, 7, 8, 9]:
            monsoon_features['IO_SW_monsoon'] = 1
        elif month in [3, 4, 5]:
            monsoon_features['IO_First_Intermonsoon'] = 1
        elif month in [10, 11]:
            monsoon_features['IO_Second_Intermonsoon'] = 1
        return monsoon_features
    
    # Default to no monsoon region for unclassified areas
    monsoon_features['No_monsoon_region'] = 1
    return monsoon_features


def get_monsoon_name(lat: float, lon: float, month: int) -> str:
    """Get the human-readable monsoon name for a location and month."""
    features = classify_monsoon(lat, lon, month)
    for key, value in features.items():
        if value == 1:
            return key
    return "Unknown"
