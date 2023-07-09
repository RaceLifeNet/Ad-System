import os
import time
import random
import json
import threading
from flask import Flask, request, jsonify, send_from_directory, render_template, abort, send_file
from werkzeug.utils import secure_filename
import string
import requests
import datetime
import re

app = Flask(__name__)

# Password to access the web panel
PASSWORD = "password"

# Path to the JSON file
JSON_FILE = "ads.json"

# Directory to store ad images
AD_IMAGES_DIR = "api/ad_images"

# Load ads from JSON file
def load_ads():
    try:
        with open(JSON_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return []

# Save ads to JSON file
def save_ads(ads):
    with open(JSON_FILE, "w") as file:
        json.dump(ads, file, indent=4)
    log_message = f"Ads modified at {datetime.datetime.now()}"
    send_discord_log(log_message)

# Check if the image has dimensions 1920x1080
def is_image_valid(file_path):
    try:
        from PIL import Image
        image = Image.open(file_path)
        return image.size == (1920, 1080)
    except (IOError, ImportError):
        return False

# Generate a random file name for the uploaded image
def generate_random_filename():
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(10))

# Generate a public URL for the uploaded image
def get_public_url(filename):
    return f"https://ads.race-life.net/{AD_IMAGES_DIR}/{filename}"

# Recheck the JSON file every 5 seconds
def recheck_json():
    global ads
    while True:
        ads = load_ads()
        time.sleep(60)
        print("Re-checked Ad Database")

# Start the background task for rechecking the JSON file
recheck_thread = threading.Thread(target=recheck_json)
recheck_thread.daemon = True
recheck_thread.start()

# Remove an ad campaign and its corresponding ad image
def remove_ad(ad_id):
    global ads

    ad_id = int(ad_id)

    for ad in ads:
        if ad['id'] == ad_id:
            ads.remove(ad)
            save_ads(ads)

            ad_image_path = os.path.join(AD_IMAGES_DIR, os.path.basename(ad['ad_image']))
            if os.path.exists(ad_image_path):
                os.remove(ad_image_path)

            log_message = f"Ad removed: ID={ad_id}, Link={ad['ad_link']}, Image={ad['ad_image']}, Timestamp={datetime.datetime.now()}"
            send_discord_log(log_message)

            break

# Endpoint to serve a random ad in JSON
@app.route('/api/serve_ad', methods=['GET'])
def serve_ad():
    if len(ads) > 0:
        ad = random.choice(ads)
        return jsonify(ad)
    else:
        return jsonify({'error': 'No ads available.'})

@app.route('/api/ad_images/<path:filename>')
def serve_ad_image(filename):
    file_path = os.path.join(AD_IMAGES_DIR, filename)
    
    # Check if the file exists
    if not os.path.isfile(file_path):
        abort(404)  # Return a 404 error if the file doesn't exist
    
    # Determine the file extension
    file_extension = os.path.splitext(filename)[1].lower()
    
    # Serve image files
    if file_extension in ['.png', '.jpg', '.jpeg', '.gif']:
        return send_from_directory(AD_IMAGES_DIR, filename)
    
    # Serve video files
    if file_extension in ['.mp4', '.obv']:
        return send_from_directory(AD_IMAGES_DIR, filename, mimetype='video/mp4')
    
    # Return a 404 error for unsupported file types
    abort(404)

# Endpoint for adding an ad campaign
@app.route('/admin/add_ad', methods=['POST'])
def add_ad():
    password = request.form.get('password')
    if password != PASSWORD:
        return "Invalid password."

    ad_link = request.form.get('ad_link')
    ad_image = request.files.get('ad_image')

    # Check if an image was uploaded
    if ad_image and ad_image.filename != '':
        filename = secure_filename(ad_image.filename)
        random_filename = generate_random_filename() + os.path.splitext(filename)[1]
        image_path = os.path.join(AD_IMAGES_DIR, random_filename)

        # Save the uploaded image
        ad_image.save(image_path)

        # Check if the image has valid dimensions
        if is_image_valid(image_path):
            ad = {
                "id": len(ads) + 1,
                "ad_link": ad_link,
                "ad_image": get_public_url(random_filename)
            }
            ads.append(ad)
            save_ads(ads)

            log_message = f"Ad added: ID={ad['id']}, Link={ad_link}, Image={ad['ad_image']}, Timestamp={datetime.datetime.now()}"
            send_discord_log(log_message)

            return "Ad added successfully!"
        else:
            os.remove(image_path)  # Remove the invalid image
            return "Invalid image dimensions. Image must be 1920x1080."

    return "No image uploaded."

# Endpoint for removing an ad campaign
@app.route('/admin/remove_ad', methods=['POST'])
def remove_ad_endpoint():
    password = request.form.get('password')
    if password != PASSWORD:
        return "Invalid password."

    ad_id = request.form.get('ad_id')
    remove_ad(ad_id)
    return "Ad removed successfully!"

# Web panel HTML
WEB_PANEL_HTML = '''
<html>
<head>
    <meta name="viewport" content="width=device-width">
    </head>
    <body>
    <form method="post" enctype="multipart/form-data" action="/admin/add_ad">
        <h2>Add Ad</h2>
        <label for="password">Password:</label>
        <input type="password" id="password" name="password">
        <br><br>
        <label for="ad_link">Ad Link:</label>
        <input type="text" id="ad_link" name="ad_link">
        <br><br>
        <label for="ad_image">Ad Image:</label>
        <input type="file" id="ad_image" name="ad_image">
        <br><br>
        <input type="submit" value="Add Ad">
    </form>
    <br><br>
    <form method="post" action="/admin/remove_ad">
        <h2>Remove Ad</h2>
        <label for="password">Password:</label>
        <input type="password" id="password" name="password">
        <br><br>
        <label for="ad_id">Ad ID:</label>
        <input type="text" id="ad_id" name="ad_id">
        <br><br>
        <input type="submit" value="Remove Ad">
    </form>
    </body>
    </html>
'''

# Endpoint for the web panel
@app.route('/admin', methods=['GET'])
def web_panel():
    return WEB_PANEL_HTML

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('api/favicons', 'favicon.ico')

@app.route('/robot.txt')
def serve_robot_txt():
    return send_file('api/robot.txt')

@app.route('/sitemap.xml')
def serve_sitemap():
    return send_file('api/sitemap.xml')
  
@app.route('/')
def index():
    template = render_template('index.html')
    cleaned_template = remove_whitespace_between_tags(template)
    return cleaned_template

# Function to remove whitespace between HTML tags
def remove_whitespace_between_tags(html):
    pattern = r">\s+<"
    cleaned_html = re.sub(pattern, '><', html)
    return cleaned_html

# Function to send a log message to Discord
def send_discord_log(content):
    webhook_url = os.environ['DISCORD_WEBHOOK']
    headers = {'Content-Type': 'application/json'}

    if isinstance(content, dict):
        # Embed with ad image
        embed = {
            'title': 'Ad System Log',
            'color': 16711680,  # Red
            'image': {
                'url': content['ad_image']
            }
        }
    else:
        # Regular log message
        embed = {
            'title': 'Ad System Log',
            'description': content,
            'color': 16711680  # Red
        }

    payload = {'embeds': [embed]}
    response = requests.post(webhook_url, headers=headers, json=payload)

    if response.status_code != 204:
        print('Failed to send Discord log:', response.text)

if __name__ == '__main__':
    if not os.path.exists(AD_IMAGES_DIR):
        os.makedirs(AD_IMAGES_DIR)
    ads = load_ads()
    app.run(host='0.0.0.0', port=81)
