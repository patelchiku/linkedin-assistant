import random

# ── Connection request messages ─────────────────────────────────────────────
# LinkedIn allows max 300 characters for connection notes.
# Keep all variants well under that limit.

GENERIC_TEMPLATES = [
    "Hi {first_name}, I came across your profile and would love to connect and learn from each other's experiences!",
    "Hi {first_name}, your profile caught my attention. I'd love to connect and grow our professional networks together!",
    "Hello {first_name}, I'd love to add you to my professional network. Looking forward to connecting!",
    "Hi {first_name}, I'd love to connect with you and explore potential synergies. Hope to hear from you!",
    "Hey {first_name}, saw your profile and thought it'd be great to connect. Looking forward to it!",
]

NOTE_TEMPLATES = [
    "Hi {first_name}, I came across your profile and noticed {note}. Would love to connect and exchange ideas!",
    "Hello {first_name}, your background in {note} really stood out to me. I'd love to connect!",
    "Hi {first_name}, I see you're involved in {note} — that aligns well with my interests. Let's connect!",
    "Hey {first_name}, came across your profile and was intrigued by {note}. Would love to be in your network!",
]

# ── Event messages ──────────────────────────────────────────────────────────

BIRTHDAY_TEMPLATES = [
    "Happy Birthday, {first_name}! 🎂 Hope you have a wonderful day filled with joy. Best wishes!",
    "Wishing you a very Happy Birthday, {first_name}! Hope this year brings you great success and happiness!",
    "Happy Birthday {first_name}! Hope you're having an amazing day. Wishing you all the best!",
]

ANNIVERSARY_TEMPLATES = [
    "Congratulations on your work anniversary, {first_name}! 🎉 Wishing you continued growth and success ahead!",
    "Happy work anniversary, {first_name}! It's great to see your journey. Keep up the great work!",
    "Congrats on the work anniversary, {first_name}! Wishing you many more milestones to celebrate!",
]

NEW_JOB_TEMPLATES = [
    "Congrats on the new role, {first_name}! 🚀 Wishing you a great start and lots of success ahead!",
    "Exciting news, {first_name}! Congratulations on your new position. Best of luck in this new chapter!",
    "Happy to see you starting something new, {first_name}! Congrats and best wishes for the journey ahead!",
]

PROMOTION_TEMPLATES = [
    "Congratulations on your promotion, {first_name}! 🎊 Well deserved — wishing you great success in your new role!",
    "Awesome news, {first_name}! Congrats on the promotion. You've earned it — keep it up!",
    "Way to go, {first_name}! Congratulations on leveling up. Wishing you all the best in your new position!",
]

EVENT_MAP = {
    "birthday": BIRTHDAY_TEMPLATES,
    "work_anniversary": ANNIVERSARY_TEMPLATES,
    "new_job": NEW_JOB_TEMPLATES,
    "promotion": PROMOTION_TEMPLATES,
}

EVENT_LABELS = {
    "birthday": "Birthday",
    "work_anniversary": "Work Anniversary",
    "new_job": "New Job",
    "promotion": "Promotion",
}


def generate_connection_message(first_name: str, note: str = "") -> str:
    """Generate a personalized connection request message."""
    note = (note or "").strip()
    if note:
        template = random.choice(NOTE_TEMPLATES)
        msg = template.format(first_name=first_name, note=note.lower())
    else:
        template = random.choice(GENERIC_TEMPLATES)
        msg = template.format(first_name=first_name)

    # Safety: LinkedIn note limit is 300 chars
    return msg[:300]


def generate_event_message(first_name: str, event_type: str) -> str:
    """Generate a congratulatory / event message."""
    templates = EVENT_MAP.get(event_type, GENERIC_TEMPLATES)
    template = random.choice(templates)
    return template.format(first_name=first_name)


def get_event_label(event_type: str) -> str:
    return EVENT_LABELS.get(event_type, event_type.replace("_", " ").title())
