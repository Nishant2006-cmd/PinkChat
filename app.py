import eventlet
eventlet.monkey_patch()  # <-- Sabse pehle ye chalega, bina kisi exception ke!

import random
import os
from flask import Flask, render_template, redirect, request, url_for
from flask_socketio import SocketIO, join_room, leave_room
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from pymongo.errors import DuplicateKeyError

from db import (
    get_user,
    save_user,
    add_friend,
    get_friends,
    get_notifications,
    save_notification,
    save_message,
    get_messages,
    delete_friend,
    mark_notifications_as_read
)
import string


app = Flask(__name__)

app.config['SECRET_KEY'] = 'secretkey'
socketio = SocketIO(app, async_mode="eventlet")
waiting_user = None#3#######
online_users = set()
user_sockets = {}
login_manager = LoginManager()
login_manager.login_view ="login"
login_manager.init_app(app)





@app.route("/")
def index():

    friends = []
    notifications = []

    if current_user.is_authenticated:

        friends = get_friends(
            current_user.username
        )

        notifications = get_notifications(
            current_user.username
        )

    return render_template(
        "index.html",
        friends=friends,
        notifications=notifications,
        online_users=online_users
    )

# Globally active users in rooms track karne ke liye
room_active_users = {}  # Format: {'room_name': ['username1', 'username2']}

# 1. 'app = Flask(__name__)' ke just neeche ye line add kar dena agar pehle se nahi hai:
room_active_users = {}  # Format: {'room_name': ['user1', 'user2']}

# 2. Apne 'join' handler ko aise update karo:
@socketio.on('join')
def handle_join(data):
    username = data.get('username')
    room = data.get('room')
    
    if not username or not room:
        return
        
    join_room(room) # User ko room me connect kiya
    
    # --- COUNT TRACK KARNE KA LOGIC ---
    if room not in room_active_users:
        room_active_users[room] = []
    if username not in room_active_users[room]:
        room_active_users[room].append(username)
        
    # Frontend ko data wapas bheja (Count aur Users list)
    emit('room_stats', {
        'count': len(room_active_users[room]),
        'users': room_active_users[room]
    }, to=room)

# 3. Apne 'leave' handler ko bhi update kar do taaki koi jaye toh count kam ho:
@socketio.on('leave')
def handle_leave(data):
    username = data.get('username')
    room = data.get('room')
    
    if not username or not room:
        return
        
    leave_room(room)
    
    if room in room_active_users and username in room_active_users[room]:
        room_active_users[room].remove(username)
        
    emit('room_stats', {
        'count': len(room_active_users[room]),
        'users': room_active_users[room]
    }, to=room)
@socketio.on('disconnect')
def handle_disconnect():

    username = user_sockets.get(request.sid)

    if username:

        online_users.discard(username)

        del user_sockets[request.sid]
        socketio.emit(
    'user_offline',
    {
        'username': username
    }
)
        
        # app.py ke andar ye naya event add karo
@socketio.on('add_friend_instant')
def handle_add_friend_instant(data):
    current_user = data.get('username')
    target_user = data.get('target')
    
    if not current_user or not target_user:
        return

    # 1. Database (friends_collection) me check karo ya naya connection banao
    # Hum ek unique room ID banate hain dono ke liye (jaise: pm_UserA_UserB sorted order me)
    sorted_users = sorted([current_user, target_user])
    pm_room_id = f"pm_{sorted_users[0]}_{sorted_users[1]}"
    
    # Check karo agar ye dosti pehle se database me hai ya nahi
    existing_friendship = friends_collection.find_one({
        'user1': sorted_users[0],
        'user2': sorted_users[1]
    })
    
    if not existing_friendship:
        # Permanent dosti insert karo database me
        friends_collection.insert_one({
            'user1': sorted_users[0],
            'user2': sorted_users[1],
            'room_id': pm_room_id,
            'timestamp': datetime.utcnow()
        })
        
    # 2. Real-time magic: Dono users ko personal channels par signal bhejo 
    # taaki dono ke sidebar ya chat list me ye PM room automatic pop-up ho jaye
    emit('friend_added_success', {
        'user1': sorted_users[0],
        'user2': sorted_users[1],
        'room_id': pm_room_id
    }, to=current_user)  # Aapko signal mila
    
    emit('friend_added_success', {
        'user1': sorted_users[0],
        'user2': sorted_users[1],
        'room_id': pm_room_id
    }, to=target_user)   # Saamne waale ko automatic signal mila

