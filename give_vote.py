from sklearn.neighbors import KNeighborsClassifier
import cv2
import numpy as np
import os
import time
from datetime import datetime
from win32com.client import Dispatch
import mysql.connector

def speak(str1):
    speak = Dispatch(("SAPI.SpVoice"))
    speak.Speak(str1)

# Database connection
db = mysql.connector.connect(
    host='localhost',
    user='admin',  # Use your actual MySQL username
    password='password',  # Use your actual MySQL password
    database='voting_system'
)
cursor = db.cursor()

video = cv2.VideoCapture(0)
facedetect = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# Load faces and labels from the database
cursor.execute("SELECT voter_id, face_data FROM faces")
faces_data = cursor.fetchall()

LABELS = []
FACES = []

for voter_id, face_data in faces_data:
    LABELS.append(voter_id)
    face_array = np.frombuffer(face_data, dtype=np.uint8).reshape((50, 50, 3)).flatten()
    FACES.append(face_array)

FACES = np.array(FACES)
LABELS = np.array(LABELS)

knn = KNeighborsClassifier(n_neighbors=5)
knn.fit(FACES, LABELS)
imgBackground = cv2.imread("image.png")

def check_if_exists(voter_id):
    """Check if the voter has already voted."""
    cursor.execute("SELECT * FROM votes WHERE voter_id = %s", (voter_id,))
    return cursor.fetchone() is not None

while True:
    ret, frame = video.read()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = facedetect.detectMultiScale(gray, 1.3, 5)
    
    detected_face = None  # Track the detected face
    detected_voter_id = None  # Track the recognized voter ID

    for (x, y, w, h) in faces:
        crop_img = frame[y:y+h, x:x+w]
        resized_img = cv2.resize(crop_img, (50, 50)).flatten().reshape(1, -1)
        detected_voter_id = knn.predict(resized_img)
        detected_face = True  # Mark that a face has been detected
        break  # Process only the first detected face for simplicity

    if detected_face:
        ts = time.time()
        date = datetime.fromtimestamp(ts).strftime("%d-%m-%Y")
        timestamp = datetime.fromtimestamp(ts).strftime("%H:%M-%S")

        # Draw bounding box and label on the frame
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 0, 255), 1)
        cv2.rectangle(frame, (x, y), (x+w, y+h), (50, 50, 255), 2)
        cv2.rectangle(frame, (x, y-40), (x+w, y), (50, 50, 255), -1)
        cv2.putText(frame, str(detected_voter_id[0]), (x, y-15), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 255), 1)
        
        # Display frame
        frame_resized = cv2.resize(frame, (400, 250))  # Resize frame to match the region size
        imgBackground[160:160 + 250, 80:80 + 400] = frame_resized
        cv2.imshow('frame', imgBackground)
        
        k = cv2.waitKey(1)
        
        if k == ord('1') or k == ord('2') or k == ord('3'):
            voter_id = int(detected_voter_id[0])
            
            if check_if_exists(voter_id):
                speak("YOU HAVE ALREADY VOTED")
                break

            candidate = ""
            if k == ord('1'):
                candidate = "PAUL KAGAME"
            elif k == ord('2'):
                candidate = "DONALD TRUMP"
            elif k == ord('3'):
                candidate = "EMMANUEL MACRON"
                
            if candidate:
                # Get the current date and timestamp just before inserting into the database
                now = datetime.now()
                date = now.strftime("%Y-%m-%d")
                timestamp = now.strftime("%H:%M:%S")
                
                speak("YOUR VOTE HAS BEEN RECORDED")
                time.sleep(1)
                cursor.execute("INSERT INTO votes (voter_id, candidate, vote_date, vote_time) VALUES (%s, %s, %s, %s)",
                               (voter_id, candidate, date, timestamp))
                db.commit()
                speak("THANK YOU FOR PARTICIPATING IN THE ELECTIONS")
                break

video.release()
cv2.destroyAllWindows()
