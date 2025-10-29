import os
from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import math
from sqlalchemy import func, extract, and_
import io  # NEW IMPORT
import csv # NEW IMPORT

# --- App & Database Configuration ---
# --- App & Database Configuration ---
basedir = os.path.abspath(os.path.dirname(__file__))

# --- Force PostgreSQL Connection ---
database_uri = os.environ.get('DATABASE_URL')

# Check if the environment variable is missing
if not database_uri:
    # If DATABASE_URL is not set on Render, this will cause the app to crash on startup
    # which is better than silently failing back to SQLite.
    raise ValueError("DATABASE_URL environment variable is not set!")

# Ensure it uses 'postgresql://' prefix required by SQLAlchemy
if database_uri.startswith("postgres://"):
    database_uri = database_uri.replace("postgres://", "postgresql://", 1)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_change_this'
# Directly use the PostgreSQL URI from the environment variable
app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# --- End of Configuration Update ---

db = SQLAlchemy(app)

# --- Database Models (Unchanged) ---
class Deductee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pan_number = db.Column(db.String(10), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    deductee_type = db.Column(db.String(20), nullable=False, default='Other')
    transactions = db.relationship('Transaction', back_populates='deductee')

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deductee_id = db.Column(db.Integer, db.ForeignKey('deductee.id'), nullable=False)
    deductee = db.relationship('Deductee', back_populates='transactions')
    tds_section = db.Column(db.String(10), nullable=True, default='194C') 
    invoice_date = db.Column(db.DateTime, nullable=False)
    invoice_amount = db.Column(db.Float, nullable=False, default=0.0) 
    assessable_amount = db.Column(db.Float, nullable=False, default=0.0)
    payment_mode = db.Column(db.String(50), nullable=True)
    payment_reference = db.Column(db.String(100), nullable=True)
    tds_rate = db.Column(db.Float, nullable=False, default=1.0)
    tax = db.Column(db.Float, nullable=False, default=0.0)
    sur_charge = db.Column(db.Float, nullable=False, default=0.0)
    cess = db.Column(db.Float, nullable=False, default=0.0)
    interest = db.Column(db.Float, nullable=False, default=0.0)
    total_tds = db.Column(db.Float, nullable=False, default=0.0)
    challan_id = db.Column(db.Integer, db.ForeignKey('challan.id'), nullable=True)
    challan = db.relationship('Challan', back_populates='transactions')

class Challan(db.Model):
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


# --- Helper Function for Summaries (Unchanged) ---
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

# --- Helper function to calculate TDS rate (Unchanged) ---
def get_tds_rate(pan, deductee_type, section):
    if not pan or len(pan) != 10:
        return 20.0
    if section == '194C':
        return 1.0 if deductee_type in ['individual', 'huf'] else 2.0
    elif section == '194H':
        return 5.0
    elif section == '194J':
        return 10.0
    elif section == '194I-A':
        return 2.0
    elif section == '194I-B':
        return 10.0
    return 0.0


# --- Routes (All routes are the same, except for the NEW /download_csv route) ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add', methods=['POST'])
def add_transaction():
    try:
        pan = request.form.get('pan').upper()
        name = request.form.get('name')
        deductee_type = request.form.get('deductee_type')
        section = request.form.get('tdsSection') 
        invoice_date_str = request.form.get('invoice_date')
        invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d')
        invoice_amount = float(request.form.get('invoice_amount'))
        assessable_amount = float(request.form.get('assessable_amount'))
        payment_mode = request.form.get('payment_mode')
        payment_reference = request.form.get('payment_reference')
        
        deductee = Deductee.query.filter_by(pan_number=pan).first()
        if not deductee:
            deductee = Deductee(pan_number=pan, name=name, deductee_type=deductee_type)
            db.session.add(deductee)
        else:
            deductee.name = name
            deductee.deductee_type = deductee_type
            
        tds_rate = get_tds_rate(pan, deductee_type, section)
        tax = math.ceil(assessable_amount * (tds_rate / 100.0))
        sur_charge = 0.0
        cess = math.ceil(tax * 0.04)
        total_tds = tax + sur_charge + cess
        
        new_transaction = Transaction(
            deductee=deductee, tds_section=section, invoice_date=invoice_date,
            invoice_amount=invoice_amount, assessable_amount=assessable_amount,
            tds_rate=tds_rate, tax=tax, sur_charge=sur_charge,
            cess=cess, interest=0.0, total_tds=total_tds,
            payment_mode=payment_mode, payment_reference=payment_reference
        )
        db.session.add(new_transaction)
        db.session.commit()
        flash('Transaction saved successfully!')
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving transaction: {str(e)}')
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
        section = request.form.get('tdsSection')
        invoice_date_str = request.form.get('invoice_date')
        assessable_amount = float(request.form.get('assessable_amount'))
        invoice_amount = assessable_amount 
        payment_mode = request.form.get('payment_mode')
        payment_reference = request.form.get('payment_reference')
        
        deductee = Deductee.query.filter_by(pan_number=pan).first()
        if not deductee:
            deductee = Deductee(
                pan_number=pan, name=name, deductee_type=deductee_type
            )
            db.session.add(deductee)
        else:
            deductee.name = name
            deductee.deductee_type = deductee_type
            
        tds_rate = get_tds_rate(pan, deductee_type, section)
        tax = math.ceil(assessable_amount * (tds_rate / 100.0))
        sur_charge = 0.0
        cess = math.ceil(tax * 0.04)
        total_tds = tax + sur_charge + cess
        
        new_transaction = Transaction(
            deductee=deductee, tds_section=section, invoice_date=invoice_date,
            invoice_amount=invoice_amount, assessable_amount=assessable_amount,
            tds_rate=tds_rate, tax=tax, sur_charge=sur_charge,
            cess=cess, interest=0.0, total_tds=total_tds,
            payment_mode=payment_mode, payment_reference=payment_reference
        )
        db.session.add(new_transaction)
        db.session.commit()
        flash('Record submitted successfully. Thank you!')
    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting record: {str(e)}')
    return redirect(url_for('client_entry'))

@app.route('/annexure')
def annexure_report():
    all_transactions = Transaction.query.order_by(Transaction.invoice_date).all()
    return render_template('annexure.html', transactions=all_transactions)

# ---
# --- NEW ROUTE FOR DOWNLOADING CSV ---
# ---
@app.route('/download_csv')
def download_csv():
    # 1. Fetch all transactions
    all_transactions = Transaction.query.order_by(Transaction.invoice_date).all()
    
    # 2. Create a "file" in memory
    si = io.StringIO()
    cw = csv.writer(si)
    
    # 3. Write the Header Row
    header = [
        'Date', 'PAN', 'Name of Deductee', 'TDS Section', 
        'Assessable Amount', 'TDS Rate', 'Tax', 'Cess', 'Total TDS',
        'Payment Mode', 'Payment Reference'
    ]
    cw.writerow(header)
    
    # 4. Write all the data rows
    for tx in all_transactions:
        row = [
            tx.invoice_date.strftime('%Y-%m-%d'),
            tx.deductee.pan_number,
            tx.deductee.name,
            tx.tds_section,
            tx.assessable_amount,
            tx.tds_rate,
            tx.tax,
            tx.cess,
            tx.total_tds,
            tx.payment_mode,
            tx.payment_reference
        ]
        cw.writerow(row)
        
    # 5. Create the response
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=tds_report.csv"
    output.headers["Content-type"] = "text/csv"
    return output


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
        flash(f'Error saving challan: {str(e)}')
    return redirect(url_for('challan_summary'))

# --- Main Application Runner ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all() 
    app.run(debug=True)