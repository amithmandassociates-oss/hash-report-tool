import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import math
from sqlalchemy import func, extract, and_

# --- App & Database Configuration ---
basedir = os.path.abspath(os.path.dirname(__file__))

# This is the smart database logic. It's perfect.
database_uri = os.environ.get('DATABASE_URL')
if database_uri:
    if database_uri.startswith("postgres://"):
        database_uri = database_uri.replace("postgres://", "postgresql://", 1)
else:
    database_uri = 'sqlite:///' + os.path.join(basedir, 'tds_database.db')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_change_this' 
app.config['SQLALCHEMY_DATABASE_URI'] = database_uri # Use the new smart URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# All UPLOAD_FOLDER logic is now GONE
db = SQLAlchemy(app)

# --- Database Models (Simplified) ---
class Deductee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pan_number = db.Column(db.String(10), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    deductee_type = db.Column(db.String(20), nullable=False, default='Other')
    # pan_image_path column is now GONE
    transactions = db.relationship('Transaction', back_populates='deductee')

class Transaction(db.Model):
    # No changes in this model
    id = db.Column(db.Integer, primary_key=True)
    deductee_id = db.Column(db.Integer, db.ForeignKey('deductee.id'), nullable=False)
    deductee = db.relationship('Deductee', back_populates='transactions')
    invoice_date = db.Column(db.DateTime, nullable=False)
    invoice_amount = db.Column(db.Float, nullable=False, default=0.0) 
    assessable_amount = db.Column(db.Float, nullable=False, default=0.0)
    tds_rate = db.Column(db.Float, nullable=False, default=1.0)
    tax = db.Column(db.Float, nullable=False, default=0.0)
    sur_charge = db.Column(db.Float, nullable=False, default=0.0)
    cess = db.Column(db.Float, nullable=False, default=0.0)
    interest = db.Column(db.Float, nullable=False, default=0.0)
    total_tds = db.Column(db.Float, nullable=False, default=0.0)
    challan_id = db.Column(db.Integer, db.ForeignKey('challan.id'), nullable=True)
    challan = db.relationship('Challan', back_populates='transactions')

class Challan(db.Model):
    # No changes in this model
    id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    total_tax = db.Column(db.Float, nullable=False, default=0.0)
    total_sur_charge = db.Column(db.Float, nullable=False, default=0.0)
    total_cess = db.Column(db.Float, nullable=False, default=0.0)
    total_interest = db.Column(db.Float, nullable=False, default=0.0)
    total_paid = db.Column(db.Float, nullable=False, default=0.0)
    challan_number = db.Column(db.String(50), nullable=True)
    bsr_code = db.Column(db.String(7), nullable=True)
    payment_date = db.Column(db.DateTime, nullable=True)
    transactions = db.relationship('Transaction', back_populates='challan')

# All file helper functions are GONE

# --- Helper Function for Summaries (Same as before) ---
def get_monthly_summary(year, month):
    summary = db.session.query(
        func.sum(Transaction.tax).label('total_tax'),
        func.sum(Transaction.cess).label('total_cess'),
        func.sum(Transaction.interest).label('total_interest')
    ).filter(
        extract('year', Transaction.invoice_date) == year,
        extract('month', Transaction.invoice_date) == month,
        Transaction.challan_id == None
    ).first()
    total_payable = (summary.total_tax or 0) + (summary.total_cess or 0) + (summary.total_interest or 0)
    return {
        'total_tax': summary.total_tax or 0,
        'total_cess': summary.total_cess or 0,
        'total_interest': summary.total_interest or 0,
        'total_payable': total_payable
    }

# --- Routes (Simplified) ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add', methods=['POST'])
def add_transaction():
    try:
        pan = request.form.get('pan').upper()
        name = request.form.get('name')
        deductee_type = request.form.get('deductee_type')
        invoice_date_str = request.form.get('invoice_date')
        invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d')
        invoice_amount = float(request.form.get('invoice_amount'))
        assessable_amount = float(request.form.get('assessable_amount'))
        
        deductee = Deductee.query.filter_by(pan_number=pan).first()
        if not deductee:
            # No file path to add
            deductee = Deductee(pan_number=pan, name=name, deductee_type=deductee_type)
            db.session.add(deductee)
        else:
            deductee.name = name
            deductee.deductee_type = deductee_type
            
        tds_rate = 0.0
        if len(pan) != 10: tds_rate = 20.0
        elif deductee_type == 'Company': tds_rate = 2.0
        else: tds_rate = 1.0
        tax = math.ceil(assessable_amount * (tds_rate / 100.0))
        sur_charge = 0.0
        cess = math.ceil(tax * 0.04)
        total_tds = tax + sur_charge + cess
        new_transaction = Transaction(
            deductee=deductee, invoice_date=invoice_date,
            invoice_amount=invoice_amount, assessable_amount=assessable_amount,
            tds_rate=tds_rate, tax=tax, sur_charge=sur_charge,
            cess=cess, interest=0.0, total_tds=total_tds
        )
        db.session.add(new_transaction)
        db.session.commit()
        flash('Transaction saved successfully!')
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving transaction: {e}')
    return redirect(url_for('index'))

@app.route('/client')
def client_entry():
    return render_template('client_entry.html')

@app.route('/client_submit', methods=['POST'])
def client_submit():
    try:
        pan = request.form.get('pan').upper()
        name = request.form.get('name')
        deductee_type = request.form.get('deductee_type') 
        invoice_date_str = request.form.get('invoice_date')
        invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d')
        assessable_amount = float(request.form.get('assessable_amount'))
        invoice_amount = assessable_amount 
        
        # All file upload logic is GONE
        
        deductee = Deductee.query.filter_by(pan_number=pan).first()
        if not deductee:
            deductee = Deductee(
                pan_number=pan, 
                name=name, 
                deductee_type=deductee_type
                # No file path
            )
            db.session.add(deductee)
        else:
            deductee.name = name
            deductee.deductee_type = deductee_type
            # No file path
            
        tds_rate = 0.0
        if len(pan) != 10:
            tds_rate = 20.0
        elif deductee_type in ['company', 'firm', 'other']:
            # This handles Company, Firm, AOP, BOI, etc.
            tds_rate = 2.0
        elif deductee_type in ['individual', 'huf']:
            # This handles Individual and HUF
            tds_rate = 1.0
        else:
            # A fallback just in case
            tds_rate = 1.0

        tax = math.ceil(assessable_amount * (tds_rate / 100.0))
        sur_charge = 0.0
        cess = math.ceil(tax * 0.04)
        total_tds = tax + sur_charge + cess
        
        new_transaction = Transaction(
            deductee=deductee, invoice_date=invoice_date,
            invoice_amount=invoice_amount,
            assessable_amount=assessable_amount,
            tds_rate=tds_rate, tax=tax, sur_charge=sur_charge,
            cess=cess, interest=0.0, total_tds=total_tds
        )
        db.session.add(new_transaction)
        db.session.commit()
        flash('Record submitted successfully. Thank you!')
    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting record: {e}')
    return redirect(url_for('client_entry'))

# The '/uploads' route is GONE

@app.route('/annexure')
def annexure_report():
    all_transactions = Transaction.query.order_by(Transaction.invoice_date).all()
    return render_template('annexure.html', transactions=all_transactions)

# All other routes are the same
@app.route('/challan')
def challan_summary():
    pending_query = db.session.query(
        extract('month', Transaction.invoice_date).label('month'),
        extract('year', Transaction.invoice_date).label('year'),
        func.sum(Transaction.tax).label('total_tax'),
        func.sum(Transaction.cess).label('total_cess'),
        func.sum(Transaction.interest).label('total_interest')
    ).filter(Transaction.challan_id == None
    ).group_by(extract('year', Transaction.invoice_date), extract('month', Transaction.invoice_date)
    ).order_by(extract('year', Transaction.invoice_date), extract('month', Transaction.invoice_date)
    ).all()
    pending_list = []
    for summary in pending_query:
        total_payable = summary.total_tax + summary.total_cess + summary.total_interest
        pending_list.append({
            'month': int(summary.month), 'year': int(summary.year),
            'month_year': f"{int(summary.month):02d}/{int(summary.year)}",
            'total_tax': summary.total_tax, 'total_cess': summary.total_cess,
            'total_interest': summary.total_interest, 'total_payable': total_payable
        })
    paid_list = Challan.query.order_by(Challan.year, Challan.month).all()
    return render_template('challan.html', 
                           pending_summaries=pending_list, 
                           paid_challans=paid_list)

@app.route('/update_challan/<int:year>/<int:month>')
def update_challan_form(year, month):
    totals = get_monthly_summary(year, month)
    return render_template('update_challan.html', 
                           year=year, month=month, totals=totals)

@app.route('/save_challan', methods=['POST'])
def save_challan():
    try:
        month = int(request.form.get('month'))
        year = int(request.form.get('year'))
        payment_date_str = request.form.get('payment_date')
        payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d')
        challan_number = request.form.get('challan_number')
        bsr_code = request.form.get('bsr_code')
        totals = get_monthly_summary(year, month)
        new_challan = Challan(
            month=month, year=year,
            total_tax=totals['total_tax'], total_sur_charge=0.0,
            total_cess=totals['total_cess'], total_interest=totals['total_interest'],
            total_paid=totals['total_payable'],
            challan_number=challan_number, bsr_code=bsr_code,
            payment_date=payment_date
        )
        db.session.add(new_challan)
        db.session.commit()
        transactions_to_update = Transaction.query.filter(
            extract('year', Transaction.invoice_date) == year,
            extract('month', Transaction.invoice_date) == month,
            Transaction.challan_id == None
        ).all()
        for tx in transactions_to_update:
            tx.challan_id = new_challan.id
        db.session.commit()
        flash('Challan payment saved successfully!')
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving challan: {e}')
    return redirect(url_for('challan_summary'))


# --- Main Application Runner ---
if __name__ == '__main__':
    with app.app_context():
        # This will create all the tables in the new database
        # It will also update your local 'tds_database.db'
        db.create_all() 
    app.run(debug=True)