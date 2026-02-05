# app/models.py
from pymongo import MongoClient
from flask import current_app
from bson.objectid import ObjectId
import os

def get_db():
    client = MongoClient(current_app.config['MONGO_URI'])
    db = client.get_default_database()
    return db

# helper functions
def create_expense(user_id, expense_doc):
    db = get_db()
    expense_doc['user_id'] = ObjectId(user_id)
    db.expenses.insert_one(expense_doc)
    return expense_doc

def list_expenses(user_id, limit=100):
    db = get_db()
    return list(db.expenses.find({"user_id": ObjectId(user_id)}).sort("timestamp", -1).limit(limit))

def create_or_update_goal(user_id, name, amount):
    db = get_db()
    q = {"user_id": ObjectId(user_id), "name": name}
    doc = db.goals.find_one(q)
    if doc:
        db.goals.update_one(q, {"$inc": {"saved_amount": amount}, "$set": {"updated_at": __import__('datetime').datetime.utcnow()}})
        return db.goals.find_one(q)
    else:
        new_doc = {
            "user_id": ObjectId(user_id),
            "name": name,
            "target_amount": amount,
            "saved_amount": amount,
            "currency": "INR",
            "created_at": __import__('datetime').datetime.utcnow(),
            "updated_at": __import__('datetime').datetime.utcnow()
        }
        db.goals.insert_one(new_doc)
        return new_doc

def list_goals(user_id):
    db = get_db()
    return list(db.goals.find({"user_id": ObjectId(user_id)}))
