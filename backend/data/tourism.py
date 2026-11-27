"""TripGraph sample data: South India tourism.

Single source of truth. neo4j/02_sample_data.cypher is generated from this file
(python tools/generate_cypher.py).

* Destinations and attractions are real places. Coordinates are approximate.
* Route distances, travel times and costs are rounded, illustrative estimates, not timetable data.
* Hotels and tourists are fictional. Tourist visits are generated with a fixed seed so the data is
  identical on every machine and recommendation results are reproducible.
"""
import random

SCENARIO = (
    "TripGraph is a travel-recommendation service for South India. It stores tourists, destinations, "
    "attractions, hotels and the road, rail and air routes between destinations as a graph. Tourists "
    "discover destinations and routes, find alternative paths, and receive personalised recommendations "
    "based on their interests, their past visits and the visits of similar travellers."
)

MODEL = {
    "nodes": [
        {"label": "Tourist", "key": "touristId", "properties": ["touristId", "name", "age", "budget (budget/mid/luxury)", "travelStyle"],
         "why": "The user who receives recommendations."},
        {"label": "Destination", "key": "name", "properties": ["name", "state", "lat", "lon", "bestMonths (list)", "description"],
         "why": "A town or city. Routes connect destinations, so route finding is graph traversal."},
        {"label": "Attraction", "key": "attractionId", "properties": ["attractionId", "name", "rating", "entryFeeInr", "visitHours"],
         "why": "Places to see. Visits to attractions are the evidence for collaborative filtering."},
        {"label": "Category", "key": "name", "properties": ["name"],
         "why": "Shared tags (Beach, Temple, Wildlife...). Interests and attractions meet at the same node."},
        {"label": "Hotel", "key": "hotelId", "properties": ["hotelId", "name", "stars", "pricePerNight", "priceBand", "rating", "amenities (list)"],
         "why": "Where tourists stay; filtered by the tourist's budget."},
    ],
    "relationships": [
        {"type": "ROUTE", "from": "Destination", "to": "Destination", "properties": ["mode (road/rail/flight)", "distanceKm", "hours", "costInr"],
         "why": "Travel link, stored once and used in both directions. Parallel ROUTEs exist for different modes."},
        {"type": "LOCATED_IN", "from": "Attraction / Hotel", "to": "Destination", "properties": [], "why": "Places belong to a destination."},
        {"type": "HAS_CATEGORY", "from": "Attraction", "to": "Category", "properties": [], "why": "An attraction can have several categories."},
        {"type": "INTERESTED_IN", "from": "Tourist", "to": "Category", "properties": ["weight (1-3)"], "why": "Explicit preferences for content-based recommendations."},
        {"type": "VISITED", "from": "Tourist", "to": "Attraction", "properties": ["date", "rating (1-5)"], "why": "Behaviour: used for collaborative filtering and evaluation."},
        {"type": "STAYED_AT", "from": "Tourist", "to": "Hotel", "properties": ["date", "nights", "rating"], "why": "Hotel experience of similar tourists."},
        {"type": "LIVES_IN", "from": "Tourist", "to": "Destination", "properties": [], "why": "Starting point for travel-time scoring."},
        {"type": "WISHLISTED", "from": "Tourist", "to": "Destination", "properties": ["added"], "why": "Stated future plans."},
    ],
}

CATEGORIES = ["Beach", "Temple", "Heritage", "Museum", "Nature", "Wildlife", "Waterfall",
              "Backwaters", "Plantation", "Adventure", "Spiritual", "Hill Station"]

