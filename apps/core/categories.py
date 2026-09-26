"""
The fixed set of place categories. One source of truth for the database
choices, the Gemini extraction schema, the geocoder's OSM-tag mapping, and
the mobile app (served at /api/v1/categories/).
"""

CATEGORIES = [
    # key, label, description (used in the Gemini prompt)
    ('food', 'Food', 'Restaurants, street food, bakeries, food markets'),
    ('cafe', 'Café', 'Coffee shops, tea houses, dessert spots'),
    ('bar', 'Bars & Nightlife', 'Bars, pubs, breweries, wineries, clubs'),
    ('nature', 'Nature', 'Parks, gardens, lakes, waterfalls, mountains, trails'),
    ('beach', 'Beach', 'Beaches, coves, coastal spots'),
    ('viewpoint', 'Viewpoint', 'Lookouts, rooftops, scenic spots'),
    ('landmark', 'Landmark', 'Monuments, historic sites, famous buildings, bridges, temples'),
    ('culture', 'Culture', 'Museums, galleries, theatres, libraries'),
    ('shopping', 'Shopping', 'Shops, malls, markets, boutiques'),
    ('stay', 'Stay', 'Hotels, hostels, resorts, campsites'),
    ('activity', 'Activity', 'Theme parks, zoos, sports, tours, experiences'),
    ('other', 'Other', 'Anything that does not fit the other categories'),
]

CATEGORY_KEYS = [key for key, _, _ in CATEGORIES]
CATEGORY_CHOICES = [(key, label) for key, label, _ in CATEGORIES]
DEFAULT_CATEGORY = 'other'


def normalize_category(value) -> str:
    """Map free text (older clients, model output) onto a known category key."""
    if not value:
        return DEFAULT_CATEGORY
    value = str(value).strip().lower()
    if value in CATEGORY_KEYS:
        return value
    for key, label, _ in CATEGORIES:
        if value == label.lower():
            return key
    return DEFAULT_CATEGORY


# OpenStreetMap tag -> category, used to suggest a category for geocoder
# results. Checked as (key, value) first, then (key, '*').
OSM_TAG_CATEGORIES = {
    ('amenity', 'restaurant'): 'food',
    ('amenity', 'fast_food'): 'food',
    ('amenity', 'food_court'): 'food',
    ('amenity', 'ice_cream'): 'cafe',
    ('amenity', 'cafe'): 'cafe',
    ('shop', 'bakery'): 'food',
    ('shop', 'coffee'): 'cafe',
    ('amenity', 'bar'): 'bar',
    ('amenity', 'pub'): 'bar',
    ('amenity', 'biergarten'): 'bar',
    ('amenity', 'nightclub'): 'bar',
    ('craft', 'brewery'): 'bar',
    ('craft', 'winery'): 'bar',
    ('natural', 'beach'): 'beach',
    ('leisure', 'beach_resort'): 'beach',
    ('natural', '*'): 'nature',
    ('leisure', 'park'): 'nature',
    ('leisure', 'garden'): 'nature',
    ('leisure', 'nature_reserve'): 'nature',
    ('boundary', 'national_park'): 'nature',
    ('waterway', 'waterfall'): 'nature',
    ('tourism', 'viewpoint'): 'viewpoint',
    ('tourism', 'museum'): 'culture',
    ('tourism', 'gallery'): 'culture',
    ('tourism', 'artwork'): 'culture',
    ('amenity', 'theatre'): 'culture',
    ('amenity', 'arts_centre'): 'culture',
    ('amenity', 'library'): 'culture',
    ('amenity', 'place_of_worship'): 'landmark',
    ('tourism', 'attraction'): 'landmark',
    ('historic', '*'): 'landmark',
    ('man_made', 'tower'): 'landmark',
    ('man_made', 'lighthouse'): 'landmark',
    ('man_made', 'bridge'): 'landmark',
    ('bridge', '*'): 'landmark',
    ('place', 'square'): 'landmark',
    ('place', 'island'): 'nature',
    ('place', 'islet'): 'nature',
    ('shop', '*'): 'shopping',
    ('amenity', 'marketplace'): 'shopping',
    ('tourism', 'hotel'): 'stay',
    ('tourism', 'hostel'): 'stay',
    ('tourism', 'guest_house'): 'stay',
    ('tourism', 'motel'): 'stay',
    ('tourism', 'apartment'): 'stay',
    ('tourism', 'camp_site'): 'stay',
    ('tourism', 'theme_park'): 'activity',
    ('tourism', 'zoo'): 'activity',
    ('tourism', 'aquarium'): 'activity',
    ('leisure', 'stadium'): 'activity',
    ('leisure', 'sports_centre'): 'activity',
    ('leisure', 'water_park'): 'activity',
}


def category_for_osm_tag(osm_key, osm_value, name: str = '') -> str:
    category = (
        OSM_TAG_CATEGORIES.get((osm_key, osm_value))
        or OSM_TAG_CATEGORIES.get((osm_key, '*'))
    )
    if category:
        return category
    # Famous bridges are mapped as the road that crosses them
    # (highway=motorway for the Golden Gate Bridge).
    if osm_key == 'highway' and name.lower().endswith(' bridge'):
        return 'landmark'
    return DEFAULT_CATEGORY
