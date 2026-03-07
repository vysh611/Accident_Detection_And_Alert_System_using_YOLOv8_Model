from flask import Flask, render_template, redirect, url_for, flash, request, session, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from ultralytics import YOLO
from PIL import Image
import numpy as np
import cv2
import os 
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.message import EmailMessage
import imghdr
from datetime import datetime


# Initialize the Flask app and configure the database
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
# Path to save uploaded images
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# Model for User table in the database
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(1), nullable=False)
    mobile = db.Column(db.String(15), nullable=False)

# Routes for pages
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            session['user_id'] = user.id  # Store user ID in session
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password.', 'danger')
    return render_template('auth.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        age = request.form.get('age')
        gender = request.form.get('gender')
        mobile = request.form.get('mobile')

        if len(mobile) != 10 or not mobile.isdigit():
            flash('Mobile number must be exactly 10 digits.', 'danger')
            return render_template('auth.html')

        if User.query.filter_by(email=email).first():
            flash('Email address already in use. Please choose a different one.', 'danger')
            return render_template('auth.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('auth.html')

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, email=email, password=hashed_password, age=age, gender=gender, mobile=mobile)
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('auth.html')

@app.route('/home')
def home():
    return render_template('home.html')

# Load the pre-trained YOLOv8 model
model = YOLO('best.pt')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        # Get the uploaded file
        uploaded_file = request.files['image_file']

        if uploaded_file.filename != '':
            # Save the uploaded file
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], uploaded_file.filename)
            uploaded_file.save(file_path)

            # Determine if it's an image or video based on extension
            file_ext = uploaded_file.filename.lower().split('.')[-1]
            is_video = file_ext in ['mp4', 'avi', 'mov', 'mkv']

            accident_detected = False
            result_image = None
            result_video = None

            if is_video:
                # Process video
                cap = cv2.VideoCapture(file_path)
                if not cap.isOpened():
                    flash('Error opening video file.', 'danger')
                    return render_template('upload.html')

                fps = cap.get(cv2.CAP_PROP_FPS)
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

                result_filename = 'result_' + uploaded_file.filename
                result_path = os.path.join(app.config['UPLOAD_FOLDER'], result_filename)
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Use mp4v for MP4
                out = cv2.VideoWriter(result_path, fourcc, fps, (width, height))

                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        break

                    # Perform inference using YOLOv8
                    results = model(frame)
                    result = results[0]

                    # Get bounding boxes and labels
                    boxes = result.boxes.xywh.cpu().numpy()
                    labels = result.names

                    for i, box in enumerate(boxes):
                        class_id = int(result.boxes.cls[i])
                        label_name = labels[class_id]

                        if "accident" in label_name.lower():
                            accident_detected = True

                        # Draw bounding box
                        x_center, y_center, w, h = box
                        x1 = int(x_center - w / 2)
                        y1 = int(y_center - h / 2)
                        x2 = int(x_center + w / 2)
                        y2 = int(y_center + h / 2)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, label_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                    out.write(frame)

                cap.release()
                out.release()

                result_video = url_for('uploaded_file', filename=result_filename)

            else:
                # Process image (existing code)
                image = cv2.imread(file_path)

                results = model(image)
                result = results[0]

                boxes = result.boxes.xywh.cpu().numpy()
                labels = result.names

                for i, box in enumerate(boxes):
                    class_id = int(result.boxes.cls[i])
                    label_name = labels[class_id]

                    if "accident" in label_name.lower():
                        accident_detected = True

                    x_center, y_center, width, height = box
                    x1 = int(x_center - width / 2)
                    y1 = int(y_center - height / 2)
                    x2 = int(x_center + width / 2)
                    y2 = int(y_center + height / 2)

                    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(image, label_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                result_filename = 'result_' + uploaded_file.filename
                result_image_path = os.path.join(app.config['UPLOAD_FOLDER'], result_filename)
                cv2.imwrite(result_image_path, image)

                result_image = url_for('uploaded_file', filename=result_filename)

            detection_message = "Accident Detected" if accident_detected else "No Accident Detected"
            print(detection_message)

            # Send email notification if an accident is detected
            if accident_detected:
                send_email_notification(uploaded_file.filename, is_video=is_video)
                print("Send")

            return render_template('upload.html', result_image=result_image, result_video=result_video, detection_message=detection_message)

    # If it's a GET request, render the upload form
    return render_template('upload.html')

def send_email_notification(filename, is_video=False):
    # Content for the email
    msg = 'Dear Sir,'
    m = 'We have detected an accident in the uploaded file.'
    dt = "Detected on "
    tm = 'at '
    im = "Kindly have a look at the attached file and take necessary actions."
    t = 'Regards,'
    t1 = 'Vehicle Accident Detection System'

    date = datetime.now().strftime("%Y-%m-%d")
    timeStamp = datetime.now().strftime("%H:%M:%S")

    mail_content = msg + '\n' + m + ' ' + dt + date + tm + timeStamp + '.' + im + '\n' + '\n' + t + '\n' + t1

    # Sender details
    sender_address = "cse.takeoff@gmail.com"  # Use your own email address
    sender_pass = "digkagfgyxcjltup" # Use your own email password
    receiver_addresses = ["rautaishwarya24999@gmail.com"]  # Admin email to receive the notification

    # Create the email message
    newMessage = EmailMessage()
    newMessage['Subject'] = "Vehicle Accident Detection"
    newMessage['From'] = sender_address
    newMessage['To'] = ', '.join(receiver_addresses)
    newMessage.set_content(mail_content)

    # Attach the result file
    attach_filename = 'result_' + filename
    attach_path = os.path.join(app.config['UPLOAD_FOLDER'], attach_filename)
    with open(attach_path, 'rb') as f:
        attach_data = f.read()

    if is_video:
        # Assume MP4 for video
        newMessage.add_attachment(attach_data, maintype='video', subtype='mp4', filename=attach_filename)
    else:
        # For image
        image_type = imghdr.what(attach_path)
        newMessage.add_attachment(attach_data, maintype='image', subtype=image_type, filename=attach_filename)

    # Send the email (using SMTP with SSL for Gmail)
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(sender_address, sender_pass)
        smtp.send_message(newMessage)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Logout route
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)