@app.route('/signup', methods=['GET', 'POST'])
def signup():

    if current_user.is_authenticated:
        return redirect(url_for('index'))

    message = ''

    if request.method == 'POST':

        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if len(username) < 3:

            message = "Username too short"

        elif "@" not in email or "." not in email:

            message = "Invalid email"

        elif len(password) < 6:

            message = "Password must be at least 6 characters"

        else:

            try:

                save_user(
                    username,
                    email,
                    password
                )

                return redirect(url_for('login'))

            except DuplicateKeyError:

                message = "User already exists!!"

    return render_template(
        'signup.html',
        message=message
    )
@app.route('/login', methods=['GET', 'POST'])
def login():

    if current_user.is_authenticated:
        return redirect(url_for('index'))

    message = ''

    if request.method == 'POST':

        username = request.form.get('username')
        password_input = request.form.get('password')

        user = get_user(username)

        if user and user.check_password(password_input):

            login_user(user)

            return redirect(url_for('index'))

        else:
            message = 'Invalid username or password'

    return render_template(
        'login.html',
        message=message
    )


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/chat')
def chat():

    username = request.args.get('username')
    room = request.args.get('room')

    if username and room:

        messages = get_messages(room)

        return render_template(
            'chat.html',
            username=username,
            room=room,
            messages=messages
        )

    else:
        return redirect(url_for('index'))


@app.route('/pm/<friend_username>')
@login_required

def private_chat(friend_username):

    sorted_users = sorted([
        current_user.username,
        friend_username
    ])
    mark_notifications_as_read(
    current_user.username,
    friend_username
)

    room = f"pm_{sorted_users[0]}_{sorted_users[1]}"

    return redirect(
        url_for(
            'chat',
            username=current_user.username,
            room=room
        )
    )   

@app.route('/random')
def random_chat():

    username = "Guest" + ''.join(random.choices(string.digits, k=4))

    room = "global_random_room"

    return redirect(
        url_for(
            'chat',
            username=username,
            room=room
        )
    )


@app.route('/add_friend', methods=['POST'])
@login_required
def add_friend_route():

    friend_username = request.form.get('friend')

    add_friend(current_user.username, friend_username)

    return redirect(url_for('index'))

@app.route('/delete_friend/<friend>')
@login_required
def delete_friend_route(friend):

    delete_friend(
        current_user.username,
        friend
    )

    return redirect(url_for('index'))





@socketio.on('send_message')
def handle_send_message_event(data):

    # SAVE ONLY PM MESSAGES
    if data['room'].startswith("pm_"):

        save_message(

            data['room'],
            data['message'],
            data['username'],
            data.get('image')

        )

    # SEND MESSAGE TO ROOM
    socketio.emit(

        'receive_message',

        {
            'username': data['username'],
            'message': data['message'],
            'image': data.get('image')
        },

        room=data['room']

    )

    # PM NOTIFICATIONS ONLY
    if data['room'].startswith("pm_"):

        users = data['room'].replace(
            "pm_",
            ""
        ).split("_")

        receiver = None

        for user in users:

            if user != data['username']:
                receiver = user

        save_notification(
            receiver,
            data['username']
        )

        socketio.emit(

            'new_notification',

            {
                'sender': data['username']
            },

            room=f"user_{receiver}"

        )
@socketio.on('join_room')
def handle_join_room_event(data):

    join_room(data['room'])

    socketio.emit(
        'join_room_announcement',
        data,
        room=data['room'],
        include_self=False
    )


@socketio.on('leave_room')
def handle_leave_room_event(data):

    leave_room(data['room'])

    socketio.emit(
        'leave_room_announcement',
        data,
        room=data['room'],
        include_self=False
    )


@login_manager.user_loader
def load_user(username):

    return get_user(username)
@socketio.on('join_personal_room')
def handle_join_personal_room(data):

    username = data['username']

    online_users.add(username)

    user_sockets[request.sid] = username

    join_room(f"user_{username}")
    socketio.emit(
    'user_online',
    {
        'username': username
    }
)




if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)