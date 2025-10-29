import os
# NEW IMPORT
from dotenv import load_dotenv 
from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import math
from sqlalchemy import func, extract, and_
import io
import csv

# --- Configuration & Database Connection ---
# NEW: Load the .env file (if it exists) before accessing os.environ
load_dotenv() 

basedir = os.path.abspath(os.path.dirname(__file__))

# --- Force PostgreSQL Connection from Environment or Secret File ---
database_uri = os.environ.get('DATABASE_URL')

# Check if the environment variable is missing after trying to load it
if not database_uri:
    # If this still fails, the problem is critical.
    raise ValueError("DATABASE_URL environment variable is not set! (Check Render Secret File)")

# Ensure it uses 'postgresql://' prefix required by SQLAlchemy
if database_uri.startswith("postgres://"):
    database_uri = database_uri.replace("postgres://", "postgresql://", 1)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_change_this' 
app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ... (Rest of app.py models and functions remain the same) ...
# ... (All routes are the same) ...

# Database Models (Ensure these are present in your file)
class Deductee(db.Model):
# ... (Model Definition) ...

class Transaction(db.Model):
# ... (Model Definition) ...

class Challan(db.Model):
# ... (Model Definition) ...

def get_monthly_summary(year, month):
# ... (Function Definition) ...

def get_tds_rate(pan, deductee_type, section):
# ... (Function Definition) ...

# @app.route('/') and all other routes below are unchanged
# ... (Continue with the rest of your app.py content) ...

if __name__ == '__main__':
    with app.app_context():
        db.create_all() 
    app.run(debug=True)