# name, state, lat, lon, best months, description
DESTINATIONS = [
    ("Chennai", "Tamil Nadu", 13.08, 80.27, [11, 12, 1, 2], "Coastal capital of Tamil Nadu."),
    ("Mahabalipuram", "Tamil Nadu", 12.62, 80.19, [11, 12, 1, 2], "Pallava rock-cut monuments by the sea."),
    ("Puducherry", "Puducherry", 11.94, 79.81, [10, 11, 12, 1, 2, 3], "French-era town on the Bay of Bengal."),
    ("Kanchipuram", "Tamil Nadu", 12.83, 79.70, [11, 12, 1, 2], "City of a thousand temples and silk."),
    ("Tirupati", "Andhra Pradesh", 13.63, 79.42, [9, 10, 11, 12, 1, 2], "Gateway to the Tirumala hill shrine."),
    ("Thanjavur", "Tamil Nadu", 10.79, 79.14, [10, 11, 12, 1, 2, 3], "Chola capital, home of the Big Temple."),
    ("Tiruchirappalli", "Tamil Nadu", 10.79, 78.70, [10, 11, 12, 1, 2, 3], "River-island temples and the Rockfort."),
    ("Madurai", "Tamil Nadu", 9.93, 78.12, [10, 11, 12, 1, 2, 3], "Temple city on the Vaigai."),
    ("Rameswaram", "Tamil Nadu", 9.29, 79.31, [10, 11, 12, 1, 2, 3], "Island pilgrimage town."),
    ("Kanyakumari", "Tamil Nadu", 8.09, 77.54, [10, 11, 12, 1, 2, 3], "Southern tip of the Indian mainland."),
    ("Coimbatore", "Tamil Nadu", 11.02, 76.96, [10, 11, 12, 1, 2, 3], "Gateway to the Nilgiris."),
    ("Ooty", "Tamil Nadu", 11.41, 76.70, [3, 4, 5, 6, 10, 11], "Hill station in the Nilgiris."),
    ("Kodaikanal", "Tamil Nadu", 10.24, 77.49, [3, 4, 5, 6, 9, 10], "Lake-side hill station in the Palani Hills."),
    ("Yercaud", "Tamil Nadu", 11.78, 78.21, [3, 4, 5, 6, 10, 11], "Small hill station in the Shevaroys."),
    ("Bengaluru", "Karnataka", 12.97, 77.59, [10, 11, 12, 1, 2, 3], "Garden city and tech capital."),
    ("Mysuru", "Karnataka", 12.30, 76.64, [10, 11, 12, 1, 2, 3], "Royal city of palaces."),
    ("Coorg", "Karnataka", 12.42, 75.74, [10, 11, 12, 1, 2, 3, 4], "Coffee country in the Western Ghats."),
    ("Hampi", "Karnataka", 15.34, 76.46, [10, 11, 12, 1, 2], "Ruins of the Vijayanagara empire."),
    ("Wayanad", "Kerala", 11.61, 76.08, [10, 11, 12, 1, 2, 3, 4, 5], "Forests, caves and peaks."),
    ("Kochi", "Kerala", 9.93, 76.27, [10, 11, 12, 1, 2, 3], "Historic port city."),
    ("Munnar", "Kerala", 10.09, 77.06, [9, 10, 11, 12, 1, 2, 3, 4, 5], "Tea-covered hills."),
    ("Thekkady", "Kerala", 9.60, 77.16, [10, 11, 12, 1, 2, 3, 4], "Periyar forests and spice gardens."),
    ("Alappuzha", "Kerala", 9.50, 76.34, [11, 12, 1, 2, 3], "Backwaters and houseboats."),
    ("Varkala", "Kerala", 8.74, 76.72, [10, 11, 12, 1, 2, 3], "Cliff-top beach town."),
    ("Thiruvananthapuram", "Kerala", 8.52, 76.94, [10, 11, 12, 1, 2, 3], "Capital of Kerala."),
]

