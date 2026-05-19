import os
from datetime import datetime
from bson.objectid import ObjectId
from pymongo import MongoClient, DESCENDING
from werkzeug.security import generate_password_hash
from user import User

# Configuration global rakhte hain sabse upar
MESSAGE_FETCH_LIMIT = 20

# Connection Setup
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
chat_db = client.get_database("ChatDB")

users_collection = chat_db.get_collection("users")
rooms_collection = chat_db.get_collection("rooms")
room_members_collection = chat_db.get_collection("room_members")
messages_collection = chat_db.get_collection("messages")
friends_collection = chat_db.get_collection("friends")
notifications_collection = chat_db.get_collection("notifications")


def save_user(username, email, password):
    password_hash = generate_password_hash(password)
    users_collection.insert_one({'_id': username, 'email': email, 'password': password_hash})


def get_user(username):
    user_data = users_collection.find_one({'_id': username})
    return User(user_data['_id'], user_data['email'], user_data['password']) if user_data else None


def save_room(room_name, created_by):
    room_id = rooms_collection.insert_one(
        {'name': room_name, 'created_by': created_by, 'created_at': datetime.now()}).inserted_id
    add_room_member(room_id, room_name, created_by, created_by, is_room_admin=True)
    return room_id


def update_room(room_id, room_name):
    rooms_collection.update_one({'_id': ObjectId(room_id)}, {'$set': {'name': room_name}})
    room_members_collection.update_many({'_id.room_id': ObjectId(room_id)}, {'$set': {'room_name': room_name}})


def get_room(room_id):
    return rooms_collection.find_one({'_id': ObjectId(room_id)})


def add_room_member(room_id, room_name, username, added_by, is_room_admin=False):
    room_members_collection.insert_one(
        {'_id': {'room_id': ObjectId(room_id), 'username': username}, 'room_name': room_name, 'added_by': added_by,
         'added_at': datetime.now(), 'is_room_admin': is_room_admin})


def add_room_members(room_id, room_name, usernames, added_by):
    room_members_collection.insert_many(
        [{'_id': {'room_id': ObjectId(room_id), 'username': username}, 'room_name': room_name, 'added_by': added_by,
          'added_at': datetime.now(), 'is_room_admin': False} for username in usernames])


def remove_room_members(room_id, usernames):
    room_members_collection.delete_many(
        {'_id': {'$in': [{'room_id': ObjectId(room_id), 'username': username} for username in usernames]}})


def get_room_members(room_id):
    return list(room_members_collection.find({'_id.room_id': ObjectId(room_id)}))


def get_rooms_for_user(username):
    return list(room_members_collection.find({'_id.username': username}))


def is_room_member(room_id, username):
    return room_members_collection.count_documents({'_id': {'room_id': ObjectId(room_id), 'username': username}})


def is_room_admin(room_id, username):
    return room_members_collection.count_documents(
        {'_id': {'room_id': ObjectId(room_id), 'username': username}, 'is_room_admin': True})


def save_message(
    room_id,
    text,
    sender,
    image=None,
    
):

    messages_collection.insert_one({

        'room_id': room_id,
        'text': text,
        'sender': sender,
        'image': image,
        'created_at': datetime.now()

    })


def get_messages(room_id, page=0):
    offset = page * MESSAGE_FETCH_LIMIT
    # Yahan agar messages khali hain ya cursor me error hai toh check lagate hain
    try:
        messages = list(
            messages_collection.find({'room_id': room_id})
            .sort('_id', DESCENDING)
            .limit(MESSAGE_FETCH_LIMIT)
            .skip(offset)
        )
        for message in messages:
            if 'created_at' in message and message['created_at']:
                if isinstance(message['created_at'], datetime):
                    message['created_at'] = message['created_at'].strftime("%d %b, %H:%M")
            else:
                message['created_at'] = datetime.now().strftime("%d %b, %H:%M")
        return messages[::-1]
    except Exception as e:
        print(f"Database Error in get_messages: {e}")
        return []
def add_friend(user, friend):

    friends_collection.insert_one({
        "user": user,
        "friend": friend
    })
def get_friends(user):

    return list(
        friends_collection.find({
            "user": user
        })
    )    
# Save a private message
def save_private_message(sender, receiver, text):
    conversation_id = get_conversation_id(sender, receiver)
    messages_collection.insert_one({
        'conversation_id': conversation_id,
        'text': text,
        'sender': sender,
        'receiver': receiver,
        'created_at': datetime.now()
    })

# Generate a consistent conversation ID
def get_conversation_id(user1, user2):
    # Ensure same ID regardless of order
    return ":".join(sorted([user1, user2]))

# Fetch private messages
MESSAGE_FETCH_LIMIT = 20

def get_private_messages(user1, user2, page=0):
    conversation_id = get_conversation_id(user1, user2)
    offset = page * MESSAGE_FETCH_LIMIT
    messages = list(
        messages_collection.find({'conversation_id': conversation_id})
        .sort('_id', DESCENDING)
        .limit(MESSAGE_FETCH_LIMIT)
        .skip(offset)
    )
    for message in messages:
        message['created_at'] = message['created_at'].strftime("%d %b, %H:%M")
    return messages[::-1]

def save_notification(user, sender):

    notifications_collection.insert_one({
        "user": user,
        "sender": sender,
        "read": False
    })


def get_notifications(user):

    return list(
        notifications_collection.find({
            "user": user,
            "read": False
        })
    )


def mark_notifications_as_read(user, sender):

    notifications_collection.update_many(
        {
            "user": user,
            "sender": sender
        },
        {
            "$set": {
                "read": True
            }
        }
    )


def delete_friend(user, friend):

    friends_collection.delete_one({
        "user": user,
        "friend": friend
    })
