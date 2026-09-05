import random
import os
import string
from datetime import datetime
from flask import Flask, render_template, redirect, request, url_for
from flask_socketio import SocketIO, join_room, leave_room
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from pymongo.errors import DuplicateKeyError

app = Flask(__name__)

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



# Global room users set initialization
if 'global_room_users' not in globals():
    global_room_users = set()

app.config['SECRET_KEY'] = 'secretkey'

socketio = SocketIO(app, cors_allowed_origins="*")
socketio.run(app, host="0.0.0.0", port=8000, debug=True)


online_users = set()
user_sockets = {}

# Login Manager Initialization
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@app.route("/")
def index():
    friends = []
    notifications = []

    if current_user.is_authenticated:
        friends = get_friends(current_user.username)
        notifications = get_notifications(current_user.username)

    return render_template(
        "index.html",
        friends=friends,
        notifications=notifications,
        online_users=online_users
    )


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
                save_user(username, email, password)
                return redirect(url_for('login'))
            except DuplicateKeyError:
                message = "User already exists!!"

    return render_template('signup.html', message=message)


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

    return render_template('login.html', message=message)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/chat')
def chat():
    username = request.args.get('username') or "guest"
    room = request.args.get('room') or "global_random_room"

    # No redirect here — just render directly
    messages = get_messages(room)
    return render_template('chat.html', username=username, room=room, messages=messages)


@app.route('/pm/<friend_username>')
@login_required
def private_chat(friend_username):
    sorted_users = sorted([current_user.username, friend_username])
    mark_notifications_as_read(current_user.username, friend_username)
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
    delete_friend(current_user.username, friend)
    return redirect(url_for('index'))


# ================= SOCKET.IO =================

@socketio.on('send_message')
def handle_send_message_event(data):
    print("DEBUG: send_message event received:", data)

    try:
        room = data.get('room')
        message = data.get('message')
        username = data.get('username')
        image = data.get('image')

        print(
            f"DEBUG: room={room}, "
            f"user={username}, "
            f"message={message[:50] if message else None}"
        )

        # Check required data
        if not room or not username:
            print("ERROR: Missing room or username")
            return

        # Save message to MongoDB
        save_message(
            room,
            message,
            username,
            image
        )

        # Send message to everyone in the room
        socketio.emit(
            'receive_message',
            {
                'username': username,
                'message': message,
                'image': image
            },
            room=room
        )

        # Private message notification
        if room.startswith("pm_"):

            users = room.replace("pm_", "").split("_")

            receiver = None

            for user in users:
                if user != username:
                    receiver = user
                    break

            if receiver:

                save_notification(
                    receiver,
                    username
                )

                socketio.emit(
                    'new_notification',
                    {
                        'sender': username
                    },
                    room=f"user_{receiver}"
                )

    except Exception as e:
        print("ERROR in send_message handler:", str(e))

        import traceback
        print(traceback.format_exc())


    # Global random room
    if room == "global_random_room" and username:

        global_room_users.add(username)

        socketio.emit(
            'global_room_stats',
            {
                'count': len(global_room_users),
                'users': list(global_room_users)
            },
            room="global_random_room"
        )

@socketio.on('join_room')
def handle_join_room_event(data):
    room = data.get('room')
    username = data.get('username')
    
    join_room(room)

    # Announcement logic (olddddd features)
    socketio.emit(
        'join_room_announcement',
        data,
        room=room,
        include_self=False
    )

    # ONLY TARGET GLOBAL RANDOM ROOM 
    if room == "global_random_room" and username:
        global_room_users.add(username)
        
        # Room ke sabhi logon ko realtime stats bhej do
        socketio.emit('global_room_stats', {
            'count': len(global_room_users),
            'users': list(global_room_users)
        }, room="global_random_room")


# 3. tune 'leave_room' event ko  change :
@socketio.on('leave_room')
def handle_leave_room_event(data):
    room = data.get('room')
    username = data.get('username')
    
    leave_room(room)

    socketio.emit(
        'leave_room_announcement',
        data,
        room=room,
        include_self=False
    )

    #  REMOVE USER jaye to
    if room == "global_random_room" and username:
        global_room_users.discard(username)
        
        socketio.emit('global_room_stats', {
            'count': len(global_room_users),
            'users': list(global_room_users)
        }, room="global_random_room")


@socketio.on('disconnect')
def handle_disconnect():
    username = user_sockets.get(request.sid)
    if username:
        online_users.discard(username)
        
        # Global room
        if username in global_room_users:
            global_room_users.discard(username)
            socketio.emit('global_room_stats', {
                'count': len(global_room_users),
                'users': list(global_room_users)
            }, room="global_random_room")

        if request.sid in user_sockets:
            del user_sockets[request.sid]
        
        socketio.emit('user_offline', {'username': username})

#  INSTANT AUTOMATIC FRIEND ADD & PM REDIRECT 
@socketio.on('add_friend_instant')
def handle_add_friend_instant(data):
    current_user_name = data.get('username')
    target_user = data.get('target')
    
    if not current_user_name or not target_user:
        return

    #  Dono tarf se dosti insert karo taaki database verify kar sake
    add_friend(current_user_name, target_user)
    add_friend(target_user, current_user_name)  # dono side dosti pakki karegi!
    
    # Realtime signal dono bandon ko jayga unke personal sockets par
    socketio.emit('friend_added_success', {
        'user1': current_user_name,
        'user2': target_user
    }, room=f"user_{current_user_name}")
    
    socketio.emit('friend_added_success', {
        'user1': current_user_name,
        'user2': target_user
    }, room=f"user_{target_user}")
    
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



@login_manager.user_loader
def load_user(username):
    return get_user(username)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=8000, debug=True)