# from, to, mode, distance km, hours, cost INR  (stored once, travelled both ways)
ROUTES = [
    ("Chennai", "Mahabalipuram", "road", 58, 1.5, 700), ("Chennai", "Kanchipuram", "road", 75, 2.0, 900),
    ("Kanchipuram", "Mahabalipuram", "road", 65, 1.5, 800), ("Mahabalipuram", "Puducherry", "road", 95, 2.0, 1100),
    ("Chennai", "Puducherry", "road", 150, 3.5, 1700), ("Chennai", "Tirupati", "road", 135, 3.5, 1500),
    ("Chennai", "Tirupati", "rail", 147, 3.0, 250), ("Chennai", "Bengaluru", "road", 345, 6.5, 3800),
    ("Chennai", "Bengaluru", "rail", 362, 5.0, 650), ("Chennai", "Tiruchirappalli", "rail", 330, 5.5, 550),
    ("Chennai", "Madurai", "flight", 430, 1.2, 4500), ("Chennai", "Kochi", "flight", 560, 1.3, 5000),
    ("Puducherry", "Thanjavur", "road", 180, 4.0, 2000), ("Tiruchirappalli", "Thanjavur", "road", 58, 1.5, 700),
    ("Tiruchirappalli", "Madurai", "road", 135, 2.5, 1500), ("Tiruchirappalli", "Madurai", "rail", 155, 2.5, 250),
    ("Madurai", "Rameswaram", "road", 175, 3.5, 1900), ("Madurai", "Rameswaram", "rail", 160, 4.0, 200),
    ("Madurai", "Kanyakumari", "road", 245, 4.5, 2700), ("Madurai", "Kodaikanal", "road", 120, 3.5, 1400),
    ("Rameswaram", "Kanyakumari", "road", 300, 5.5, 3300), ("Kanyakumari", "Thiruvananthapuram", "road", 90, 2.5, 1000),
    ("Kanyakumari", "Thiruvananthapuram", "rail", 87, 2.0, 150), ("Thiruvananthapuram", "Varkala", "road", 45, 1.5, 550),
    ("Thiruvananthapuram", "Varkala", "rail", 41, 1.0, 100), ("Varkala", "Alappuzha", "road", 115, 3.0, 1300),
    ("Thiruvananthapuram", "Kochi", "rail", 220, 4.0, 400), ("Alappuzha", "Kochi", "road", 55, 1.5, 650),
    ("Kochi", "Munnar", "road", 130, 4.0, 1500), ("Munnar", "Thekkady", "road", 90, 3.0, 1100),
    ("Thekkady", "Madurai", "road", 140, 3.5, 1600), ("Alappuzha", "Thekkady", "road", 140, 4.0, 1600),
    ("Kochi", "Coimbatore", "rail", 190, 4.0, 350), ("Kodaikanal", "Munnar", "road", 160, 5.0, 1900),
    ("Coimbatore", "Ooty", "road", 85, 3.0, 1000), ("Coimbatore", "Tiruchirappalli", "road", 215, 4.5, 2400),
    ("Coimbatore", "Kodaikanal", "road", 175, 5.0, 2000), ("Coimbatore", "Bengaluru", "rail", 365, 6.5, 600),
    ("Ooty", "Mysuru", "road", 125, 3.5, 1400), ("Wayanad", "Ooty", "road", 110, 3.5, 1300),
    ("Mysuru", "Bengaluru", "road", 145, 3.0, 1600), ("Mysuru", "Bengaluru", "rail", 139, 2.5, 200),
    ("Mysuru", "Coorg", "road", 120, 3.0, 1400), ("Mysuru", "Wayanad", "road", 140, 3.5, 1600),
    ("Coorg", "Bengaluru", "road", 250, 5.5, 2800), ("Bengaluru", "Hampi", "road", 340, 6.5, 3700),
    ("Bengaluru", "Hampi", "rail", 360, 7.0, 500), ("Bengaluru", "Tirupati", "road", 250, 5.0, 2800),
    ("Bengaluru", "Yercaud", "road", 230, 5.0, 2600), ("Yercaud", "Tiruchirappalli", "road", 170, 4.0, 1900),
    ("Yercaud", "Coimbatore", "road", 190, 4.0, 2100), ("Bengaluru", "Thiruvananthapuram", "flight", 560, 1.3, 5200),
    ("Wayanad", "Kochi", "road", 255, 6.5, 2800),
]

