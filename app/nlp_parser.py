import re

def parse_expense_text(text: str):
    """
    Parse text like "I spent 500 on pizza via Google Pay"
    → returns {'amount': 500, 'category': 'Food', 'payment_method': 'Google Pay'}
    """

    if not text:
        return {}

    text = text.lower()

    # --- Extract amount ---
    amount_match = re.search(r'(\d{1,6}(?:[\.,]\d{1,2})?)', text)
    amount = float(amount_match.group(1).replace(',', '')) if amount_match else 0.0

    # --- Detect payment method ---
    payment_method = None
    if "google pay" in text or "gpay" in text:
        payment_method = "Google Pay"
    elif "cash" in text:
        payment_method = "Cash"
    elif "credit" in text or "debit" in text:
        payment_method = "Card"
    elif "upi" in text:
        payment_method = "UPI"

    # --- Detect category ---
    category = "Others"

    food_keywords = ["pizza", "burger", "food", "meal", "restaurant", "coffee", "snack", "dinner", "lunch"]
    shopping_keywords = ["dress", "clothes", "shopping", "furniture", "electronics", "jeans", "bag"]
    transport_keywords = ["taxi", "uber", "bus", "train", "fuel", "petrol", "diesel", "cab", "bike"]
    bills_keywords = ["electric", "bill", "wifi", "internet", "mobile recharge", "subscription", "netflix"]
    entertainment_keywords = ["movie", "cinema", "game", "music", "concert", "ott"]
    health_keywords = ["medicine", "hospital", "doctor", "gym", "health", "protein"]
    education_keywords = ["book", "course", "exam", "college", "school", "tuition", "fees"]
    rent_keywords = ["rent", "flat", "room", "hostel"]
    travel_keywords = ["flight", "hotel", "trip", "vacation", "travel"]

    # Match category from text
    if any(word in text for word in food_keywords):
        category = "Food"
    elif any(word in text for word in shopping_keywords):
        category = "Shopping"
    elif any(word in text for word in transport_keywords):
        category = "Transport"
    elif any(word in text for word in bills_keywords):
        category = "Bills"
    elif any(word in text for word in entertainment_keywords):
        category = "Entertainment"
    elif any(word in text for word in health_keywords):
        category = "Health"
    elif any(word in text for word in education_keywords):
        category = "Education"
    elif any(word in text for word in rent_keywords):
        category = "Rent"
    elif any(word in text for word in travel_keywords):
        category = "Travel"

    # --- Build final parsed object ---
    return {
        "amount": amount,
        "category": category,
        "payment_method": payment_method,
        "description": text.capitalize(),
    }
