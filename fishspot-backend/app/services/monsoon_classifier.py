"""
Monsoon classification service for oceanographic features.
Classifies geographical locations and months into monsoon categories.
"""
from typing import Dict


def classify_monsoon(lat: float, lon: float, month: int) -> Dict[str, int]:
    """
    Classify monsoon pattern based on location and month.

    Priority order mirrors the training-data preprocessing script
    (assign_monsoon_world), so inference labels exactly match training labels:

      1. Indian Ocean / Arabian Sea / Bay of Bengal : 30°S–30°N, 20°E–120°E
      2. Maritime Continent / SE Asia               : 15°S–20°N, 90°E–150°E
      3. Western North Pacific / East Asian         : 20°N–45°N, 110°E–150°E  → No_monsoon_region
      4. Northern Australia                         : 25°S–0°,   110°E–155°E  → No_monsoon_region
      5. Everything else                            : No_monsoon_region

    EAS and AUS regions exist in the preprocessing logic but are not OHE
    categories in the trained model, so they fall through to No_monsoon_region.

    Args:
        lat:   Latitude  in degrees  (-90 … +90)
        lon:   Longitude in degrees  (-180 … +180, or 0 … 360)
        month: Month (1–12)

    Returns:
        Dictionary with one-hot encoded monsoon features.
    """
    # Normalize longitude from 0–360 to –180–180 (matches training script)
    if lon > 180.0:
        lon = lon - 360.0

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
        'No_monsoon_region': 0,
    }

    # ------------------------------------------------------------------
    # 1. Indian Ocean / Arabian Sea / Bay of Bengal
    #    Box: 30°S–30°N, 20°E–120°E   (matches training script exactly)
    #    Dec–Feb  → IO_NE_monsoon
    #    Mar–Apr  → IO_First_Intermonsoon
    #    May–Sep  → IO_SW_monsoon
    #    Oct–Nov  → IO_Second_Intermonsoon
    # ------------------------------------------------------------------
    if -30.0 <= lat <= 30.0 and 20.0 <= lon <= 120.0:
        if month in (12, 1, 2):
            monsoon_features['IO_NE_monsoon'] = 1
        elif month in (3, 4):
            monsoon_features['IO_First_Intermonsoon'] = 1
        elif month in (5, 6, 7, 8, 9):
            monsoon_features['IO_SW_monsoon'] = 1
        elif month in (10, 11):
            monsoon_features['IO_Second_Intermonsoon'] = 1
        else:
            monsoon_features['No_monsoon_region'] = 1
        return monsoon_features

    # ------------------------------------------------------------------
    # 2. Maritime Continent / SE Asia
    #    Box: 15°S–20°N, 90°E–150°E
    #    Nov–Mar  → MC_NW_monsoon
    #    Apr–May  → MC_Transition_1
    #    Jun–Sep  → MC_SE_monsoon
    #    Oct      → MC_Transition_2
    # ------------------------------------------------------------------
    if -15.0 <= lat <= 20.0 and 90.0 <= lon <= 150.0:
        if month in (11, 12, 1, 2, 3):
            monsoon_features['MC_NW_monsoon'] = 1
        elif month in (4, 5):
            monsoon_features['MC_Transition_1'] = 1
        elif month in (6, 7, 8, 9):
            monsoon_features['MC_SE_monsoon'] = 1
        elif month == 10:
            monsoon_features['MC_Transition_2'] = 1
        else:
            monsoon_features['No_monsoon_region'] = 1
        return monsoon_features

    # ------------------------------------------------------------------
    # 3. Western North Pacific / East Asian monsoon
    #    Box: 20°N–45°N, 110°E–150°E
    #    (not an OHE category in the trained model → No_monsoon_region)
    # ------------------------------------------------------------------
    if 20.0 <= lat <= 45.0 and 110.0 <= lon <= 150.0:
        monsoon_features['No_monsoon_region'] = 1
        return monsoon_features

    # ------------------------------------------------------------------
    # 4. Northern Australia monsoon
    #    Box: 25°S–0°, 110°E–155°E
    #    (not an OHE category in the trained model → No_monsoon_region)
    # ------------------------------------------------------------------
    if -25.0 <= lat <= 0.0 and 110.0 <= lon <= 155.0:
        monsoon_features['No_monsoon_region'] = 1
        return monsoon_features

    # Default: outside all monsoon boxes
    monsoon_features['No_monsoon_region'] = 1
    return monsoon_features


def get_monsoon_name(lat: float, lon: float, month: int) -> str:
    """Get the human-readable monsoon name for a location and month."""
    features = classify_monsoon(lat, lon, month)
    for key, value in features.items():
        if value == 1:
            return key
    return "Unknown"