# attractionId, name, destination, categories, rating, entry fee INR (approx.), visit hours
ATTRACTIONS = [
    ("a01", "Marina Beach", "Chennai", ["Beach"], 4.3, 0, 2), ("a02", "Kapaleeshwarar Temple", "Chennai", ["Temple"], 4.6, 0, 1.5),
    ("a03", "Government Museum Chennai", "Chennai", ["Museum", "Heritage"], 4.2, 15, 2), ("a04", "Fort St. George", "Chennai", ["Heritage", "Museum"], 4.1, 25, 1.5),
    ("a05", "Shore Temple", "Mahabalipuram", ["Heritage", "Temple", "Beach"], 4.6, 40, 1.5), ("a06", "Pancha Rathas", "Mahabalipuram", ["Heritage"], 4.5, 40, 1),
    ("a07", "Promenade Beach", "Puducherry", ["Beach"], 4.5, 0, 2), ("a08", "French Quarter", "Puducherry", ["Heritage"], 4.6, 0, 2.5),
    ("a09", "Auroville", "Puducherry", ["Spiritual", "Nature"], 4.4, 0, 3), ("a10", "Ekambareswarar Temple", "Kanchipuram", ["Temple"], 4.6, 0, 1.5),
    ("a11", "Kailasanathar Temple", "Kanchipuram", ["Heritage", "Temple"], 4.6, 0, 1), ("a12", "Tirumala Venkateswara Temple", "Tirupati", ["Temple", "Spiritual"], 4.8, 0, 4),
    ("a13", "Brihadeeswarar Temple", "Thanjavur", ["Heritage", "Temple"], 4.8, 0, 2), ("a14", "Thanjavur Palace", "Thanjavur", ["Heritage", "Museum"], 4.2, 50, 1.5),
    ("a15", "Sri Ranganathaswamy Temple", "Tiruchirappalli", ["Temple", "Spiritual"], 4.7, 0, 2.5), ("a16", "Rockfort Temple", "Tiruchirappalli", ["Temple", "Adventure"], 4.5, 5, 1.5),
    ("a17", "Meenakshi Amman Temple", "Madurai", ["Temple", "Heritage", "Spiritual"], 4.8, 0, 2.5), ("a18", "Thirumalai Nayakkar Mahal", "Madurai", ["Heritage", "Museum"], 4.3, 50, 1),
    ("a19", "Ramanathaswamy Temple", "Rameswaram", ["Temple", "Spiritual"], 4.7, 0, 2), ("a20", "Dhanushkodi", "Rameswaram", ["Beach", "Adventure"], 4.6, 0, 3),
    ("a21", "Vivekananda Rock Memorial", "Kanyakumari", ["Spiritual", "Heritage"], 4.6, 50, 2), ("a22", "Kanyakumari Sunrise Point", "Kanyakumari", ["Beach"], 4.4, 0, 1),
    ("a23", "Adiyogi Shiva Statue", "Coimbatore", ["Spiritual"], 4.7, 0, 2), ("a24", "Marudhamalai Temple", "Coimbatore", ["Temple", "Hill Station"], 4.5, 0, 1.5),
    ("a25", "Ooty Botanical Garden", "Ooty", ["Nature"], 4.4, 50, 2), ("a26", "Nilgiri Mountain Railway", "Ooty", ["Heritage", "Adventure", "Hill Station"], 4.7, 300, 5),
    ("a27", "Doddabetta Peak", "Ooty", ["Hill Station", "Nature"], 4.4, 10, 1.5), ("a28", "Kodai Lake", "Kodaikanal", ["Nature", "Hill Station"], 4.5, 0, 2),
    ("a29", "Coaker's Walk", "Kodaikanal", ["Nature", "Hill Station"], 4.4, 20, 1), ("a30", "Yercaud Lake", "Yercaud", ["Nature", "Hill Station"], 4.2, 0, 1.5),
    ("a31", "Kiliyur Falls", "Yercaud", ["Waterfall", "Adventure"], 4.1, 0, 2), ("a32", "Lalbagh Botanical Garden", "Bengaluru", ["Nature"], 4.5, 30, 2),
    ("a33", "Bangalore Palace", "Bengaluru", ["Heritage", "Museum"], 4.2, 280, 1.5), ("a34", "Cubbon Park", "Bengaluru", ["Nature"], 4.5, 0, 1.5),
    ("a35", "Mysore Palace", "Mysuru", ["Heritage", "Museum"], 4.7, 120, 2), ("a36", "Chamundi Hills", "Mysuru", ["Temple", "Hill Station"], 4.6, 0, 2),
    ("a37", "Brindavan Gardens", "Mysuru", ["Nature"], 4.3, 50, 2), ("a38", "Abbey Falls", "Coorg", ["Waterfall", "Nature"], 4.2, 15, 1.5),
    ("a39", "Dubare Elephant Camp", "Coorg", ["Wildlife", "Adventure"], 4.3, 100, 3), ("a40", "Coorg Coffee Estate Walk", "Coorg", ["Plantation", "Nature"], 4.5, 500, 3),
    ("a41", "Virupaksha Temple", "Hampi", ["Heritage", "Temple"], 4.7, 0, 1.5), ("a42", "Vittala Temple Complex", "Hampi", ["Heritage"], 4.8, 40, 2.5),
    ("a43", "Edakkal Caves", "Wayanad", ["Heritage", "Adventure"], 4.4, 40, 2.5), ("a44", "Chembra Peak", "Wayanad", ["Adventure", "Nature", "Hill Station"], 4.5, 150, 5),
    ("a45", "Banasura Sagar Dam", "Wayanad", ["Nature"], 4.3, 40, 2), ("a46", "Fort Kochi", "Kochi", ["Heritage"], 4.5, 0, 3),
    ("a47", "Chinese Fishing Nets", "Kochi", ["Heritage", "Beach"], 4.3, 0, 1), ("a48", "Mattancherry Palace", "Kochi", ["Museum", "Heritage"], 4.2, 5, 1),
    ("a49", "Munnar Tea Gardens", "Munnar", ["Plantation", "Nature", "Hill Station"], 4.7, 0, 3), ("a50", "Eravikulam National Park", "Munnar", ["Wildlife", "Nature"], 4.6, 200, 3),
    ("a51", "Mattupetty Dam", "Munnar", ["Nature"], 4.3, 10, 1.5), ("a52", "Periyar Tiger Reserve", "Thekkady", ["Wildlife", "Adventure"], 4.5, 45, 4),
    ("a53", "Thekkady Spice Plantation", "Thekkady", ["Plantation"], 4.3, 200, 2), ("a54", "Alleppey Backwater Houseboat", "Alappuzha", ["Backwaters", "Nature"], 4.7, 0, 6),
    ("a55", "Alappuzha Beach", "Alappuzha", ["Beach"], 4.3, 0, 1.5), ("a56", "Varkala Cliff Beach", "Varkala", ["Beach", "Adventure"], 4.6, 0, 3),
    ("a57", "Padmanabhaswamy Temple", "Thiruvananthapuram", ["Temple", "Heritage"], 4.7, 0, 2), ("a58", "Kovalam Beach", "Thiruvananthapuram", ["Beach"], 4.4, 0, 2.5),
]

