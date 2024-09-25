from flask import Flask, request, render_template, redirect, url_for, session, make_response
import cv2
import numpy as np
import mysql.connector
import subprocess
import sys

# Try to connect to the MySQL database
try:
    db = mysql.connector.connect(
        host='localhost',
        user='admin',  
        password='password'  
    )
    print("Connection successful!")

    cursor = db.cursor()
    # Create a new database
    cursor.execute("CREATE DATABASE IF NOT EXISTS voting_system")
    cursor.execute("USE voting_system")

    # Create the required tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voters (
            id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(255) NOT NULL,
            id_number VARCHAR(16) NOT NULL UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faces (
            id INT AUTO_INCREMENT PRIMARY KEY,
            voter_id INT,
            face_data LONGBLOB,
            FOREIGN KEY (voter_id) REFERENCES voters(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            voter_id INT,
            candidate VARCHAR(255) NOT NULL,
            vote_date DATE NOT NULL,
            vote_time TIME NOT NULL,
            FOREIGN KEY (voter_id) REFERENCES voters(id) ON DELETE CASCADE
        )
    """)

    db.commit()
    print("Database and tables created successfully.")

except mysql.connector.Error as err:
    print(f"Error: {err}")
    sys.exit(1)

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with your actual secret key

# Admin credentials
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password'

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        full_name = request.form['full-name']
        id_number = request.form['id-number']

        if not (id_number.isdigit() and len(id_number) == 16):
            return render_template('index.html', error_message='Please enter a valid 16-digit ID number')

        try:
            video = cv2.VideoCapture(0)
            facedetect = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces_data = []
            i = 0
            framesTotal = 51
            captureAfterFrame = 2
            while True:
                ret, frame = video.read()
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = facedetect.detectMultiScale(gray, 1.3, 5)
                for (x, y, w, h) in faces:
                    crop_img = frame[y:y+h, x:x+w]
                    resized_img = cv2.resize(crop_img, (50, 50))
                    if len(faces_data) <= framesTotal and i % captureAfterFrame == 0:
                        faces_data.append(resized_img)
                    i += 1
                    cv2.putText(frame, str(len(faces_data)), (50, 50), cv2.FONT_HERSHEY_COMPLEX, 1, (50, 50, 255), 1)
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (50, 50, 255), 1)
                cv2.imshow('frame', frame)
                k = cv2.waitKey(1)
                if k == ord('q') or len(faces_data) >= framesTotal:
                    break

            video.release()
            cv2.destroyAllWindows()

            # Save the full name, ID number, and faces data to the database
            faces_data = np.asarray(faces_data)
            faces_data = faces_data.reshape((framesTotal, -1))

            # Insert voter and faces data into the database
            try:
                cursor.execute("INSERT INTO voters (full_name, id_number) VALUES (%s, %s)", (full_name, id_number))
                db.commit()
                print(f"Inserted voter: {full_name}, ID: {id_number}")  # Log successful insertion

                voter_id = cursor.lastrowid  # Get the last inserted voter ID
                for face in faces_data:
                    face_blob = face.tobytes()
                    cursor.execute("INSERT INTO faces (voter_id, face_data) VALUES (%s, %s)", (voter_id, face_blob))
                
                db.commit()

                # Display a success message on the same page
                return render_template('index.html', success_message='Successful!', show_registration=False)

            except mysql.connector.Error as err:
                print(f"Failed to insert voter: {err}")  # Log any errors
                return render_template('index.html', error_message='Failed to insert voter data.')

            except Exception as e:
                print(f"An error occurred: {e}")
                return render_template('index.html', error_message='An error occurred during registration.')

        except Exception as e:
            print(f"An error occurred while capturing faces: {e}")
            return render_template('index.html', error_message='An error occurred during face capture.')

    return render_template('index.html', success_message='', show_registration=True)

@app.route('/voter_login', methods=['GET', 'POST'])
def voter_login():
    if request.method == 'POST':
        fullname = request.form['fullname']
        id_number = request.form['id_number']

        # Check if the voter exists in the database
        cursor.execute("SELECT id FROM voters WHERE full_name = %s AND id_number = %s", (fullname, id_number))
        voter = cursor.fetchone()

        if voter:
            session['voter_logged_in'] = True
            session['voter_id'] = voter[0]
            return redirect(url_for('give_vote'))
        else:
            return render_template('voter_login.html', error_message='Invalid full name or ID number')

    return render_template('voter_login.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Validate the credentials
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            return render_template('admin_dashboard.html')  # Render the admin dashboard
        else:
            error_message = 'Invalid username or password'
            return render_template('admin_login.html', error_message=error_message)

    # Always show the login page on GET request
    return render_template('admin_login.html')


@app.route('/voting_message')
def voting_message():
    return render_template('voting_message.html')

@app.route('/give_vote')
def give_vote():
    if 'voter_logged_in' not in session:
        return redirect(url_for('voter_login'))

    subprocess.run([sys.executable, 'give_vote.py'])

    # Render a template with the "Your vote has been recorded" message and the voting status link
    return render_template('vote_confirmation.html')


@app.route('/voting_status')
def voting_status():
    return render_template('voting_status.html')

@app.route('/get_voting_status')
def get_voting_status():
    # Query for the total number of voters
    cursor.execute("SELECT COUNT(*) FROM voters")
    total_voters = cursor.fetchone()[0]
    
    # Query for the vote counts per candidate
    cursor.execute("SELECT candidate, COUNT(*) as vote_count FROM votes GROUP BY candidate")
    vote_counts = cursor.fetchall()

    # Create HTML content for the total number of voters
    html_content = f'<p>Total Voters: {total_voters}</p>'
    
    # Check if there are any vote counts
    if len(vote_counts) == 0:
        html_content += '<p>No votes have been recorded yet.</p>'
    else:
        html_content += '<table><tr><th>Candidate</th><th>Votes</th></tr>'
        for candidate in vote_counts:
            html_content += f'<tr><td>{candidate[0]}</td><td>{candidate[1]}</td></tr>'
        html_content += '</table>'
    
    print(f"Total Voters: {total_voters}, Votes: {vote_counts}")  # Log for debugging
    
    # Create the response with no-cache headers
    response = make_response(html_content)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response

if __name__ == '__main__':
    app.run(debug=True)
