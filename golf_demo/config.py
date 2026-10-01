"""Everything a salesperson might want to change before a demo.

Swap the business name, the course, or the prices here; nothing else needs
editing. Prices are per player, in whole dollars.
"""

# Your company (shown small, as "Powered by ...").
BUSINESS_NAME = "Fairway Follow-Up"

# The made-up course the demo pretends to be.
COURSE_NAME = "Pine Ridge Golf Club"
COURSE_CITY = "Springfield"
COURSE_PHONE = "(555) 010-4653"
EVENTS_CONTACT = "Mike Larson, Head Golf Professional"

# Golf formats: (label, price per player).
FORMATS = {
    "18": ("18 holes with cart", 65),
    "9": ("9 holes with cart", 40),
    "scramble": ("18-hole scramble with prizes and scoring", 80),
}

# Food and drink: (label, price per player).
FOOD = {
    "none": ("No food", 0),
    "boxed": ("Boxed lunch at the turn", 15),
    "buffet": ("Post-round buffet", 35),
    "banquet": ("Plated dinner and awards banquet", 55),
}

WEEKDAY_DISCOUNT = 0.15     # Monday to Thursday
SHOTGUN_MIN_PLAYERS = 72    # groups this big get the whole course (shotgun start)
ESTIMATE_SPREAD = 0.10      # show the guest a +/-10% range, not a quote

# Follow-ups to quiet leads, in days after the inquiry.
FOLLOW_UP_DAYS = (2, 5, 10)
# Ask last year's groups to rebook this many days after their event.
REBOOK_AFTER_DAYS = 300