# Hotels are fictional. One per price band where it makes sense.
_BANDS = {"budget": (2, 1800, 3.9), "mid": (3, 4200, 4.2), "luxury": (5, 12500, 4.5)}
_SUFFIX = {"budget": "Traveller Inn", "mid": "Residency", "luxury": "Grand Retreat"}
_POPULAR = {"Chennai", "Bengaluru", "Kochi", "Mysuru", "Ooty", "Munnar", "Alappuzha", "Madurai", "Puducherry",
            "Coorg", "Thiruvananthapuram", "Kodaikanal", "Wayanad"}
_AMENITIES = {"budget": ["wifi"], "mid": ["wifi", "restaurant", "parking"], "luxury": ["wifi", "restaurant", "pool", "spa", "parking"]}


def _hotels():
    out, n = [], 1
    for i, (dest, *_rest) in enumerate(DESTINATIONS):
        bands = ["budget", "mid", "luxury"] if dest in _POPULAR else ["budget", "mid"]
        for band in bands:
            stars, price, rating = _BANDS[band]
            price = int(price * (1 + ((i * 7 + n) % 5) / 10))          # vary prices a little
            rating = round(min(4.9, rating + ((i + n) % 4) / 10), 1)
            out.append((f"h{n:02d}", f"{dest} {_SUFFIX[band]}", dest, stars + (1 if band == "mid" and i % 3 == 0 else 0),
                        price, band, rating, _AMENITIES[band]))
            n += 1
    return out


HOTELS = _hotels()

