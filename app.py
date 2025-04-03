import os
from flask import Flask, request, jsonify, render_template
import google.generativeai as genai
from dotenv import load_dotenv
import sqlite3
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
API_KEY = os.getenv("GEMINI_API_KEY","AIzaSyD1hgSI9E6DWu9rywzi099nbl-E1eQ6xOQ")
assert API_KEY, "ERROR: Gemini API Key is missing"

# Configure Gemini API
genai.configure(api_key=API_KEY)

# Select the Gemini model
model = genai.GenerativeModel("gemini-1.5-pro-latest")

# Initialize Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = None  # Allow unlimited content length
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", os.urandom(24))  # Generate a secure secret key
csrf = CSRFProtect(app)  # Initialize CSRF protection

# Setup rate limiting
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"])

# Setup SQLite database
def init_db():
    conn = sqlite3.connect('policies.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS policies (id INTEGER PRIMARY KEY, scenario TEXT, generated_policy TEXT)''')
    conn.commit()
    conn.close()

init_db()

# Error handler for 413
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "File is too large. Please upload a smaller file."}), 413

# Home route
@app.route('/')
def home():
    return render_template('index.html')

# Route to provide CSRF token to JavaScript
@app.route('/csrf-token', methods=['GET'])
def get_csrf_token():
    return jsonify({'csrf_token': generate_csrf()})

# Summarize policy route with rate limiting
@app.route('/summarize', methods=['POST'])
@limiter.limit("10 per minute")  # Limit to 10 requests per minute
def summarize():
    content = request.form.get('content', '')
    file = request.files.get('file')

    if file:
        # Read the content of the uploaded file
        if file.filename.endswith('.txt'):
            content = file.read().decode('utf-8')
        elif file.filename.endswith('.pdf'):
            import PyPDF2
            reader = PyPDF2.PdfReader(file)
            content = ''.join([page.extract_text() for page in reader.pages])
        elif file.filename.endswith(('.doc', '.docx')):
            from docx import Document
            doc = Document(file)
            content = '\n'.join([para.text for para in doc.paragraphs])
        else:
            return jsonify({"error": "Unsupported file type"})

    prompt = f"Summarize the following economic policy document: {content}"
    try:
        response = model.generate_content(prompt)
        summary = response.text
        return jsonify({"summary": summary})
    except Exception as e:
        # Fallback mechanism for quota errors
        if "429" in str(e):
            return jsonify({"error": "API quota exhausted. Please try again later."})
        else:
            return jsonify({"error": str(e)})

# Generate custom policy route
@app.route('/generate', methods=['POST'])
def generate():
    scenario = request.form['scenario']
    prompt = f"Generate a detailed economic policy based on this scenario: {scenario}"
    try:
        response = model.generate_content(prompt)
        policy = response.text
        
        # Save the scenario and generated policy to the database
        conn = sqlite3.connect('policies.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO policies (scenario, generated_policy) VALUES (?, ?)", (scenario, policy))
        conn.commit()
        conn.close()

        return jsonify({"policy": policy})
    except Exception as e:
        return jsonify({"error": str(e)})

# Classify text route
@app.route('/classify', methods=['POST'])
def classify():
    inquiry = request.form['inquiry']
    prompt = f"Classify the following inquiry into one of the following categories: [Pricing, Hardware Support, Software Support]\n\nInquiry: {inquiry}\n\nClassified category:"
    try:
        response = model.generate_content(prompt)
        category = response.text
        return jsonify({"category": category})
    except Exception as e:
        return jsonify({"error": str(e)})

# Generate product names route
@app.route('/product_names', methods=['POST'])
def product_names():
    description = request.form['description']
    seed_words = request.form['seed_words']
    prompt = f"Product description: {description}\nSeed words: {seed_words}\nProduct names:"
    try:
        response = model.generate_content(prompt)
        names = response.text
        return jsonify({"product_names": names})
    except Exception as e:
        return jsonify({"error": str(e)})

# File upload route
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"})
    
    # Process file upload - in this case we're just acknowledging receipt
    return jsonify({"message": "File successfully uploaded"})

if __name__ == '__main__':
    app.run(debug=True)