# touristId, name, age, home destination, budget band, travel style, interests {category: weight}
TOURISTS = [
    ("t01", "Ananya Iyer", 24, "Chennai", "budget", "beach", {"Beach": 3, "Backwaters": 2, "Adventure": 1}),
    ("t02", "Rohit Sharma", 29, "Bengaluru", "mid", "beach", {"Beach": 3, "Adventure": 2}),
    ("t03", "Meera Pillai", 35, "Kochi", "mid", "beach", {"Beach": 2, "Backwaters": 3, "Nature": 1}),
    ("t04", "Arjun Reddy", 41, "Bengaluru", "luxury", "heritage", {"Heritage": 3, "Museum": 2, "Temple": 1}),
    ("t05", "Lakshmi Venkat", 52, "Chennai", "mid", "heritage", {"Heritage": 3, "Temple": 2}),
    ("t06", "Daniel Joseph", 33, "Coimbatore", "budget", "heritage", {"Heritage": 2, "Museum": 3}),
    ("t07", "Sita Raman", 60, "Madurai", "mid", "spiritual", {"Temple": 3, "Spiritual": 3}),
    ("t08", "Ganesh Kumar", 47, "Chennai", "budget", "spiritual", {"Temple": 3, "Spiritual": 2, "Heritage": 1}),
    ("t09", "Padma Srinivasan", 58, "Bengaluru", "mid", "spiritual", {"Spiritual": 3, "Temple": 2}),
    ("t10", "Kiran Nair", 27, "Kochi", "mid", "nature", {"Nature": 3, "Hill Station": 3, "Plantation": 2}),
    ("t11", "Priya Menon", 31, "Bengaluru", "luxury", "nature", {"Nature": 3, "Plantation": 2, "Waterfall": 2}),
    ("t12", "Vikram Das", 26, "Coimbatore", "budget", "nature", {"Hill Station": 3, "Nature": 2, "Waterfall": 1}),
    ("t13", "Farah Khan", 30, "Chennai", "mid", "nature", {"Nature": 2, "Hill Station": 2, "Waterfall": 2}),
    ("t14", "Sanjay Gupta", 34, "Bengaluru", "mid", "wildlife", {"Wildlife": 3, "Adventure": 3}),
    ("t15", "Nisha Thomas", 28, "Kochi", "budget", "wildlife", {"Wildlife": 3, "Adventure": 2, "Nature": 1}),
    ("t16", "Aditya Rao", 23, "Bengaluru", "budget", "wildlife", {"Adventure": 3, "Wildlife": 2, "Waterfall": 2}),
    ("t17", "Kavitha Suresh", 38, "Madurai", "mid", "mixed", {"Temple": 2, "Hill Station": 2, "Nature": 2}),
    ("t18", "Rahul Verma", 36, "Chennai", "luxury", "mixed", {"Beach": 2, "Heritage": 2, "Backwaters": 1}),
    ("t19", "Divya Prakash", 25, "Coimbatore", "mid", "mixed", {"Adventure": 2, "Beach": 2, "Hill Station": 1}),
    ("t20", "Joseph Mathew", 44, "Kochi", "mid", "mixed", {"Heritage": 2, "Plantation": 2, "Wildlife": 1}),
]


def _generate_visits(seed=42):
    """Visits follow interests (with some randomness), so similar tourists overlap."""
    rng = random.Random(seed)
    visits, stays, wishes = [], [], []
    hotel_by_dest = {}
    for h in HOTELS:
        hotel_by_dest.setdefault(h[2], []).append(h)
    for tid, _name, _age, home, budget, _style, interests in TOURISTS:
        weights = []
        for a in ATTRACTIONS:
            match = sum(interests.get(c, 0) for c in a[3])
            weights.append((a, match))
        k = rng.randint(6, 9)
        chosen, pool = [], [(a, 1 + 2.5 * m) for a, m in weights if a[2] != home]
        while len(chosen) < k and pool:
            total = sum(w for _, w in pool)
            r, acc = rng.random() * total, 0.0
            for idx, (a, w) in enumerate(pool):
                acc += w
                if acc >= r:
                    chosen.append(a)
                    pool.pop(idx)
                    break
        for j, a in enumerate(chosen):
            match = sum(interests.get(c, 0) for c in a[3])
            rating = 5 if match >= 3 else 4 if match >= 2 else rng.choice([3, 4]) if match >= 1 else rng.choice([2, 3, 3, 4])
            date = f"{2023 + j * 3 // k}-{1 + (j * 5 + rng.randint(0, 3)) % 12:02d}-{rng.randint(1, 28):02d}"
            visits.append((tid, a[0], date, rating))
        for d in sorted({a[2] for a in chosen})[:4]:
            options = [h for h in hotel_by_dest.get(d, []) if h[5] == budget] or hotel_by_dest.get(d, [])
            if options:
                h = options[0]
                stays.append((tid, h[0], f"{2023 + rng.randint(0, 2)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                              rng.randint(1, 4), rng.choice([3, 4, 4, 5, 5])))
        seen = {a[2] for a in chosen} | {home}
        dest_scores = {}
        for a, m in weights:
            if a[2] not in seen and m:
                dest_scores[a[2]] = dest_scores.get(a[2], 0) + m
        for d, _ in sorted(dest_scores.items(), key=lambda x: (-x[1], x[0]))[:rng.randint(1, 2)]:
            wishes.append((tid, d, f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"))
    visits.sort(key=lambda v: (v[0], v[2]))
    return visits, stays, wishes


VISITS, STAYS, WISHLIST = _generate_visits()
